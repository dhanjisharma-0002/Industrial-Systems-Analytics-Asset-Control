"""Vercel entrypoint for the ISAAC FastAPI application."""

from backend.app.main import app

__all__ = ["app"]
