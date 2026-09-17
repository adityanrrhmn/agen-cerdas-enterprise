"""Endpoint harus berjalan di event loop: orchestrator membuat asyncio task dan state tidak thread-safe."""
import inspect

from fastapi.routing import APIRoute

from app.main import app


def test_semua_endpoint_async_agar_tidak_berjalan_di_threadpool():
    sync = [r.path for r in app.routes if isinstance(r, APIRoute) and not inspect.iscoroutinefunction(r.endpoint)]
    assert sync == []
