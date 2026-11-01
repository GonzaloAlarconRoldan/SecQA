from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from secqa.hub.app import create_app
from secqa.hub.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data")


@pytest.fixture
def client(settings: Settings) -> TestClient:
    c = TestClient(create_app(settings))
    c.headers["X-SecQA-Actor"] = "human:tester"
    return c


@pytest.fixture
def project(client: TestClient) -> dict:
    r = client.post("/api/projects", json={"key": "SHOP", "name": "Shop"})
    assert r.status_code == 201, r.text
    return r.json()


def start_run(client: TestClient, kind: str = "security", **extra) -> dict:
    r = client.post("/api/projects/SHOP/runs", json={"kind": kind, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def upload(client: TestClient, run_id: int, fmt: str, fixture: str, **params) -> dict:
    with (FIXTURES / fixture).open("rb") as fh:
        r = client.post(f"/api/runs/{run_id}/ingest/{fmt}", files={"file": (fixture, fh)}, params=params)
    assert r.status_code == 200, r.text
    return r.json()
