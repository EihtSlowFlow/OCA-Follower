# 📦 OCA-Follower

Monitor autónomo de envíos para **OCA Argentina** que notifica cada cambio de estado directamente a tu **WhatsApp**, sin necesidad de entrar manualmente a la web ni resolver CAPTCHAs.

El sistema consulta el Web Service público e-Pak de OCA (`Oep_TrackEPak.asmx/Tracking_Pieza`) mediante peticiones HTTP POST, normaliza el XML de producción, persiste el historial de eventos en **SQLite** (modo WAL con firmas SHA-256 para evitar alertas duplicadas) y despacha notificaciones push instantáneas a través de la API gratuita de **[CallMeBot](https://www.google.com/search?q=https%3A%2F%2Fwww.callmebot.com%2Fblog%2Ffree-api-whatsapp-messages%2F)**.

## ✨ Características Principales

* **Cero CAPTCHAs ni navegadores pesados**: Consulta directamente el endpoint `Tracking_Pieza` del servicio ASMX de OCA por `POST` de formulario, evitando los desafíos anti-bot del frontend web.
* **Tolerancia al esquema XML real de OCA**: Soporta tanto etiquetas estándar como las particularidades reales del backend de OCA en producción (incluyendo el histórico typo `<Desdcripcion_Estado>`, `<Descripcion_Motivo>`, `<SUC>`, `<fecha>` y el ordenamiento cronológico de múltiples nodos `<Table>`).
* **Deduplicación criptográfica en SQLite**: Almacena cada evento con una firma única `SHA-256(tracking:estado:fecha)` en `data/tracker.db` (`PRAGMA journal_mode = WAL` y `busy_timeout = 5000`), garantizando que nunca recibas dos veces la misma alerta.
* **Detección automática de entrega**: Marca automáticamente el paquete como entregado (`is_delivered = True`) cuando el estado alcanza la fase final, deteniendo el sondeo innecesario sobre ese envío.
* **Daemon resiliente con Backoff Exponencial**: Incorpora espera progresiva con *jitter* aleatorio (`60s` a `900s`) ante caídas de red o mantenimiento de OCA, y apagado limpio (*graceful shutdown*) ante señales `SIGINT` y `SIGTERM`.
* **Arquitectura Agent-First**: Incluye definiciones modulares en `skills/` para que editores como Google Antigravity IDE o Claude Code comprendan las reglas de negocio y esquemas sin alucinar endpoints.

## 🗂️ Estructura del Proyecto

```text
OCA-Follower/
├── deploy/
│   └── oca-tracker.service       # Unidad systemd para ejecución continua en segundo plano
├── skills/
│   ├── daemon-scheduler/
│   │   └── SKILL.md              # Orquestación del loop, backoff exponencial y señales POSIX
│   ├── oca-soap-query/
│   │   └── SKILL.md              # Especificación del endpoint Tracking_Pieza y esquema XML
│   ├── sqlite-state-tracker/
│   │   └── SKILL.md              # Persistencia WAL, firmas SHA-256 y detección de deltas
│   └── whatsapp-callmebot-alert/
│       └── SKILL.md              # Formateo Markdown y despacho vía CallMeBot API
├── src/
│   ├── __init__.py
│   ├── main.py                   # Punto de entrada CLI y bucle principal del daemon
│   ├── models.py                 # Modelos de dominio (TrackingEvent, PackageConfig, DeltaResult)
│   ├── clients/
│   │   ├── __init__.py
│   │   └── oca_client.py         # Cliente HTTP POST y parser XML tolerante a fallos
│   ├── notifiers/
│   │   ├── __init__.py
│   │   ├── base.py               # Interfaz abstracta de notificaciones
│   │   └── whatsapp.py           # Cliente CallMeBot con formato enriquecido e íconos dinámicos
│   └── storage/
│       ├── __init__.py
│       └── state_store.py        # Gestor SQLite de paquetes e historial de eventos
├── tests/
│   ├── __init__.py
│   └── test_oca_client.py        # Suite de 10 tests unitarios y de concurrencia
├── .env.example                  # Plantilla de variables de entorno
├── .gitignore
├── config.yaml                   # Configuración general y lista inicial de envíos
├── plan_implementacion_oca_tracker.md
├── requirements.txt
└── README.md
```

## 🚀 Instalación y Configuración Rápida

### 1. Clonar el repositorio y crear el entorno virtual

```bash
git clone https://github.com/EihtSlowFlow/OCA-Follower.git
cd OCA-Follower
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Activar tu API Key gratuita de CallMeBot (WhatsApp)

1. Agendá el número del bot de CallMeBot en tus contactos (verificá el número activo en [CallMeBot WhatsApp API](https://www.google.com/search?q=https%3A%2F%2Fwww.callmebot.com%2Fblog%2Ffree-api-whatsapp-messages%2F), habitualmente `+34 623 78 64 49`).
2. Enviá por WhatsApp a ese contacto exactamente este mensaje:
   ```text
   I allow callmebot to send me messages
   ```
3. Guardá la **API Key** numérica que te responderá el bot en unos segundos.

### 3. Configurar variables de entorno (`.env`)

Copiá la plantilla `.env.example` y restringí sus permisos de lectura:

```bash
cp .env.example .env
chmod 600 .env
```

Editá el archivo `.env` con tus datos reales:

```env
# Número en formato internacional para Argentina (+54 9 + código de área sin 15 + número)
CALLMEBOT_PHONE=+5491112345678
CALLMEBOT_API_KEY=tu_api_key_aqui

TRACKER_DB_PATH=data/tracker.db
POLL_INTERVAL_SECONDS=1200
LOG_LEVEL=INFO
OCA_TIMEOUT_SECONDS=15
```

### 4. Registrar tus paquetes (`config.yaml` o CLI)

Podés declarar tus envíos en `config.yaml` (se sincronizan automáticamente con la base SQLite al iniciar):

```yaml
packages:
  - tracking_number: "3890200000000012345"
    alias: "Compra Componentes PC"
    active: true
```

## 💻 Uso por Línea de Comandos (CLI)

| Comando | Descripción |
| :--- | :--- |
| `python3 -m src.main --test-whatsapp "Mensaje"` | Envía un mensaje de prueba para validar tus credenciales de CallMeBot en `.env`. |
| `python3 -m src.main --add-package <NRO> "<ALIAS>"` | Agrega o actualiza un número de seguimiento directamente en la base SQLite. |
| `python3 -m src.main --status` | Muestra en consola una tabla con todos los paquetes registrados, su último estado y si fueron entregados. |
| `python3 -m src.main --once` | Ejecuta un único ciclo de consulta, guarda novedades, envía alertas si hubo cambios y finaliza. |
| `python3 -m src.main --daemon` | Inicia el servicio en bucle continuo (por defecto cada 20 minutos) con manejo de señales y backoff exponencial. |

### Ejemplo de alerta recibida en WhatsApp

```text
📦 *Novedad en tu paquete OCA*

🏷️ *Paquete:* Compra Componentes PC
• *Estado:* 🚚 *En sucursal destino - Listo para retirar*
• *Fecha:* 2026-10-19T11:30:00-03:00
• *Ubicación:* SUC. BELGRANO
• *Tracking:* `3890200000000012345`
🔄 *Estado anterior:* En viaje
```

## ⚙️ Ejecución como Servicio en Linux (`systemd`)

El repositorio incluye una unidad lista para producción en `deploy/oca-tracker.service` que levanta el daemon tras conectarse a la red y lo reinicia automáticamente en caso de fallo:

```bash
# 1. Ajustar usuario y rutas absolutas en el archivo de servicio si corresponde
nano deploy/oca-tracker.service

# 2. Copiar e instalar la unidad en systemd
sudo cp deploy/oca-tracker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now oca-tracker.service

# 3. Verificar estado y seguir los logs en vivo
systemctl status oca-tracker.service
journalctl -u oca-tracker.service -f
```

## 🔍 Detalles Técnicos del Web Service de OCA

Durante la ingeniería inversa y validación contra los servidores de producción de OCA (`webservice.oca.com.ar`), se resolvieron tres particularidades críticas reflejadas en `src/clients/oca_client.py`:

1. **`Tracking_Pieza` vs `GetEnvioEstadoActual`**: El método `GetEnvioEstadoActual` devuelve `HTTP 500 (Missing parameter: ordenRetiro)`, un dato interno que solo posee el comercio remitente. En cambio, `Tracking_Pieza` invocado vía `POST` (`application/x-www-form-urlencoded`) con `Pieza=<tracking>`, `NroDocumentoCliente=""` y `CUIT=""` responde `HTTP 200` con el historial completo sin requerir credenciales empresariales.
2. **Namespace `#Oca_e_Pak`**: El servicio SOAP utiliza el namespace propietario `#Oca_e_Pak` en lugar de `tempuri.org`. Usar el binding HTTP POST evita fallos de validación de sobres SOAP manuales.
3. **Esquema XML y el typo `<Desdcripcion_Estado>`**: La respuesta `DataSet` / `DiffGram` enumera cada evento histórico en bloques `<Table>` ordenados cronológicamente (donde el último `<Table>` representa el estado vigente). En producción, OCA etiqueta el campo de estado como `<Desdcripcion_Estado>` (con una **"d" intermedia extra**), la sucursal como `<SUC>` y la marca de tiempo como `<fecha>`. El parser prioriza estas etiquetas exactas y concatena `<Descripcion_Motivo>` cuando aporta información relevante (ignorando `"Sin Motivo"`).

## 🧪 Pruebas Automatizadas

La suite de pruebas (`tests/test_oca_client.py`) valida el parseo del esquema XML real de OCA, el filtrado de `"Sin Motivo"`, la firma determinista SHA-256, la detección de deltas e historial de entregas en SQLite, la escritura concurrente multihilo en modo WAL y el cálculo de backoff exponencial:

```bash
pytest tests/ -v
```
