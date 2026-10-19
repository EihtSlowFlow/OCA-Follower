"""Tests for OCAClient XML parsing, delta detection, and formatting."""

import concurrent.futures
import pytest
from src.clients.oca_client import OCAClient
from src.models import PackageConfig, TrackingEvent, DeltaResult, TrackingResponse
from src.storage.state_store import StateStore
from src.notifiers.whatsapp import CallMeBotWhatsAppNotifier
from src.main import calculate_backoff, GracefulKiller


SAMPLE_OCA_DIFFGRAM_XML = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <soap:Body>
    <Tracking_PiezaResponse xmlns="http://tempuri.org/">
      <Tracking_PiezaResult>
        <diffgr:diffgram xmlns:msdata="urn:schemas-microsoft-com:xml-msdata"
                         xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1">
          <NewDataSet xmlns="">
            <Table diffgr:id="Table1" msdata:rowOrder="0">
              <NumeroEnvio>3890200000000012345</NumeroEnvio>
              <Descripcion_Estado>Ingreso a Planta</Descripcion_Estado>
              <Descripcion_Motivo>Procesamiento inicial</Descripcion_Motivo>
              <Fecha>2026-03-10T11:00:00</Fecha>
              <Sucursal>PLANTA VELEZ SARSFIELD</Sucursal>
            </Table>
            <Table diffgr:id="Table2" msdata:rowOrder="1">
              <NumeroEnvio>3890200000000012345</NumeroEnvio>
              <Descripcion_Estado>En Sucursal</Descripcion_Estado>
              <Descripcion_Motivo>Disponible para retiro</Descripcion_Motivo>
              <Fecha>2026-03-12T15:30:00</Fecha>
              <Sucursal>SUC. BELGRANO</Sucursal>
            </Table>
          </NewDataSet>
        </diffgr:diffgram>
      </Tracking_PiezaResult>
    </Tracking_PiezaResponse>
  </soap:Body>
</soap:Envelope>
"""

SAMPLE_EMPTY_DIFFGRAM_XML = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <Tracking_PiezaResponse xmlns="http://tempuri.org/">
      <Tracking_PiezaResult>
        <diffgr:diffgram xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1">
          <NewDataSet xmlns="" />
        </diffgr:diffgram>
      </Tracking_PiezaResult>
    </Tracking_PiezaResponse>
  </soap:Body>
</soap:Envelope>
"""


OCA_REAL_SCHEMA_XML = """<?xml version="1.0" encoding="utf-8"?>
<DataSet xmlns="#Oca_e_Pak">
  <xs:schema id="NewDataSet" xmlns="" xmlns:xs="http://www.w3.org/2001/XMLSchema"
             xmlns:msdata="urn:schemas-microsoft-com:xml-msdata">
    <xs:element name="NewDataSet" msdata:IsDataSet="true" msdata:Locale="">
      <xs:complexType><xs:choice minOccurs="0" maxOccurs="unbounded" /></xs:complexType>
    </xs:element>
  </xs:schema>
  <diffgr:diffgram xmlns:msdata="urn:schemas-microsoft-com:xml-msdata"
                   xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1">
    <NewDataSet xmlns="">
      <Table diffgr:id="Table1" msdata:rowOrder="0">
        <NumeroEnvio>3890200000000012345</NumeroEnvio>
        <Desdcripcion_Estado>Ingresado</Desdcripcion_Estado>
        <Descripcion_Motivo>Sin Motivo</Descripcion_Motivo>
        <SUC>CENTRO DE DISTRIBUCION BARRACAS</SUC>
        <fecha>2026-03-10T11:00:00-03:00</fecha>
      </Table>
      <Table diffgr:id="Table2" msdata:rowOrder="1">
        <NumeroEnvio>3890200000000012345</NumeroEnvio>
        <Desdcripcion_Estado>En viaje</Desdcripcion_Estado>
        <Descripcion_Motivo>Sin Motivo</Descripcion_Motivo>
        <SUC>CENTRO DE DISTRIBUCION BARRACAS</SUC>
        <fecha>2026-03-11T08:30:00-03:00</fecha>
      </Table>
      <Table diffgr:id="Table3" msdata:rowOrder="2">
        <NumeroEnvio>3890200000000012345</NumeroEnvio>
        <Desdcripcion_Estado>En sucursal destino</Desdcripcion_Estado>
        <Descripcion_Motivo>Listo para retirar</Descripcion_Motivo>
        <SUC>SUC. BELGRANO</SUC>
        <fecha>2026-03-12T15:30:00-03:00</fecha>
      </Table>
    </NewDataSet>
  </diffgr:diffgram>
</DataSet>
"""


