# src/cortex/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from cortex.api.routes import override, simulation, status, control, audit
from cortex.infra.db.database import init_db

app = FastAPI(title="Cortex QRTOS API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()

app.include_router(override.router)
app.include_router(simulation.router)
app.include_router(status.router)
app.include_router(control.router)
app.include_router(audit.router)

@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok"}