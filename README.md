# opentelemetry-template-python

Proyecto de ejemplo para manejar OpenTelemetry en proyectos de Python.

## Servicio DEV.to Tech News

Este repositorio contiene una API construida con FastAPI que consulta la API pública de DEV.to para recuperar las últimas noticias de tecnología. Cada consulta queda trazada con OpenTelemetry y se exporta a la consola para facilitar la observabilidad durante el desarrollo.

### Requisitos

- Python 3.11+
- Acceso a internet para consultar la API de DEV.to

### Instalación

```bash
python -m venv .venv
source .venv/bin/activate  # En Windows use `.venv\\Scripts\\activate`
pip install -r requirements.txt
```

### Ejecución

Inicie el servidor de desarrollo con Uvicorn:

```bash
uvicorn app.main:app --reload
```

Visite `http://localhost:8000/docs` para explorar la documentación interactiva generada por FastAPI.

### Observabilidad

Las trazas se envían a la consola estándar usando `ConsoleSpanExporter`. Cada petición al endpoint `/news` crea un span `devto.fetch_articles` que contiene metadatos del request realizado a DEV.to. Puede modificar fácilmente la configuración para apuntar a un backend de observabilidad diferente.
