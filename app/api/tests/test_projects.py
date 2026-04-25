import json
from pathlib import Path

from fastapi.testclient import TestClient

from studio_api.main import create_app


def make_client(tmp_path: Path) -> TestClient:
    app = create_app(projects_root=tmp_path / "projects")
    return TestClient(app)


def test_health_reports_mock_adapter(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "adapter": "mock"}


def test_create_project_persists_project_and_brief(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/projects",
        json={
            "title": "Szczoteczka bohater",
            "topic": "mycie zebow",
            "age_range": "3-5",
            "emotional_tone": "radosc",
            "educational_goal": "dziecko pamieta o porannym myciu zebow",
            "characters": ["toothbrush_friend_v1"],
        },
    )

    assert response.status_code == 201
    project = response.json()
    project_id = project["id"]
    project_dir = tmp_path / "projects" / project_id

    assert project["title"] == "Szczoteczka bohater"
    assert project["pipeline"][0]["stage"] == "brief.generate"
    assert project["pipeline"][0]["status"] == "needs_review"

    saved_project = json.loads((project_dir / "project.json").read_text())
    saved_brief = json.loads((project_dir / "brief.json").read_text())
    assert saved_project["id"] == project_id
    assert saved_brief["topic"] == "mycie zebow"
    assert saved_brief["characters"] == ["toothbrush_friend_v1"]


def test_mock_server_connection_is_ready(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post("/api/server/test-connection")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "mock",
        "reachable": True,
        "message": "Mock GPU server is ready for local development.",
    }


def test_submit_mock_job_updates_pipeline_and_job_can_be_read(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowy refren",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "ciekawosc",
            "educational_goal": "dziecko rozpoznaje podstawowe kolory",
            "characters": [],
        },
    ).json()

    response = client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")

    assert response.status_code == 202
    job = response.json()
    assert job["project_id"] == created["id"]
    assert job["stage"] == "lyrics.generate"
    assert job["status"] == "needs_review"
    assert job["adapter"] == "mock"

    read_job = client.get(f"/api/jobs/{job['id']}")
    assert read_job.status_code == 200
    assert read_job.json()["id"] == job["id"]

    project = client.get(f"/api/projects/{created['id']}").json()
    lyric_stage = next(item for item in project["pipeline"] if item["stage"] == "lyrics.generate")
    assert lyric_stage["status"] == "needs_review"
    assert lyric_stage["job_id"] == job["id"]
