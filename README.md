# 📦 OCA WhatsApp Tracker

Sistema automatizado en Python para monitoreo de envíos de **OCA (Argentina)** mediante consultas a su servicio web SOAP/ASMX (`Tracking_Pieza`), persistencia y detección de deltas con **SQLite**, y despacho de alertas instantáneas por **WhatsApp** utilizando la API de **CallMeBot**. Diseñado para ejecutarse como daemon continuo o tarea programada.

---

## 🗂️ Estructura del Proyecto

```text
oca-whatsapp-tracker/
├── skills/
│   ├── oca-soap-query/
│   │   └── SKILL.md              # Skill: Querying OCA ASMX endpoint & XML parsing
│   ├── whatsapp-callmebot-alert/
│   │   └── SKILL.md              # Skill: Formatting & dispatching WhatsApp notifications
│   ├── sqlite-state-tracker/
│   │   └── SKILL.md              # Skill: Delta detection & state persistence
│   └── daemon-scheduler/
│       └── SKILL.md              # Skill: Polling loop, backoff & signal handling
├── .env.example
├── .env
├── config.yaml
├── requirements.txt
├── README.md
├── data/
│   └── tracker.db
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   ├── clients/
│   │   ├── __init__.py
│   │   └── oca_client.py
│   ├── storage/
│   │   ├── __init__.py
│   │   └── state_store.py
│   └── notifiers/
│       ├── __init__.py
│       ├── base.py
│       └── whatsapp.py
└── tests/
    ├── __init__.py
    └── test_oca_client.py
```

---

## 🚀 Inicio Rápido

### 1. Requisitos Previos
- Python 3.10 o superior.
- Una cuenta de WhatsApp activa.

### 2. Instalación de Dependencias
```bash
cd oca-whatsapp-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuración de CallMeBot (WhatsApp)
Para recibir las notificaciones en tu WhatsApp:
1. Agrega el número del bot de CallMeBot a tus contactos (ver número actual en [CallMeBot WhatsApp](https://www.callmebot.com/blog/free-api-whatsapp-messages/)).
2. Envía el siguiente mensaje desde tu WhatsApp al bot:
   ```text
   I allow callmebot to send me messages
   ```
3. El bot te responderá con tu **API Key** personal.

### 4. Variables de Entorno (`.env`)
Copia `.env.example` a `.env` y completa tus credenciales:
```bash
cp .env.example .env
```
Edita `.env`:
```env
# Teléfono en formato internacional sin '+' ni espacios (ej: 5491112345678)
CALLMEBOT_PHONE=5491112345678
CALLMEBOT_API_KEY=tu_api_key_aqui
POLL_INTERVAL_SECONDS=900
LOG_LEVEL=INFO
```

### 5. Configurar Paquetes a Seguir (`config.yaml`)
Define tus paquetes en `config.yaml` o agrégalos por CLI:
```yaml
packages:
  - tracking_number: "3890200000000012345"
    alias: "Notebook Dell"
    active: true
```

---

## 💻 Modos de Uso

### Probar envío de WhatsApp
Verifica que las credenciales de CallMeBot funcionen correctamente:
```bash
python3 -m src.main --test-whatsapp "Hola! Prueba de alerta OCA Tracker 🚀"
```

### Agregar un nuevo paquete por línea de comandos
```bash
python3 -m src.main --add-package 3890200000000012345 "Monitor Gamer"
```

### Ver tabla de estado actual de todos los paquetes
```bash
python3 -m src.main --status
```

### Ejecutar una sola sincronización (`--once`)
Consulta OCA, procesa deltas, notifica y finaliza (ideal para cron jobs):
```bash
python3 -m src.main --once
```

### Ejecutar como Daemon continuo (`--daemon`)
Ejecuta el loop con intervalo configurable (por defecto cada 15 min), backoff exponencial con jitter en caso de fallas y apagado graceful ante `Ctrl+C` o `SIGTERM`:
```bash
python3 -m src.main --daemon
```

---

## 🧠 Skills Incluidos

Cada skill cuenta con documentación técnica exhaustiva en formato estándar YAML frontmatter + Markdown:

| Skill | Directorio | Descripción |
| :--- | :--- | :--- |
| **OCA SOAP Query** | [`skills/oca-soap-query/SKILL.md`](skills/oca-soap-query/SKILL.md) | Consulta al endpoint ASMX de OCA (`Tracking_Pieza`), construcción de envelopes SOAP 1.1 y parseo de respuestas Microsoft .NET `DataSet` / `DiffGram`. |
| **WhatsApp Alert** | [`skills/whatsapp-callmebot-alert/SKILL.md`](skills/whatsapp-callmebot-alert/SKILL.md) | Formateo estético de mensajes con emojis y markdown, sanitización telefónica y despacho HTTP via CallMeBot. |
| **SQLite State Tracker** | [`skills/sqlite-state-tracker/SKILL.md`](skills/sqlite-state-tracker/SKILL.md) | Persistencia en base de datos local SQLite con WAL mode, deduplicación mediante huella hash SHA-256 y ciclo de vida de entregas. |
| **Daemon Scheduler** | [`skills/daemon-scheduler/SKILL.md`](skills/daemon-scheduler/SKILL.md) | Loop resiliente con backoff exponencial adaptativo, manejo seguro de señales POSIX (`SIGINT`, `SIGTERM`) y servicio systemd. |

---

## 🧪 Pruebas Automatizadas

El proyecto incluye tests unitarios para el parser XML, la detección de deltas en SQLite y el formateador de alertas:
```bash
pytest tests/ -v
```
