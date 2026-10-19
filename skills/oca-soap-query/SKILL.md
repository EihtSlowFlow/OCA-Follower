---
name: oca-soap-query
description: Queries OCA Argentina e-Pak ASMX web service (Tracking_Pieza) via HTTP POST, bypasses frontend CAPTCHA, and extracts structured shipping event data from the DiffGram XML.
---

# OCA ASMX/XML Tracking Query Skill

## 1. Purpose
Retrieves real-time shipment history directly from OCA's e-Pak ASMX integration endpoint, without Cloudflare challenges, browser sessions or reCAPTCHA.

---

## 2. Target Endpoint (verified against the live service)

- **Base URL**: `https://webservice.oca.com.ar/epak_tracking/Oep_TrackEPak.asmx`
- **Method used**: `Tracking_Pieza`
- **Call**: `POST {base}/Tracking_Pieza` with `application/x-www-form-urlencoded`
- **Parameters** (per WSDL): `Pieza` (tracking number), `NroDocumentoCliente` (may be empty), `CUIT` (may be empty)
- **Headers**: realistic `User-Agent`.

```text
POST /epak_tracking/Oep_TrackEPak.asmx/Tracking_Pieza
Pieza=3890200000000012345&NroDocumentoCliente=&CUIT=
```

> [!WARNING]
> - `GetEnvioEstadoActual` does **not** work for this use case: it requires `numeroEnvio` **and** `ordenRetiro` (a pickup-order id only the shipper has). Calling it with only the tracking number returns `HTTP 500: Missing parameter: ordenRetiro`.
> - The service's XML/SOAP namespace is `#Oca_e_Pak`, **not** `http://tempuri.org/`. A SOAP envelope built with `tempuri.org` fails with `Server did not recognize the value of HTTP Header SOAPAction`. The HTTP POST binding avoids the problem.
> - `Oep_TrackVP.asmx` does not exist (404). There is no known fallback endpoint.
> - Related methods in the WSDL: `Tracking_PiezaExtendido` (same params), `Tracking_PiezaNumeroEnvio` (`Pieza`), `Tracking_Pieza_ConIdEstado` (`NumeroEnvio`).

---

## 3. Response Structure

The response is an ADO.NET `DataSet` serialized as DiffGram:

```xml
<DataSet xmlns="#Oca_e_Pak">
  <xs:schema id="NewDataSet" ...>...</xs:schema>
  <diffgr:diffgram xmlns:msdata="urn:schemas-microsoft-com:xml-msdata"
                   xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1">
    <NewDataSet xmlns="">
      <Table diffgr:id="Table1" msdata:rowOrder="0"> ... </Table>
    </NewDataSet>
  </diffgr:diffgram>
</DataSet>
```

An unknown tracking number returns HTTP 200 with an **empty** `<diffgr:diffgram />` (confirmed live).

> [!NOTE]
> Row field names (`Descripcion_Estado`, `Fecha`, `Sucursal`, `Descripcion_Motivo`) come from public integrations and could **not** be verified without a real tracking number. The parser accepts several synonyms; validate with a real shipment (plan, Fase 1).

| Field (synonyms) | Description |
| :--- | :--- |
| `NumeroEnvio` / `Pieza` | Shipment identifier |
| `Descripcion_Estado` / `Estado` | Delivery phase |
| `Fecha` / `Fecha_Estado` | Event timestamp |
| `Sucursal` / `Descripcion_Sucursal` | Branch / facility |
| `Descripcion_Motivo` / `Motivo` | Cause or note |

---

## 4. Operational Workflow

1. Validate the tracking string (non-empty, trimmed).
2. POST to `Tracking_Pieza` with a 15 s timeout.
3. Parse with `xml.etree.ElementTree`, stripping namespaces.
4. Extract rows (`Table`/`Table1`/`Pieza`) with synonym fallbacks.
5. Sort events chronologically.

---

## 5. Implementation References

- [`OCAClient`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/clients/oca_client.py) in [`src/clients/oca_client.py`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/clients/oca_client.py) (`track_piece`, `_send_request`, `parse_tracking_xml`).
- [`TrackingEvent`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/models.py) and `TrackingResponse` in [`src/models.py`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/models.py).

---

## 6. Edge Cases & Resilience

- **Empty / unknown package**: empty diffgram → empty event list, no exception.
- **HTTP 5xx / network errors**: `TrackingResponse(success=False)`; the scheduler skips the package and applies backoff on repeated failures.
- **SSL**: keep `certifi` up to date.
