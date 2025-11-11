# opentelemetry-template-python

Proyecto de ejemplo que expone un servicio FastAPI instrumentado con OpenTelemetry y listo para ejecutarse en contenedores de desarrollo y producción. Todas las trazas, métricas y logs generados por la aplicación se envían a un OpenTelemetry Collector mediante OTLP.

## Requisitos

- Python 3.11+
- Acceso a internet para consultar la API de DEV.to
- Un OpenTelemetry Collector accesible desde la aplicación

## Configuración de variables de entorno

Cree un archivo `.env` en la raíz del repositorio (o copie `.env.example`) y ajuste las variables según su entorno:

```bash
cp .env.example .env
```

Variables principales:

- `OTEL_COLLECTOR_URL`: URL base del OpenTelemetry Collector.
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`, `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`: rutas completas del Collector para cada señal (opcional si `OTEL_COLLECTOR_URL` está definido).
- `OTEL_EXPORTER_OTLP_HEADERS`: cabeceras personalizadas a enviar con cada petición OTLP (opcional).
- `DEVTO_API_KEY`: clave privada utilizada para autenticar las peticiones contra la API de DEV.to.
- `LOG_LEVEL`: nivel de logging de la aplicación.
- `OTEL_SERVICE_*`: metadatos opcionales del servicio expuestos en la telemetría.

## Ejecución local

```bash
python -m venv .venv
source .venv/bin/activate  # En Windows use `.venv\\Scripts\\activate`
pip install -r requirements.txt
uvicorn app.main:app --reload
```

El servicio queda disponible en `http://localhost:8000` y la documentación interactiva en `http://localhost:8000/docs`.

## Dev Container (VS Code)

El proyecto incluye la carpeta `.devcontainer/` para abrir el repositorio directamente en un contenedor de desarrollo con todas las dependencias instaladas.

1. Instale la extensión **Dev Containers** de VS Code.
2. Abra el repositorio y seleccione `Reopen in Container`.
3. Asegúrese de tener el archivo `.env` con la configuración del OpenTelemetry Collector para que el contenedor lo cargue automáticamente.

El contenedor expone el puerto 8000 para ejecutar la API y ya cuenta con las extensiones de Python configuradas.

## Ejecución en Docker

### Build y ejecución directa

```bash
docker build -t opentelemetry-template-python .
docker run --env-file .env -p 8000:8000 opentelemetry-template-python
```

### docker-compose

```bash
docker compose up --build
```

El servicio quedará escuchando en `http://localhost:8000` y utilizará la configuración declarada en el archivo `.env` para conectarse con el OpenTelemetry Collector que actúe como backend de observabilidad.

## Observabilidad con OpenTelemetry Collector

La configuración de telemetría (`app/telemetry.py`) realiza:

- **Logs**: se configura un `LoggerProvider` con un `BatchLogRecordProcessor` y el `OTLPLogExporter` para enviar los registros de la aplicación al Collector.
- **Trazas**: se define un `TracerProvider` con un `BatchSpanProcessor` y el `OTLPSpanExporter` para transmitir los spans a través de OTLP/HTTP.
- **Métricas**: se utiliza un `MeterProvider` junto a un `PeriodicExportingMetricReader` y el `OTLPMetricExporter` para remitir periódicamente las métricas al Collector.

La aplicación expone dos contadores: uno para las peticiones al endpoint `/news` y otro para el número de artículos devueltos. Estos valores se envían automáticamente al Collector.

## Endpoints principales

- `GET /health`: verificación de estado.
- `GET /news`: obtiene artículos recientes de DEV.to filtrados por etiqueta. Acepta parámetros `tag` y `per_page`.

Cada petición al endpoint `/news` genera spans y métricas que se envían al Collector, además de logs que reflejan los posibles errores durante la comunicación con DEV.to.
