"""FastAPI application exposing DEV.to news with OpenTelemetry telemetry piped into MongoDB."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI, HTTPException, Query
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.telemetry import configure_telemetry

logger = logging.getLogger(__name__)

DEVTO_API_URL = "https://dev.to/api/articles"


tracer_provider, meter_provider = configure_telemetry()
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

request_counter = meter.create_counter(
    name="devto.news.requests",
    description="Number of calls to the /news endpoint",
)

article_counter = meter.create_counter(
    name="devto.news.articles_returned",
    description="Number of DEV.to articles returned to clients",
)

app = FastAPI(
    title="DEV.to Tech News API",
    description="API backend that retrieves the latest technology news from DEV.to with OpenTelemetry telemetry.",
    version="1.0.0",
)

FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)


async def _fetch_articles(tag: str, per_page: int) -> List[Dict[str, Any]]:
    params = {"tag": tag, "per_page": per_page}

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        with tracer.start_as_current_span("devto.fetch_articles") as span:
            span.set_attribute("http.method", "GET")
            span.set_attribute("http.url", DEVTO_API_URL)
            span.set_attribute("devto.tag", tag)
            span.set_attribute("devto.per_page", per_page)
            response = await client.get(DEVTO_API_URL, params=params)
            span.set_attribute("http.status_code", response.status_code)
            response.raise_for_status()

    articles: List[Dict[str, Any]] = []
    for article in response.json():
        articles.append(
            {
                "id": article.get("id"),
                "title": article.get("title"),
                "url": article.get("url"),
                "description": article.get("description"),
                "published_at": article.get("published_at"),
                "tags": article.get("tags"),
                "user": {
                    "name": article.get("user", {}).get("name"),
                    "username": article.get("user", {}).get("username"),
                },
            }
        )

    return articles


@app.get("/health", summary="API health status")
async def health() -> Dict[str, str]:
    """Simple health-check endpoint."""
    return {"status": "ok"}


@app.get(
    "/news",
    summary="Fetch technology news from DEV.to",
    response_description="A collection of recent technology articles",
)
async def get_news(
    tag: str = Query("technology", description="DEV.to tag used to filter news"),
    per_page: int = Query(5, ge=1, le=30, description="Number of articles to retrieve"),
) -> Dict[str, Any]:
    """Return recent technology news articles from DEV.to."""
    request_counter.add(1, attributes={"tag": tag})

    try:
        articles = await _fetch_articles(tag=tag, per_page=per_page)
    except httpx.HTTPStatusError as exc:  # type: ignore[unreachable]
        logger.exception("DEV.to API returned an error: %s", exc)
        raise HTTPException(status_code=exc.response.status_code, detail="Upstream error from DEV.to API") from exc
    except httpx.RequestError as exc:
        logger.exception("Failed to communicate with DEV.to API: %s", exc)
        raise HTTPException(status_code=502, detail="Unable to reach DEV.to API") from exc

    article_counter.add(len(articles), attributes={"tag": tag})

    return {"source": "DEV.to", "tag": tag, "count": len(articles), "articles": articles}
