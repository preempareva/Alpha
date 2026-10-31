from __future__ import annotations

import importlib
import logging
import inspect
import json
import os
import time
import webbrowser
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request as URLRequest, urlopen

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from alpha_core.observability import RequestContextMiddleware
from alpha_core.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
WORKSPACE = ROOT / "tools"
PROJECTS = [
    ("knowledge", "enterprise-knowledge-assistant", "Knowledge assistant", "Search approved docs and get answers with source citations.", "⌕", "Work"),
    ("helpdesk", "ai-it-helpdesk-assistant", "IT helpdesk", "Classify a support request and prepare a reviewable ticket.", "◈", "Work"),
    ("travel", "travel-itinerary-planner", "Trip planner", "Build an itinerary from a fictional activity catalog.", "✳", "Plan"),
    ("demand", "intelligent-inventory-forecasting", "Demand forecast", "Explore demand forecasts and a temporal backtest.", "⌁", "Plan"),
    ("churn", "customer-churn-prediction", "Churn signals", "Score synthetic accounts and inspect evaluation metrics.", "↘", "Insights"),
    ("sales-forecast", "sales-pipeline-forecasting", "Sales forecast", "Estimate opportunity win probabilities for review.", "↗", "Insights"),
    ("sentiment", "customer-sentiment-intelligence", "Voice of customer", "Analyze a review and explore sentiment themes.", "◉", "Insights"),
    ("bi", "multi-agent-business-intelligence", "Business intelligence", "Ask questions against a controlled synthetic retail dataset.", "⌗", "Insights"),
    ("replenishment", "inventory-optimization-agent", "Replenishment", "Review reorder proposals and backtest results.", "▦", "Plan"),
    ("sales-nudge", "ai-sales-nudge-agent", "Sales follow-up", "Prioritize fictional leads and draft a follow-up for review.", "✉", "Work"),
    ("incidents", "ai-observability-investigator", "Incident investigator", "Correlate synthetic logs, metrics, and traces.", "⌬", "Work"),
    ("quotes", "ai-supplier-quote-comparison", "Quote comparison", "Compare supplier offers with explicit cost and quality terms.", "⇄", "Plan"),
    ("segments", "customer-segmentation-agent", "Customer segments", "Inspect aggregate RFM clusters from synthetic transactions.", "◌", "Insights"),
]
_weather_cache: dict[str, tuple[float, dict]] = {}


class WeatherRequest(BaseModel):
    destination: str = Field(min_length=2, max_length=100)


def _get_json(url: str) -> dict:
    request = URLRequest(url, headers={"User-Agent": "ProjectAlpha/1.0 (personal local travel planner)"})
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


class PrefixApiPaths(BaseHTTPMiddleware):
    """Adjust the original demo's root-relative API links inside the mounted page."""

    def __init__(self, app, slug: str):
        super().__init__(app)
        self.slug = slug

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if "text/html" not in response.headers.get("content-type", ""):
            return response
        body = b"".join([part async for part in response.body_iterator])
        prefix = f"/tools/{self.slug}/".encode()
        body = body.replace(b"href='/", b"href='" + prefix).replace(b'href="/', b'href="' + prefix)
        api_prefix = prefix + b"api/"
        body = body.replace(b"'/api/", b"'" + api_prefix).replace(b'"/api/', b'"' + api_prefix)
        headers = dict(response.headers)
        headers.pop("content-length", None)
        return HTMLResponse(body, status_code=response.status_code, headers=headers)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    async with AsyncExitStack() as stack:
        for subapp in _loaded_apps:
            await stack.enter_async_context(subapp.router.lifespan_context(subapp))
        if os.getenv("ALPHA_OPEN_BROWSER") == "1":
            webbrowser.open("http://127.0.0.1:8000")
        yield


