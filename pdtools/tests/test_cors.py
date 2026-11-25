import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from pdtools import api


@pytest.fixture
def pd_server(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {
        **os.environ,
        "PD_WORK_BASE": str(tmp_path),
        "PD_ALLOWED_ORIGINS": "",
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "pdtools.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(80):
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise AssertionError(f"PD test server exited early:\n{output}")
        try:
            if httpx.get(f"{base_url}/health", timeout=0.2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        process.terminate()
        raise AssertionError("PD test server did not become ready")

    try:
        yield base_url, tmp_path
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_vite_origins_can_preflight_json_posts(pd_server, origin):
    base_url, _ = pd_server
    response = httpx.request(
        "OPTIONS",
        f"{base_url}/new_run",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_unrelated_browser_origin_is_rejected(pd_server):
    base_url, _ = pd_server
    response = httpx.request(
        "OPTIONS",
        f"{base_url}/new_run",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_actual_get_and_post_responses_include_local_cors(pd_server):
    base_url, work_base = pd_server
    headers = {"Origin": "http://localhost:5173"}

    health = httpx.get(f"{base_url}/health", headers=headers)
    created = httpx.post(f"{base_url}/new_run", headers=headers, json={"design": "top"})

    assert health.status_code == 200
    assert health.headers["access-control-allow-origin"] == headers["Origin"]
    assert created.status_code == 200
    assert created.headers["access-control-allow-origin"] == headers["Origin"]
    run_id = created.json()["run_id"]
    assert run_id
    assert (work_base / run_id / "run_meta.json").exists()


def test_configured_origins_reject_wildcards():
    with pytest.raises(ValueError, match="wildcard"):
        api.build_allowed_origins("https://team.example,*")

    assert api.build_allowed_origins("https://team.example, https://two.example") == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://team.example",
        "https://two.example",
    ]
