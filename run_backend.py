#!/usr/bin/env python
"""
Entry point for running the Good Signal backend server.

Usage:
    python run_backend.py

Environment variables:
    HOST: Server host (default: 127.0.0.1)
    PORT: Server port (default: 8000)
    RELOAD: Enable auto-reload (default: false)
"""

import os
import sys


def main() -> None:
    """Run the FastAPI application with uvicorn."""
    import uvicorn

    from backend.config import get_settings

    settings = get_settings()

    # Configuration from environment or defaults
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "true").lower() in ("true", "1", "yes")

    # Use reload in debug mode if not explicitly set
    if settings.DEBUG and not os.getenv("RELOAD"):
        reload = True

    print(f"Starting Good Signal API server on {host}:{port}")
    print(f"Debug mode: {settings.DEBUG}")
    print(f"Auto-reload: {reload}")

    if settings.DEBUG:
        print(f"API docs available at: http://{host}:{port}/api/docs")

    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=settings.DEBUG,
    )


if __name__ == "__main__":
    # Ensure the project root is in the Python path
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    main()