def test_parse_tracking_xml_with_events():
    """Generic synonyms (Descripcion_Estado / Sucursal / Fecha); motive is merged into status."""
    events = OCAClient.parse_tracking_xml(SAMPLE_OCA_DIFFGRAM_XML, "3890200000000012345")
    assert len(events) == 2

    ev1 = events[0]
    assert ev1.status == "Ingreso a Planta - Procesamiento inicial"
    assert ev1.branch == "PLANTA VELEZ SARSFIELD"
    assert ev1.event_date == "2026-03-10T11:00:00"

    ev2 = events[1]
    assert ev2.status == "En Sucursal - Disponible para retiro"
    assert ev2.branch == "SUC. BELGRANO"
    assert ev2.event_date == "2026-03-12T15:30:00"


def test_parse_tracking_xml_oca_real_schema_uses_last_table():
    """Real OCA tags: Desdcripcion_Estado (typo), SUC, fecha; last <Table> is the latest event."""
    events = OCAClient.parse_tracking_xml(OCA_REAL_SCHEMA_XML, "3890200000000012345")
    assert len(events) == 3

    # "Sin Motivo" is NOT appended to the status
    assert events[0].status == "Ingresado"
    assert events[1].status == "En viaje"
    assert events[1].branch == "CENTRO DE DISTRIBUCION BARRACAS"

    # Last <Table>: real motive IS concatenated to the status
    last = events[-1]
    assert last.status == "En sucursal destino - Listo para retirar"
    assert last.branch == "SUC. BELGRANO"
    assert last.event_date == "2026-03-12T15:30:00-03:00"
    assert last.tracking_number == "3890200000000012345"

    response = TrackingResponse(tracking_number="3890200000000012345", events=events)
    assert response.latest_event is last


def test_parse_tracking_xml_empty_dataset():
    events = OCAClient.parse_tracking_xml(SAMPLE_EMPTY_DIFFGRAM_XML, "3890200000000012345")
    assert events == []


def test_parse_tracking_xml_invalid_text():
    events = OCAClient.parse_tracking_xml("", "123")
    assert events == []


def test_event_hash_deterministic():
    ev1 = TrackingEvent(
        tracking_number="3890200000000012345",
        status="En Sucursal",
        motive="Disponible",
        branch="BELGRANO",
        event_date="2026-03-12T15:30:00",
    )
    ev2 = TrackingEvent(
        tracking_number="3890200000000012345",
        status="En Sucursal",
        motive="Disponible",
        branch="BELGRANO",
        event_date="2026-03-12T15:30:00",
    )
    assert ev1.event_hash == ev2.event_hash

    # Different date or status must produce different hash
    ev3 = TrackingEvent(
        tracking_number="3890200000000012345",
        status="Entregado",
        motive="Firma",
        branch="BELGRANO",
        event_date="2026-03-13T10:00:00",
    )
    assert ev1.event_hash != ev3.event_hash


