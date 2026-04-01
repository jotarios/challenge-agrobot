"""FastAPI application factory."""

from fastapi import FastAPI

from src.api.middleware.rate_limit import RateLimitMiddleware
from src.api.routers import auth, dashboard, health, metric_types, rule_groups, rules


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agrobot",
        description="Weather notification system",
        version="0.1.0",
    )

    app.add_middleware(RateLimitMiddleware)

    app.include_router(auth.router)
    app.include_router(rules.router)
    app.include_router(rule_groups.router)
    app.include_router(metric_types.router)
    app.include_router(health.router)
    app.include_router(dashboard.router)

    return app


app = create_app()