app = FastAPI(title="Project Alpha", lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
_loaded_apps = []

for slug, folder, _title, _description, _icon, _group in PROJECTS:
    project_path = WORKSPACE / folder
    if not project_path.is_dir():
        raise RuntimeError(f"Project directory is missing: {project_path}")
    module = importlib.import_module(f"tools.{folder}.app.main")
    subapp = module.app
    subapp.add_middleware(PrefixApiPaths, slug=slug)
    _loaded_apps.append(subapp)
    app.mount(f"/tools/{slug}", subapp, name=slug)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, headers=exc.headers, content={
        "detail": exc.detail,
        "code": "http_error",
        "request_id": getattr(request.state, "request_id", None),
    })


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={
        "detail": exc.errors(),
        "code": "validation_error",
        "request_id": getattr(request.state, "request_id", None),
    })


@app.get("/health")
async def health():
    checks = []
    for (slug, *_), subapp in zip(PROJECTS, _loaded_apps):
        route = next((route for route in subapp.routes if getattr(route, "path", None) == "/health"), None)
        if route is None:
            checks.append({"id": slug, "status": "unavailable", "reason": "No health route"})
            continue
        try:
            result = route.endpoint()
            if inspect.isawaitable(result):
                result = await result
            status = result.get("status", "unknown") if isinstance(result, dict) else "unknown"
            checks.append({"id": slug, "status": status})
        except Exception as exc:
            logging.getLogger("alpha.health").exception("Health check failed for %s", slug)
            checks.append({"id": slug, "status": "error", "reason": type(exc).__name__})
    ready = len(checks) == len(PROJECTS) and all(item["status"] in {"ok", "ready", "healthy"} for item in checks)
    return {"status": "ok" if ready else "degraded", "projects": checks}


@app.get("/api/projects")
def projects():
    return [
        {"id": slug, "folder": folder, "title": title, "description": description, "icon": icon, "group": group}
        for slug, folder, title, description, icon, group in PROJECTS
    ]


@app.post("/api/travel-weather")
def travel_weather(payload: WeatherRequest):
    """Fetch current 7-day destination weather. Queries are user-triggered and cached."""
    key = payload.destination.strip().casefold()
    cached = _weather_cache.get(key)
    if cached and time.time() - cached[0] < 1800:
        return {**cached[1], "cached": True}
    try:
        geocode = _get_json("https://geocoding-api.open-meteo.com/v1/search?" + urlencode({"name": payload.destination.strip(), "count": 1, "language": "en", "format": "json"}))
        locations = geocode.get("results") or []
        if not locations:
            raise HTTPException(status_code=404, detail="No matching destination found. Add a country or region to narrow the search.")
        place = locations[0]
        forecast = _get_json("https://api.open-meteo.com/v1/forecast?" + urlencode({"latitude": place["latitude"], "longitude": place["longitude"], "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max", "forecast_days": 7, "timezone": "auto"}))
        daily = forecast.get("daily", {})
        result = {
            "destination": ", ".join(part for part in [place.get("name"), place.get("admin1"), place.get("country")] if part),
            "timezone": forecast.get("timezone"),
            "days": [{"date": day, "weather_code": daily.get("weather_code", [])[index], "max_c": daily.get("temperature_2m_max", [])[index], "min_c": daily.get("temperature_2m_min", [])[index], "precipitation_chance": daily.get("precipitation_probability_max", [])[index]} for index, day in enumerate(daily.get("time", []))],
            "source": "Open-Meteo forecast and geocoding APIs",
            "attribution": "Weather data © Open-Meteo, CC BY 4.0; location search data based on GeoNames.",
            "cached": False,
        }
        _weather_cache[key] = (time.time(), result)
        return result
    except HTTPException:
        raise
    except (URLError, TimeoutError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="The live weather service is unavailable. The rest of the itinerary can still be reviewed.") from exc


@app.get("/", response_class=HTMLResponse)
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/static/{asset}")
def static_asset(asset: str):
    if asset not in {"app.css", "app.js"}:
        raise HTTPException(status_code=404)
    return FileResponse(ROOT / "static" / asset)
