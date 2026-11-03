"""FastAPI application entry point.  Run from backend/:  uvicorn app.main:app --reload"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import businesses, customers, documents, meta

app = FastAPI(
    title="YottaFlex KYC Onboarding Evidence System",
    version="0.5.0",
    description="Read API over the KYC evidence database. All rules (completeness, expiry, risk, "
                "anomalies) come from app/services, the same code the generator and validators use.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server
    allow_methods=["GET"],
    allow_headers=["*"],
)

for module in (meta, customers, documents, businesses):
    app.include_router(module.router, prefix="/api")
