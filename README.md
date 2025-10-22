# opentelemetry-template-python

Proyecto de ejemplo que expone un servicio FastAPI instrumentado con OpenTelemetry y listo para ejecutarse en contenedores de desarrollo y producción. Todas las trazas, métricas y logs generados por la aplicación se persisten en MongoDB.

## Requisitos

- Python 3.11+
- Acceso a internet para consultar la API de DEV.to
- Una instancia de MongoDB accesible desde la aplicación

## Configuración de variables de entorno

Cree un archivo `.env` en la raíz del repositorio (o copie `.env.example`) y ajuste las variables según su entorno:

```bash
cp .env.example .env
```

Variables principales:

- `MONGO_URI` o `MONGO_HOST`/`MONGO_PORT`/`MONGO_USERNAME`/`MONGO_PASSWORD`: parámetros de conexión a MongoDB.
- `MONGO_DB_NAME`: base de datos utilizada para almacenar la telemetría.
- `MONGO_LOG_COLLECTION`, `MONGO_TRACE_COLLECTION`, `MONGO_METRIC_COLLECTION`: colecciones donde se guardan logs, trazas y métricas.
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
3. Asegúrese de tener el archivo `.env` con la configuración de MongoDB para que el contenedor lo cargue automáticamente.

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

El servicio quedará escuchando en `http://localhost:8000` y utilizará la configuración declarada en el archivo `.env` para conectarse a MongoDB (local o remoto).

## Observabilidad en MongoDB

La configuración de telemetría (`app/telemetry.py`) realiza:

- **Logs**: se registra un `logging.Handler` personalizado que almacena cada evento en la colección indicada.
- **Trazas**: se define un `SpanExporter` personalizado que guarda cada span con sus atributos, eventos y enlaces.
- **Métricas**: se configura un `MetricExporter` junto a un `PeriodicExportingMetricReader` para enviar periódicamente los datos de métricas a MongoDB.

La aplicación expone dos contadores: uno para las peticiones al endpoint `/news` y otro para el número de artículos devueltos. Estos valores se persisten automáticamente en la colección de métricas.

## Endpoints principales

- `GET /health`: verificación de estado.
- `GET /news`: obtiene artículos recientes de DEV.to filtrados por etiqueta. Acepta parámetros `tag` y `per_page`.

Cada petición al endpoint `/news` genera spans y métricas que se almacenan en MongoDB, además de logs que reflejan los posibles errores durante la comunicación con DEV.to.
