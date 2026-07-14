from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from fleetpulse.auth.api import router as auth_router
from fleetpulse.shared.config import get_settings
from fleetpulse.shared.database import dispose_engine
from fleetpulse.shared.errors import APIError, api_error_handler, validation_error_handler
from fleetpulse.shared.health import router as health_router
from fleetpulse.shared.request_id import RequestIDMiddleware
from fleetpulse.vehicles.api import router as vehicle_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


settings = get_settings()
app = FastAPI(
    title="FleetPulse Intelligence API",
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
    lifespan=lifespan,
)
app.add_middleware(RequestIDMiddleware)
app.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
app.include_router(auth_router, prefix="/api/v1")
app.include_router(vehicle_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "fleetpulse-api", "status": "ok"}
