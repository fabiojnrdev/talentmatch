import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app import models  # noqa: F401  (registra tabelas no metadata)
from app.api import candidates, jobs
from app.config import get_settings
from app.db import Base, get_engine
from app.utils import new_uuid


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if get_settings().auto_create_tables:
        Base.metadata.create_all(get_engine())
    yield


app = FastAPI(title="TalentMatch AI", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    request.state.trace_id = new_uuid()
    response = await call_next(request)
    response.headers["X-Trace-Id"] = request.state.trace_id
    return response


@app.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(jobs.router)
app.include_router(candidates.router)
