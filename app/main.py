from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import ai, dashboard, products, search


app = FastAPI(
    title="WFX AI ERP Assistant API",
    description="AI-native ERP APIs for apparel business data.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(search.router, prefix="/api/search", tags=["search"])


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "WFX AI ERP Assistant API",
        "status": "ready",
        "version": "0.1.0",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
