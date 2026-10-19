# Plan de Implementación — OCA WhatsApp Tracker

## 1. Información General

| 

| **Campo** | **Valor** | 
| Responsable | Desarrollador Principal | 
| Fecha de inicio | 2026-10-19 | 
| Fecha objetivo | 2026-10-21 | 
| Versión | 0.2 (Validado contra servicio OCA) | 
| Estado global | ☐ Pendiente ☑ En curso ☐ Completado | 

## 2. Objetivo y Alcance

**Objetivo:** Automatizar el monitoreo periódico de envíos en OCA Argentina consultando su Web Service e-Pak (`Tracking_Pieza` por POST sin CAPTCHA) y despachar notificaciones push a WhatsApp ante cada cambio de estado detectado.

**Dentro del alcance:**

* Consultar periódicamente el endpoint ASMX de OCA (`Tracking_Pieza`) mediante peticiones HTTP POST de formulario (`application/x-www-form-urlencoded`).

* Parsear el payload XML (`NewDataSet/Table`) contemplando los nombres reales de los nodos de OCA (`Desdcripcion_Estado`, `Descripcion_Motivo`, `SUC`, `fecha`, `NumeroEnvio`).

* Almacenar el historial y el último estado en SQLite (`data/tracker.db`) en la tabla `shipment_events` con `PRAGMA busy_timeout = 5000` y firmas SHA-256 (`tracking:estado:fecha`).

* Despachar alertas formateadas en Markdown a WhatsApp a través de CallMeBot API.

* Ejecutar el monitor en segundo plano como servicio gestionado por systemd en Linux (`deploy/oca-tracker.service`).

**Fuera del alcance:**

* Resolver desafíos CAPTCHA o simular navegación interactiva en la interfaz web de OCA.

* Construir paneles gráficos de administración o interfaces web de usuario.

* Implementar respuestas interactivas o comandos bidireccionales dentro de WhatsApp.

**Criterios de éxito:**

* \[x\] Respuesta exitosa del Web Service de OCA (`Tracking_Pieza` vía POST) con código HTTP 200.

* \[ \] Recepción del mensaje de WhatsApp en el dispositivo móvil dentro de un intervalo de polling tras la actualización del envío.

* \[x\] Supresión total de alertas duplicadas al ejecutar ciclos de consulta consecutivos sobre el mismo estado.

* \[x\] Recuperación automática del proceso con reintentos y backoff exponencial ante cortes momentáneos de conectividad (validado con tests unitarios).

## 3. Prerrequisitos

| **Ítem** | **Detalle** | **Listo** | 
| Python 3.10+ instalado | Versión 3.10 o superior en el entorno de ejecución | \[x\] | 
| Dependencias (`requirements.txt`) | Instalación de `requests`, `pyyaml`, `python-dotenv`, `pytest` | \[x\] | 
| Número de WhatsApp | Línea receptora en formato internacional (`+549...`) | \[ \] | 
| API Key de CallMeBot | Clave personal activada con "I allow callmebot to send me messages" | \[ \] | 
| Números de tracking OCA a monitorear | Códigos de envío reales asignados a rastrear | \[ \] | 
| Servidor / equipo donde correrá el daemon | Máquina local 24/7 o VPS Linux para ejecución continua | \[x\] | 

## 4. Configuración

### 4.1 Variables de entorno (`.env`)

| **Variable** | **Valor / Decisión** | **Hecho** | 
| `CALLMEBOT_PHONE` | `+549XXXXXXXXXX` (pendiente completar por el usuario) | \[ \] | 
| `CALLMEBOT_API_KEY` | `XXXXXX` (pendiente completar por el usuario) | \[ \] | 
| `TRACKER_DB_PATH` | `data/tracker.db` | \[x\] | 
| `POLL_INTERVAL_SECONDS` | `1200` (20 minutos) | \[x\] | 
| `LOG_LEVEL` | `INFO` | \[x\] | 
| `OCA_TIMEOUT_SECONDS` | `15` | \[x\] | 

