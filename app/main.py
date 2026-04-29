from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.market.exchange import get_exchange_provider
from app.routes.health import router as health_router
from app.routes.signals import router as signals_router
from app.scheduler import BackgroundScheduler, SignalService
from app.storage.state import StateStore


@dataclass
class AppState:
    settings: Settings
    service: SignalService
    scheduler: BackgroundScheduler


app_state: AppState


@asynccontextmanager
async def lifespan(_: FastAPI):
    global app_state
    settings = get_settings()
    settings.state_path.parent.mkdir(parents=True, exist_ok=True)
    state_store = StateStore(settings.state_path)
    service = SignalService(settings=settings, exchange=get_exchange_provider(settings), state_store=state_store)
    scheduler = BackgroundScheduler(service=service, interval_seconds=settings.check_interval_seconds)
    app_state = AppState(settings=settings, service=service, scheduler=scheduler)
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(health_router)
app.include_router(signals_router)
