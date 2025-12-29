"""FastAPI application setup for the website blocker daemon."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Website Blocker Daemon",
        description="REST API for the website blocker daemon",
        version="1.0.0"
    )

    # Add CORS middleware for local access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app