def test_sqlite_delta_detection(tmp_path):
    db_file = tmp_path / "test_tracker.db"
    store = StateStore(db_path=str(db_file), wal_mode=False)

    pkg = PackageConfig(tracking_number="TEST1234", alias="Teclado")
    store.sync_configured_packages([pkg])

    # First batch: 2 events
    ev1 = TrackingEvent(
        tracking_number="TEST1234",
        status="En Viaje",
        branch="Rosario",
        event_date="2026-03-10 10:00:00",
    )
    ev2 = TrackingEvent(
        tracking_number="TEST1234",
        status="En Sucursal",
        branch="Buenos Aires",
        event_date="2026-03-11 12:00:00",
    )

    delta1 = store.detect_and_save_deltas(pkg, [ev1, ev2])
    assert delta1.has_deltas is True
    assert len(delta1.new_events) == 2
    assert delta1.current_status == "En Sucursal"

    # Second batch with same events (should detect 0 deltas)
    delta2 = store.detect_and_save_deltas(pkg, [ev1, ev2])
    assert delta2.has_deltas is False
    assert len(delta2.new_events) == 0

    # Third batch with a new 'Entregado' event
    ev3 = TrackingEvent(
        tracking_number="TEST1234",
        status="Entregado a titular",
        branch="Buenos Aires",
        event_date="2026-03-12 16:00:00",
    )
    delta3 = store.detect_and_save_deltas(pkg, [ev1, ev2, ev3])
    assert delta3.has_deltas is True
    assert len(delta3.new_events) == 1
    assert delta3.new_events[0].status == "Entregado a titular"

    # Verify package is now marked delivered
    updated_pkg = store.get_package("TEST1234")
    assert updated_pkg is not None
    assert updated_pkg.is_delivered is True
    assert updated_pkg.current_status == "Entregado a titular"


def test_whatsapp_message_formatter():
    notifier = CallMeBotWhatsAppNotifier(phone="5491112345678", api_key="testkey")
    pkg = PackageConfig(tracking_number="12345", alias="Mi Monitor")
    event = TrackingEvent(
        tracking_number="12345",
        status="En Sucursal",
        branch="Sucursal Centro",
        motive="Retiro disponible",
        event_date="2026-03-15 10:00:00",
    )
    delta = DeltaResult(
        package=pkg,
        new_events=[event],
        previous_status="En Tránsito",
        current_status="En Sucursal",
    )

    msg = notifier.format_event_message(delta)
    assert "Novedad en tu paquete OCA" in msg
    assert "Mi Monitor" in msg
    assert "En Sucursal" in msg
    assert "Sucursal Centro" in msg
    assert "Retiro disponible" in msg


def test_calculate_backoff_progression():
    """Validates exponential backoff progression and max_backoff cap with jitter."""
    base = 60.0
    cap = 900.0

    # Error 1: ~60s (±20%)
    b1 = calculate_backoff(1, base_backoff=base, max_backoff=cap, jitter_factor=0.2)
    assert 48.0 <= b1 <= 72.0

    # Error 2: ~120s (±20%)
    b2 = calculate_backoff(2, base_backoff=base, max_backoff=cap, jitter_factor=0.2)
    assert 96.0 <= b2 <= 144.0

    # Error 3: ~240s (±20%)
    b3 = calculate_backoff(3, base_backoff=base, max_backoff=cap, jitter_factor=0.2)
    assert 192.0 <= b3 <= 288.0

    # Error 5: 60 * 2^4 = 960 -> capped at 900s (±20%)
    b5 = calculate_backoff(5, base_backoff=base, max_backoff=cap, jitter_factor=0.2)
    assert 720.0 <= b5 <= 1080.0

    # Error 10: still capped around 900s
    b10 = calculate_backoff(10, base_backoff=base, max_backoff=cap, jitter_factor=0.0)
    assert b10 == 900.0


def test_sqlite_concurrent_writes(tmp_path):
    """Validates concurrent threads writing to StateStore with WAL and busy_timeout."""
    db_file = tmp_path / "concurrent_tracker.db"
    store = StateStore(db_path=str(db_file), wal_mode=True)

    def worker(i: int):
        pkg = PackageConfig(tracking_number=f"TRK_{i}", alias=f"Package {i}")
        store.sync_configured_packages([pkg])
        event = TrackingEvent(
            tracking_number=f"TRK_{i}",
            status="En Viaje",
            branch="Centro",
            event_date="2026-10-19 10:00:00",
        )
        res = store.detect_and_save_deltas(pkg, [event])
        return res.has_deltas

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(20)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 20
    assert all(results)
    assert len(store.get_all_packages()) == 20


def test_daemon_graceful_killer():
    """Validates GracefulKiller non-blocking wait and immediate termination."""
    killer = GracefulKiller()
    assert killer.should_stop is False

    # Short wait with timeout (should return False when not stopped)
    stopped = killer.wait(0.05)
    assert stopped is False

    # Trigger stop event
    killer.stop_event.set()
    assert killer.should_stop is True

    # Immediate return when stopped
    stopped_now = killer.wait(5.0)
    assert stopped_now is True

