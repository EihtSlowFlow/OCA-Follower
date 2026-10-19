"""Client for interacting with OCA Argentina tracking ASMX/SOAP web services."""

import logging
import xml.etree.ElementTree as ET
from typing import List, Optional
import requests

from src.models import TrackingEvent, TrackingResponse

logger = logging.getLogger(__name__)


class OCAClient:
    """Client for querying package tracking information from OCA Argentina."""

    DEFAULT_EP_URL = "https://webservice.oca.com.ar/epak_tracking/Oep_TrackEPak.asmx"
    TRACKING_METHOD = "Tracking_Pieza"

    def __init__(
        self,
        asmx_url: Optional[str] = None,
        fallback_url: Optional[str] = None,
        timeout: int = 15,
        session: Optional[requests.Session] = None,
    ):
        self.asmx_url = asmx_url or self.DEFAULT_EP_URL
        # Optional secondary endpoint (none is known to exist by default).
        self.fallback_url = fallback_url
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "OCA-WhatsApp-Tracker/1.0 (Python/Requests)"
        })

    def track_piece(self, tracking_number: str) -> TrackingResponse:
        """Queries OCA web service (Tracking_Pieza) for a package tracking number.

        Uses the ASMX HTTP POST binding. Tries the optional fallback URL only if
        one is configured and the primary fails.
        """
        clean_tracking = str(tracking_number).strip()
        if not clean_tracking:
            return TrackingResponse(
                tracking_number=clean_tracking,
                events=[],
                success=False,
                error_message="Empty tracking number provided",
            )

        endpoints = [self.asmx_url]
        if self.fallback_url and self.fallback_url != self.asmx_url:
            endpoints.append(self.fallback_url)

        last_error = None
        for endpoint in endpoints:
            try:
                logger.debug("Querying OCA endpoint %s for piece %s", endpoint, clean_tracking)
                xml_response = self._send_request(endpoint, clean_tracking)
                events = self.parse_tracking_xml(xml_response, clean_tracking)
                return TrackingResponse(
                    tracking_number=clean_tracking,
                    events=events,
                    success=True,
                )
            except requests.RequestException as exc:
                last_error = f"Network error calling {endpoint}: {exc}"
                logger.warning(last_error)
            except ET.ParseError as exc:
                last_error = f"XML parsing error from {endpoint}: {exc}"
                logger.error(last_error)
            except Exception as exc:
                last_error = f"Unexpected error during tracking lookup: {exc}"
                logger.exception(last_error)

        return TrackingResponse(
            tracking_number=clean_tracking,
            events=[],
            success=False,
            error_message=last_error or "Unknown tracking error",
        )

    def _send_request(self, endpoint_url: str, tracking_number: str) -> str:
        """Calls Tracking_Pieza through the ASMX HTTP POST binding.

        The service's SOAP namespace is '#Oca_e_Pak' (not tempuri.org), so the
        form-encoded POST is used instead of a hand-built SOAP envelope.
        """
        response = self.session.post(
            f"{endpoint_url.rstrip('/')}/{self.TRACKING_METHOD}",
            data={
                "Pieza": tracking_number,
                "NroDocumentoCliente": "",
                "CUIT": "",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.text

    @staticmethod
    def parse_tracking_xml(xml_content: str, tracking_number: str = "") -> List[TrackingEvent]:
        """Parses Microsoft DataSet / DiffGram XML into a list of TrackingEvent objects."""
        if not xml_content or not xml_content.strip():
            return []

        try:
            root = ET.fromstring(xml_content.strip())
        except ET.ParseError:
            # Handle potential encoding declaration mismatch or leading BOM
            root = ET.fromstring(xml_content.strip().encode("utf-8"))

        # Strip XML namespaces for uniform querying across different response formats
        for elem in root.iter():
            if "}" in elem.tag:
                elem.tag = elem.tag.split("}", 1)[1]

        events: List[TrackingEvent] = []

        # In OCA ASMX DiffGrams, table rows are typically named 'Table', 'Table1', or 'Pieza'
        candidate_rows = (
            root.findall(".//Table") or
            root.findall(".//Table1") or
            root.findall(".//Pieza") or
            root.findall(".//diffgram/NewDataSet/*")
        )

        # OCA returns one <Table> per historical event in chronological order,
        # so document order is preserved and the LAST row is the latest event.
        for row in candidate_rows:
            # Status: 'Desdcripcion_Estado' is a real typo in OCA's backend
            status = OCAClient._first_text(
                row, "Desdcripcion_Estado", "Descripcion_Estado", "DescripcionEstado", "Estado"
            )

            # Skip header or empty rows
            if not status:
                continue

            # Motive: appended to the status unless it is empty or "Sin Motivo"
            motive = OCAClient._first_text(
                row, "Descripcion_Motivo", "DescripcionMotivo", "Motivo"
            )
            if motive and motive.strip().lower() != "sin motivo":
                status = f"{status} - {motive}"
            motive = ""  # already merged into status; avoids a duplicated 'Detalle'

            branch = OCAClient._first_text(
                row, "SUC", "Sucursal", "Descripcion_Sucursal", "CentroCosto"
            )

            date_str = OCAClient._first_text(
                row, "fecha", "Fecha", "FechaEntrega", "Fecha_Estado"
            )

            piece = OCAClient._first_text(
                row, "NumeroEnvio", "Pieza", "NroEnvio"
            ) or tracking_number

            raw_dict = {child.tag: (child.text or "").strip() for child in row}

            events.append(
                TrackingEvent(
                    tracking_number=piece or tracking_number,
                    status=status,
                    motive=motive,
                    branch=branch,
                    event_date=date_str,
                    raw_data=raw_dict,
                )
            )

        return events

    @staticmethod
    def _first_text(row: ET.Element, *tags: str) -> str:
        """Returns the first non-empty child text among `tags` (priority order)."""
        for tag in tags:
            text = row.findtext(tag)
            if text and text.strip():
                return text.strip()
        return ""
