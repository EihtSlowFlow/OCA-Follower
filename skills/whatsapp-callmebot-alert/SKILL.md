---
name: whatsapp-callmebot-alert
description: Formats package milestone updates and sends instant WhatsApp push notifications to the user using the CallMeBot API.
---

# WhatsApp CallMeBot Alert Skill

## 1. Purpose
Formats package status transition milestones and delivers push alerts directly to the user's mobile device via WhatsApp using the CallMeBot HTTP gateway.

---

## 2. Target Endpoint & Parameters

- **Base URL**: `https://api.callmebot.com/whatsapp.php`
- **HTTP Method**: `GET`
- **Parameters**:
  - `phone`: Destination phone number in international E.164 format without `+` or spaces (e.g., `5491112345678`).
  - `text`: URL-encoded message text (`UTF-8`) supporting WhatsApp Markdown.
  - `apikey`: Private user authorization key.

### Account Activation
1. Save the CallMeBot bot phone number (from [CallMeBot](https://www.callmebot.com/blog/free-api-whatsapp-messages/)) to contacts.
2. Send WhatsApp message: `I allow callmebot to send me messages`.
3. Store the returned `apikey` into `.env`.

---

## 3. Message Formatting Standard

Alerts follow a clean, scannable layout using WhatsApp Markdown:

```text
📦 *Novedad en tu paquete OCA*

🏷️ *Paquete:* Notebook Lenovo
• *Estado:* 🏢 *En Sucursal*
• *Fecha:* 19/10/2026 10:15 hs
• *Ubicación:* Sucursal Belgrano
• *Tracking:* `3890200000000012345`
📝 *Detalle:* Listo para retiro
```

### Milestone Emojis
- 📦 Preparation / In depot (`Ingreso a Planta`)
- ✈️ In transit (`En Viaje`)
- 🏢 At local branch (`En Sucursal`, `Listo para retiro`)
- 🚚 Out for delivery (`En Distribución`, `En Móvil`)
- ✅ Delivered (`Entregado`)
- ⚠️ Incident / Warning (`Visita no concretada`, `Dirección errónea`)

---

## 4. Operational Workflow

1. **Credentials Verification**: Ensure `CALLMEBOT_PHONE` and `CALLMEBOT_API_KEY` are defined in the environment.
2. **Template Interpolation**: Populate the status template with package alias, new milestone, branch, and tracking code.
3. **URL Encoding**: Apply `urllib.parse.quote_plus` to the compiled UTF-8 string to encode emojis, newlines, and symbols.
4. **HTTP Dispatch**: Send the HTTP GET request with a 15-second timeout.
5. **Delivery Check**: Confirm HTTP 200 response and presence of acceptance keywords (`ok`, `queued`) in the response body.

---

## 5. Implementation References

The alert formatting and network dispatching logic are implemented in:

- **WhatsApp Notifier Class**: [`CallMeBotWhatsAppNotifier`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/notifiers/whatsapp.py#L14-L141) in [`src/notifiers/whatsapp.py`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/notifiers/whatsapp.py).
- **Template Formatter**: [`format_event_message`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/notifiers/whatsapp.py#L42-L86) in [`src/notifiers/whatsapp.py`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/notifiers/whatsapp.py).
- **Abstract Base Notifier**: [`BaseNotifier`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/notifiers/base.py#L7-L19) in [`src/notifiers/base.py`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/notifiers/base.py).

---

## 6. Edge Cases & Resilience

- **Rate Limiting**: CallMeBot enforces a cool-down period of 5–10 seconds between consecutive messages. When multiple shipments change status in the same polling cycle, queue and pace outgoing messages with a sleep interval.
- **Invalid API Key**: Detect non-200 responses or unauthorized errors and log actionable diagnostics without terminating tracking.
- **Emoji and Special Character Encoding**: Ensure proper UTF-8 percent-encoding so emojis render correctly on recipient mobile screens.