### 4.2 `config.yaml`

* \[x\] Paquetes definidos (`tracking_number`, `alias`, `active`)

* \[x\] Endpoint OCA validado: `http://webservice.oca.com.ar/epak_tracking/Oep_TrackEPak.asmx/Tracking_Pieza` (POST)

* \[x\] Parámetros de backoff (`min_backoff_seconds: 60`, `max_backoff_seconds: 900`)

* \[x\] Cooldown entre alertas (`cooldown_between_alerts_seconds: 10`)

## 5. Fases de Implementación

### Fase 1 — Validación del endpoint OCA y Esquema XML

| **Tarea** | **Responsable** | **Fecha** | **Estado** | **Notas** | 
| Evaluar `GetEnvioEstadoActual` | Agente IDE | 2026-10-19 | \[x\] | Descartado: devuelve `500 Missing parameter: ordenRetiro` | 
| Validar `Tracking_Pieza` por POST de formulario | Agente IDE | 2026-10-19 | \[x\] | Devuelve HTTP 200 sin requerir SOAP manual ni `ordenRetiro` | 
| Mapear nombres exactos de nodos XML de OCA | Desarrollador Principal | 2026-10-19 | \[x\] | OCA usa `<Desdcripcion_Estado>` (con typo "d"), `<Descripcion_Motivo>`, `<SUC>` y `<fecha>` | 
| Ajustar `parse_tracking_xml` al esquema real | Agente IDE | 2026-10-19 | \[x\] | Soporta `<Desdcripcion_Estado>`, `<SUC>`, `<fecha>`; conserva el orden de los `<Table>` (el último es el más reciente); concatena `Descripcion_Motivo` salvo "Sin Motivo". Test: `test_parse_tracking_xml_oca_real_schema_uses_last_table` | 

### Fase 2 — Notificaciones WhatsApp

| **Tarea** | **Responsable** | **Fecha** | **Estado** | **Notas** | 
| Activar CallMeBot y obtener API key | Usuario | 2026-10-19 | \[ \] | Agendar bot y enviar mensaje de activación | 
| `--test-whatsapp` exitoso | Usuario | 2026-10-19 | \[ \] | Probar una vez cargadas las credenciales en `.env` | 
| Validar formato del mensaje en el móvil | Usuario | 2026-10-19 | \[ \] | Verificar renderizado de Markdown y datos del paquete | 

### Fase 3 — Persistencia y detección de cambios

| **Tarea** | **Responsable** | **Fecha** | **Estado** | **Notas** | 
| Verificar creación de `data/tracker.db` | Agente IDE | 2026-10-19 | \[x\] | Tabla `shipment_events` alineada con `PRAGMA busy_timeout = 5000` | 
| Ejecutar `--once` dos veces: sin alertas duplicadas | Agente IDE | 2026-10-19 | \[x\] | Validado en tests y ejecución contra endpoint | 
| Confirmar marcado `is_delivered` al entregarse | Agente IDE | 2026-10-19 | \[x\] | Cubierto por suite de pruebas unitarias | 

### Fase 4 — Daemon y operación

| **Tarea** | **Responsable** | **Fecha** | **Estado** | **Notas** | 
| Probar `--daemon` y cierre con `Ctrl+C` | Agente / Usuario | 2026-10-19 | \[x\] | Interrupción limpia de señales validada en `test_daemon_graceful_killer`; listo para ejecución en consola | 
| Simular caída de red y verificar backoff | Agente / Usuario | 2026-10-19 | \[x\] | Validado en `test_calculate_backoff_progression` (60 s -> 120 s -> 240 s -> tope 900 s con jitter) | 
| Configurar servicio systemd | Usuario | 2026-10-21 | \[ \] | Archivo generado en `deploy/oca-tracker.service` listo para instalar | 
| Revisar logs tras 24 h | Usuario | 2026-10-22 | \[ \] | Auditoría de estabilidad en producción | 

