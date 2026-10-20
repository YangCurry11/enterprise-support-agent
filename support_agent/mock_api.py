"""Compatibility entry point; all routes now use the authenticated application."""
from .app import app

__all__ = ["app"]
