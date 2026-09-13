# src/cortex/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from cortex.api.routes import (
    override,
    simulation,
    status,
    control,
    audit,
    decisions,
    topology,
    analytics,
)
from cortex.infra.db.database import init_db
from cortex.config import CORS_ORIGINS

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Cortex API Built by Aradhya",
    version="1.0.0",
    description="Real-Time Train Operating System Backend with TEG, Modified Dijkstra, & Marey Analytics",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(topology.router)
app.include_router(analytics.router)
app.include_router(decisions.router)
app.include_router(override.router)
app.include_router(simulation.router)
app.include_router(status.router)
app.include_router(control.router)
app.include_router(audit.router)

@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok"}