## 6. Pruebas

* \[x\] `pytest tests/ -v` pasa completo (10 tests aprobados).

* \[x\] Mock con el XML real de `Tracking_Pieza` incluyendo el nodo `<Desdcripcion_Estado>` (con el typo nativo de OCA), `<SUC>`, `<fecha>` y selección del último nodo `<Table>` (`test_parse_tracking_xml_oca_real_schema_uses_last_table`).

* \[x\] Verificación de concurrencia multihilo en escritura SQLite con modo WAL y `PRAGMA busy_timeout = 5000` (`test_sqlite_concurrent_writes`).

* \[x\] Verificación de progresión de backoff exponencial adaptativo (60 s a 900 s con jitter) (`test_calculate_backoff_progression`).

* \[x\] Verificación de interrupción inmediata de señales POSIX con `GracefulKiller` (`test_daemon_graceful_killer`).

* \[x\] Casos borde: paquete inexistente (HTTP 200 + diffgram vacío), OCA caído, API key inválida.

* \[ \] Prueba end-to-end con un envío real en tránsito (requiere credenciales CallMeBot y número de seguimiento activo).

## 7. Riesgos

| **Riesgo** | **Probabilidad** | **Impacto** | **Mitigación** | **Responsable** | 
| Typo nativo en XML de OCA (`Desdcripcion_Estado`) | Alta | Alta | Incluir explícitamente `Desdcripcion_Estado`, `SUC` y `fecha` en el parser XML | Desarrollador Principal | 
| Rate limit de CallMeBot | Media | Baja | Pausa obligatoria de 10 segundos entre despachos sucesivos | Desarrollador Principal | 
| Caída del servicio ASMX de OCA | Media | Media | Backoff exponencial (60 s a 900 s) sin interrumpir el daemon | Desarrollador Principal | 
| Exposición de credenciales en `.env` | Baja | Alta | Permisos `chmod 600 .env` aplicados e inclusión en `.gitignore` | Agente IDE | 

## 8. Despliegue

* \[ \] Entorno virtual creado (`.venv`)

* \[x\] `.env` con permisos restringidos (`chmod 600 .env`)

* \[x\] `.env` excluido del control de versiones (`.gitignore` creado)

* \[ \] Servicio systemd habilitado y activo (`deploy/oca-tracker.service`)

* \[x\] Plan de rollback: Detener la unidad con `systemctl stop oca-tracker`, restaurar el commit estable anterior en Git y reiniciar el servicio.

## 9. Mantenimiento

| **Actividad** | **Frecuencia** | **Responsable** | 
| Revisión de logs (`journalctl -u oca-tracker`) | Semanal | Usuario | 
| Limpieza y archivo de paquetes entregados | Mensual | Usuario | 
| Respaldo de base de datos `tracker.db` | Mensual | Usuario | 
| Actualización de dependencias del entorno | Trimestral | Usuario | 

## 10. Decisiones y Notas

| **Fecha** | **Decisión / Nota** | 
| 2026-10-19 | Se descartó `GetEnvioEstadoActual` porque exige `ordenRetiro` (Error 500) y se adoptó `Tracking_Pieza` vía POST de formulario (HTTP 200). | 
| 2026-10-19 | Se eliminó el endpoint inexistente `Oep_TrackVP.asmx` y se reemplazó SOAP (`tempuri.org`) por POST directo. | 
| 2026-10-19 | Se documentó la estructura real del XML de `Tracking_Pieza`: OCA devuelve el estado bajo la etiqueta `<Desdcripcion_Estado>` (con una "d" extra por error histórico de OCA), la sucursal en `<SUC>` y la fecha en `<fecha>` minúscula. | 

## 11. Aprobación

| **Rol** | **Nombre** | **Fecha** | **Firma** | 
| Responsable técnico | Desarrollador Principal | Pendiente | Pendiente | 
| Revisor de infraestructura | Administrador de Sistemas | Pendiente | Pendiente | 
