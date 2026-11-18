import sys
import inspect
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import api  # noqa: E402


def test_health_is_independent_of_external_services(monkeypatch):
    def unexpected_external_call(*_args, **_kwargs):
        raise AssertionError("health must not access an external dependency")

    monkeypatch.setattr(api, "_supabase", unexpected_external_call)
    monkeypatch.setattr(api, "_get_llm_client", unexpected_external_call)
    monkeypatch.setattr(api.subprocess, "run", unexpected_external_call)

    health_routes = [
        route for route in api.app.routes
        if getattr(route, "path", None) == "/health" and "GET" in getattr(route, "methods", set())
    ]
    assert len(health_routes) == 1

    result = health_routes[0].endpoint()
    if inspect.isawaitable(result):
        raise AssertionError("health endpoint should not need async I/O")
    assert result == {"status": "ok"}
