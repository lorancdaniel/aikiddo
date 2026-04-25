import json
from pathlib import Path

from fastapi.testclient import TestClient

from studio_api.main import create_app


def make_client(tmp_path: Path) -> TestClient:
    app = create_app(projects_root=tmp_path / "projects")
    return TestClient(app)


def create_minimal_series(client: TestClient, name: str = "English Action Songs") -> dict:
    return client.post(
        "/api/series",
        json={
            "name": name,
            "target_age_min": 3,
            "target_age_max": 5,
            "primary_language": "en",
            "learning_domain": "ESL",
            "series_premise": "Short movement songs for preschool English practice.",
            "main_characters": [],
            "visual_style": "bright 2D classroom scenes",
            "music_style": "upbeat call-and-response",
            "voice_rules": "clear pronunciation",
            "safety_rules": ["no unsafe actions"],
            "forbidden_content": ["violence"],
            "made_for_kids_default": True,
        },
    ).json()


def create_project_with_episode_spec(
    client: TestClient,
    *,
    series_id: str,
    title: str,
    topic: str,
    objective: str,
    vocabulary: list[str],
) -> dict:
    project = client.post(
        "/api/projects",
        json={
            "title": title,
            "topic": topic,
            "age_range": "3-5",
            "emotional_tone": "radosc",
            "educational_goal": objective,
            "characters": [],
        },
    ).json()
    client.put(f"/api/projects/{project['id']}/series", json={"series_id": series_id})
    client.put(
        f"/api/projects/{project['id']}/episode-spec",
        json={
            "working_title": title,
            "topic": topic,
            "target_age_min": 3,
            "target_age_max": 5,
            "learning_objective": {
                "statement": objective,
                "domain": "vocabulary",
                "vocabulary_terms": vocabulary,
                "success_criteria": ["child repeats target words"],
            },
            "format": "song_video",
            "target_duration_sec": 150,
            "audience_context": "both",
            "search_keywords": [topic, "preschool song"],
            "derivative_plan": {
                "make_shorts": True,
                "make_reels": True,
                "make_parent_teacher_page": True,
                "make_lyrics_page": True,
            },
            "made_for_kids": True,
        },
    )
    client.post(f"/api/projects/{project['id']}/episode-spec/approve", json={})
    return client.get(f"/api/projects/{project['id']}").json()


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


def test_stage_catalog_exposes_display_names_without_renaming_stage_ids(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/stages/catalog")

    assert response.status_code == 200
    catalog = {item["stage"]: item for item in response.json()}
    assert catalog["render.full_episode"]["display_name"] == "Primary video"
    assert catalog["render.full_episode"]["future_stage"] == "render.primary_video"
    assert catalog["quality.compliance_report"]["display_name"] == "Safety, quality & rights review"
    assert catalog["quality.compliance_report"]["future_stage"] == "safety_quality_rights_review"


def test_series_bible_can_be_created_and_linked_to_project(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Action colors",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "energia",
            "educational_goal": "dziecko powtarza kolory po angielsku",
            "characters": [],
        },
    ).json()

    series_response = client.post(
        "/api/series",
        json={
            "name": "English Action Songs",
            "target_age_min": 3,
            "target_age_max": 5,
            "primary_language": "en",
            "secondary_language": "pl",
            "learning_domain": "ESL",
            "series_premise": "Short movement songs for preschool English practice.",
            "main_characters": [
                {
                    "name": "Mila",
                    "role": "teacher",
                    "visual_description": "Warm preschool teacher in simple bright 2D style.",
                    "personality": "calm, playful, precise",
                    "voice_notes": "clear pronunciation, medium tempo",
                }
            ],
            "visual_style": "bright 2D classroom scenes",
            "music_style": "upbeat call-and-response",
            "voice_rules": "simple words, clear pronunciation, no shouting",
            "safety_rules": ["no unsafe actions", "no fear pressure"],
            "forbidden_content": ["violence", "brand mascots", "endless-watch prompts"],
            "thumbnail_rules": "single clear action with high contrast object",
            "made_for_kids_default": True,
        },
    )

    assert series_response.status_code == 201
    series = series_response.json()
    assert series["status"] == "draft"
    assert series["name"] == "English Action Songs"

    link_response = client.put(f"/api/projects/{project['id']}/series", json={"series_id": series["id"]})

    assert link_response.status_code == 200
    linked_project = link_response.json()
    assert linked_project["series_id"] == series["id"]

    listed_series = client.get("/api/series")
    assert listed_series.status_code == 200
    assert [item["id"] for item in listed_series.json()] == [series["id"]]


def test_episode_spec_can_be_saved_approved_and_used_by_next_action(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Colors with movement",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radosc",
            "educational_goal": "dziecko rozpoznaje pięć kolorów",
            "characters": [],
        },
    ).json()
    series = client.post(
        "/api/series",
        json={
            "name": "English Action Songs",
            "target_age_min": 3,
            "target_age_max": 5,
            "primary_language": "en",
            "learning_domain": "ESL",
            "series_premise": "Short movement songs for preschool English practice.",
            "main_characters": [],
            "visual_style": "bright 2D classroom scenes",
            "music_style": "upbeat call-and-response",
            "voice_rules": "clear pronunciation",
            "safety_rules": ["no unsafe actions"],
            "forbidden_content": ["violence"],
            "made_for_kids_default": True,
        },
    ).json()

    missing_strategy_action = client.get(f"/api/projects/{project['id']}/next-action").json()
    assert missing_strategy_action["action_type"] == "define_series"
    assert missing_strategy_action["severity"] == "blocker"

    client.put(f"/api/projects/{project['id']}/series", json={"series_id": series["id"]})
    missing_spec_action = client.get(f"/api/projects/{project['id']}/next-action").json()
    assert missing_spec_action["action_type"] == "complete_episode_spec"

    spec_response = client.put(
        f"/api/projects/{project['id']}/episode-spec",
        json={
            "working_title": "Colors Action Song",
            "topic": "basic colors",
            "target_age_min": 3,
            "target_age_max": 5,
            "learning_objective": {
                "statement": "Dziecko 3-5 lat rozpoznaje i powtarza pięć kolorów po angielsku.",
                "domain": "vocabulary",
                "vocabulary_terms": ["red", "blue", "yellow", "green", "purple"],
                "success_criteria": ["child repeats five colors", "child matches colors to objects"],
            },
            "format": "song_video",
            "target_duration_sec": 150,
            "audience_context": "both",
            "search_keywords": ["colors song", "preschool ESL"],
            "hook_idea": "Children point to classroom objects while singing colors.",
            "derivative_plan": {
                "make_shorts": True,
                "make_reels": True,
                "make_parent_teacher_page": True,
                "make_lyrics_page": True,
            },
            "made_for_kids": True,
            "risk_notes": "Avoid template repetition and brand-like characters.",
        },
    )

    assert spec_response.status_code == 200
    assert spec_response.json()["approval_status"] == "draft"

    needs_approval_action = client.get(f"/api/projects/{project['id']}/next-action").json()
    assert needs_approval_action["action_type"] == "approve_episode_spec"

    approve_response = client.post(f"/api/projects/{project['id']}/episode-spec/approve", json={"note": "Cel edukacyjny jest konkretny."})
    assert approve_response.status_code == 200
    assert approve_response.json()["episode_spec"]["approval_status"] == "approved"

    check_action = client.get(f"/api/projects/{project['id']}/next-action").json()
    assert check_action["action_type"] == "run_anti_repetition_check"

    client.post(f"/api/projects/{project['id']}/anti-repetition/run")
    brief_action = client.get(f"/api/projects/{project['id']}/next-action").json()
    assert brief_action["action_type"] == "approve"
    assert brief_action["stage"] == "brief.generate"


def test_mock_server_connection_is_ready(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post("/api/server/test-connection")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "mock",
        "reachable": True,
        "message": "Mock GPU server is ready for local development.",
    }


def test_server_profile_can_be_saved_and_loaded(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    save_response = client.put(
        "/api/server/profile",
        json={
            "mode": "mock",
            "label": "GPU tower draft",
            "host": "gpu-studio.tailnet.local",
            "username": "studio",
            "port": 22,
            "remote_root": "/srv/ai-kids-studio",
            "ssh_key_path": "~/.ssh/ai_kids_studio",
            "tailscale_name": "gpu-studio",
        },
    )

    assert save_response.status_code == 200
    profile = save_response.json()
    assert profile["label"] == "GPU tower draft"
    assert profile["host"] == "gpu-studio.tailnet.local"
    assert profile["remote_root"] == "/srv/ai-kids-studio"
    assert profile["updated_at"]

    loaded_response = client.get("/api/server/profile")
    assert loaded_response.status_code == 200
    assert loaded_response.json() == profile

    config_file = tmp_path / "projects" / ".studio" / "server-profile.json"
    saved = json.loads(config_file.read_text())
    assert saved["username"] == "studio"
    assert "password" not in saved


def test_mock_connection_uses_saved_server_profile(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    client.put(
        "/api/server/profile",
        json={
            "mode": "mock",
            "label": "GPU tower draft",
            "host": "gpu-studio.tailnet.local",
            "username": "studio",
            "port": 22,
            "remote_root": "/srv/ai-kids-studio",
            "ssh_key_path": "~/.ssh/ai_kids_studio",
            "tailscale_name": "gpu-studio",
        },
    )

    response = client.post("/api/server/test-connection")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "mock",
        "reachable": True,
        "message": "Mock GPU server profile 'GPU tower draft' is ready for local development.",
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

    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})

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

    lyrics_file = tmp_path / "projects" / created["id"] / "lyrics.json"
    lyrics = json.loads(lyrics_file.read_text())
    assert lyrics["title"] == "Kolorowy refren"
    assert lyrics["chorus"]
    assert lyrics["verses"]
    assert lyrics["safety_notes"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/lyrics")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == lyrics


def test_project_jobs_can_be_listed_in_creation_order(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Historia pracy",
            "topic": "rytmy",
            "age_range": "4-6",
            "emotional_tone": "energia",
            "educational_goal": "dziecko rozpoznaje prosty rytm",
            "characters": [],
        },
    ).json()

    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    lyrics_job = client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate").json()
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    characters_job = client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve").json()

    response = client.get(f"/api/projects/{created['id']}/jobs")

    assert response.status_code == 200
    jobs = response.json()
    assert [job["id"] for job in jobs] == [lyrics_job["id"], characters_job["id"]]
    assert [job["stage"] for job in jobs] == ["lyrics.generate", "characters.import_or_approve"]
    assert [job["adapter"] for job in jobs] == ["mock", "mock"]
    assert jobs[0]["status"] == "needs_review"
    assert jobs[1]["status"] == "needs_review"


def test_project_stage_approvals_can_be_listed_in_approval_order(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Audyt akceptacji",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "spokój",
            "educational_goal": "dziecko rozpoznaje kolor czerwony",
            "characters": [],
        },
    ).json()

    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={"note": "Brief gotowy."})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={"note": "Tekst bezpieczny."})

    response = client.get(f"/api/projects/{created['id']}/approvals")

    assert response.status_code == 200
    approvals = response.json()
    assert [approval["stage"] for approval in approvals] == ["brief.generate", "lyrics.generate"]
    assert [approval["note"] for approval in approvals] == ["Brief gotowy.", "Tekst bezpieczny."]
    assert [approval["status"] for approval in approvals] == ["completed", "completed"]
    assert approvals[0]["approved_at"] <= approvals[1]["approved_at"]


def test_project_next_action_guides_operator_through_review_and_run_steps(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Następny krok",
            "topic": "liczenie",
            "age_range": "4-6",
            "emotional_tone": "ciekawość",
            "educational_goal": "dziecko liczy do trzech",
            "characters": [],
        },
    ).json()
    series = client.post(
        "/api/series",
        json={
            "name": "Counting Songs",
            "target_age_min": 4,
            "target_age_max": 6,
            "primary_language": "pl",
            "learning_domain": "math",
            "series_premise": "Songs that teach early counting through simple movement.",
            "main_characters": [],
            "visual_style": "bright simple shapes",
            "music_style": "gentle clapping rhythm",
            "voice_rules": "slow and clear",
            "safety_rules": ["no unsafe actions"],
            "forbidden_content": ["fear"],
            "made_for_kids_default": True,
        },
    ).json()
    client.put(f"/api/projects/{created['id']}/series", json={"series_id": series["id"]})
    client.put(
        f"/api/projects/{created['id']}/episode-spec",
        json={
            "working_title": "Liczymy do trzech",
            "topic": "liczenie",
            "target_age_min": 4,
            "target_age_max": 6,
            "learning_objective": {
                "statement": "Dziecko liczy do trzech i powtarza liczby w rytmie piosenki.",
                "domain": "counting",
                "vocabulary_terms": ["jeden", "dwa", "trzy"],
                "success_criteria": ["child counts to three", "child repeats each number"],
            },
            "format": "song_video",
            "target_duration_sec": 120,
            "audience_context": "both",
            "search_keywords": ["liczenie do trzech", "piosenka dla dzieci"],
            "derivative_plan": {
                "make_shorts": True,
                "make_reels": True,
                "make_parent_teacher_page": True,
                "make_lyrics_page": True,
            },
            "made_for_kids": True,
        },
    )
    client.post(f"/api/projects/{created['id']}/episode-spec/approve", json={})
    client.post(f"/api/projects/{created['id']}/anti-repetition/run")

    first_action = client.get(f"/api/projects/{created['id']}/next-action")
    assert first_action.status_code == 200
    assert first_action.json() == {
        "action_type": "approve",
        "stage": "brief.generate",
        "label": "Brief",
        "message": "Brief czeka na akceptację operatora.",
        "severity": "info",
    }

    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    second_action = client.get(f"/api/projects/{created['id']}/next-action")
    assert second_action.status_code == 200
    assert second_action.json() == {
        "action_type": "run",
        "stage": "lyrics.generate",
        "label": "Tekst",
        "message": "Możesz uruchomić etap Tekst.",
        "severity": "info",
    }

    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    third_action = client.get(f"/api/projects/{created['id']}/next-action")
    assert third_action.status_code == 200
    assert third_action.json() == {
        "action_type": "approve",
        "stage": "lyrics.generate",
        "label": "Tekst",
        "message": "Tekst czeka na akceptację operatora.",
        "severity": "info",
    }


def test_cannot_start_stage_when_previous_review_gate_is_unapproved(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Zablokowany tekst",
            "topic": "mycie rąk",
            "age_range": "3-5",
            "emotional_tone": "spokoj",
            "educational_goal": "dziecko pamięta o myciu rąk",
            "characters": [],
        },
    ).json()

    response = client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")

    assert response.status_code == 409
    assert response.json()["detail"] == "Previous stage brief.generate must be completed first"


def test_storyboard_job_writes_reviewable_storyboard_artifact(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")

    response = client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")

    assert response.status_code == 202
    job = response.json()
    assert job["stage"] == "storyboard.generate"
    assert job["status"] == "needs_review"

    storyboard_file = tmp_path / "projects" / created["id"] / "storyboard.json"
    storyboard = json.loads(storyboard_file.read_text())
    assert storyboard["title"] == "Kolorowa przygoda"
    assert len(storyboard["scenes"]) == 4
    assert storyboard["scenes"][0]["visual_prompt"]
    assert storyboard["safety_checks"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/storyboard")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == storyboard

    project = client.get(f"/api/projects/{created['id']}").json()
    stage = next(item for item in project["pipeline"] if item["stage"] == "storyboard.generate")
    assert stage["status"] == "needs_review"
    assert stage["job_id"] == job["id"]


def test_keyframes_job_writes_reviewable_keyframe_artifact(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")
    client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")
    client.post(f"/api/projects/{created['id']}/stages/storyboard.generate/approve", json={})

    response = client.post(f"/api/projects/{created['id']}/jobs/keyframes.generate")

    assert response.status_code == 202
    job = response.json()
    assert job["stage"] == "keyframes.generate"
    assert job["status"] == "needs_review"

    keyframes_file = tmp_path / "projects" / created["id"] / "keyframes.json"
    keyframes = json.loads(keyframes_file.read_text())
    assert keyframes["title"] == "Kolorowa przygoda"
    assert len(keyframes["frames"]) == 4
    assert keyframes["frames"][0]["scene_id"] == "scene_01_opening"
    assert keyframes["frames"][0]["image_prompt"]
    assert keyframes["consistency_notes"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/keyframes")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == keyframes

    project = client.get(f"/api/projects/{created['id']}").json()
    stage = next(item for item in project["pipeline"] if item["stage"] == "keyframes.generate")
    assert stage["status"] == "needs_review"
    assert stage["job_id"] == job["id"]


def test_video_scenes_job_writes_reviewable_video_scenes_artifact(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")
    client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")
    client.post(f"/api/projects/{created['id']}/stages/storyboard.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/keyframes.generate")
    client.post(f"/api/projects/{created['id']}/stages/keyframes.generate/approve", json={})

    response = client.post(f"/api/projects/{created['id']}/jobs/video.scenes.generate")

    assert response.status_code == 202
    job = response.json()
    assert job["stage"] == "video.scenes.generate"
    assert job["status"] == "needs_review"

    video_scenes_file = tmp_path / "projects" / created["id"] / "video-scenes.json"
    video_scenes = json.loads(video_scenes_file.read_text())
    assert video_scenes["title"] == "Kolorowa przygoda"
    assert len(video_scenes["scenes"]) == 4
    assert video_scenes["scenes"][0]["source_keyframe_id"] == "keyframe_01"
    assert video_scenes["scenes"][0]["motion_prompt"]
    assert video_scenes["render_notes"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/video-scenes")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == video_scenes

    project = client.get(f"/api/projects/{created['id']}").json()
    stage = next(item for item in project["pipeline"] if item["stage"] == "video.scenes.generate")
    assert stage["status"] == "needs_review"
    assert stage["job_id"] == job["id"]


def test_full_episode_render_writes_completed_episode_artifact(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")
    client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")
    client.post(f"/api/projects/{created['id']}/stages/storyboard.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/keyframes.generate")
    client.post(f"/api/projects/{created['id']}/stages/keyframes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/video.scenes.generate")
    client.post(f"/api/projects/{created['id']}/stages/video.scenes.generate/approve", json={})

    response = client.post(f"/api/projects/{created['id']}/jobs/render.full_episode")

    assert response.status_code == 202
    job = response.json()
    assert job["stage"] == "render.full_episode"
    assert job["status"] == "completed"

    episode_file = tmp_path / "projects" / created["id"] / "full-episode.json"
    episode = json.loads(episode_file.read_text())
    assert episode["title"] == "Kolorowa przygoda"
    assert episode["episode_slug"] == "kolorowa-przygoda"
    assert episode["duration_seconds"] == 44
    assert episode["scene_count"] == 4
    assert episode["assembly_notes"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/full-episode")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == episode

    project = client.get(f"/api/projects/{created['id']}").json()
    stage = next(item for item in project["pipeline"] if item["stage"] == "render.full_episode")
    assert stage["status"] == "completed"
    assert stage["job_id"] == job["id"]


def test_reels_render_writes_completed_reels_artifact(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")
    client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")
    client.post(f"/api/projects/{created['id']}/stages/storyboard.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/keyframes.generate")
    client.post(f"/api/projects/{created['id']}/stages/keyframes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/video.scenes.generate")
    client.post(f"/api/projects/{created['id']}/stages/video.scenes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/render.full_episode")

    response = client.post(f"/api/projects/{created['id']}/jobs/render.reels")

    assert response.status_code == 202
    job = response.json()
    assert job["stage"] == "render.reels"
    assert job["status"] == "completed"

    reels_file = tmp_path / "projects" / created["id"] / "reels.json"
    reels = json.loads(reels_file.read_text())
    assert reels["title"] == "Kolorowa przygoda"
    assert len(reels["reels"]) == 3
    assert reels["reels"][0]["aspect_ratio"] == "9:16"
    assert reels["reels"][0]["output_path"].endswith("reel-01.mp4")
    assert reels["distribution_notes"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/reels")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == reels

    project = client.get(f"/api/projects/{created['id']}").json()
    stage = next(item for item in project["pipeline"] if item["stage"] == "render.reels")
    assert stage["status"] == "completed"
    assert stage["job_id"] == job["id"]


def test_compliance_report_writes_reviewable_quality_artifact(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")
    client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")
    client.post(f"/api/projects/{created['id']}/stages/storyboard.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/keyframes.generate")
    client.post(f"/api/projects/{created['id']}/stages/keyframes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/video.scenes.generate")
    client.post(f"/api/projects/{created['id']}/stages/video.scenes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/render.full_episode")
    client.post(f"/api/projects/{created['id']}/jobs/render.reels")

    response = client.post(f"/api/projects/{created['id']}/jobs/quality.compliance_report")

    assert response.status_code == 202
    job = response.json()
    assert job["stage"] == "quality.compliance_report"
    assert job["status"] == "needs_review"

    compliance_file = tmp_path / "projects" / created["id"] / "compliance-report.json"
    report = json.loads(compliance_file.read_text())
    assert report["title"] == "Kolorowa przygoda"
    assert report["overall_status"] == "ready_for_human_review"
    assert len(report["checks"]) >= 4
    assert report["checks"][0]["status"] == "pass"
    assert report["episode_output_path"].endswith("full-episode.mp4")
    assert report["reel_output_paths"][0].endswith("reel-01.mp4")
    assert report["operator_notes"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/compliance-report")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == report

    project = client.get(f"/api/projects/{created['id']}").json()
    stage = next(item for item in project["pipeline"] if item["stage"] == "quality.compliance_report")
    assert stage["status"] == "needs_review"
    assert stage["job_id"] == job["id"]


def test_publish_prepare_package_writes_completed_package_manifest(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")
    client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")
    client.post(f"/api/projects/{created['id']}/stages/storyboard.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/keyframes.generate")
    client.post(f"/api/projects/{created['id']}/stages/keyframes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/video.scenes.generate")
    client.post(f"/api/projects/{created['id']}/stages/video.scenes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/render.full_episode")
    client.post(f"/api/projects/{created['id']}/jobs/render.reels")
    client.post(f"/api/projects/{created['id']}/jobs/quality.compliance_report")
    client.post(f"/api/projects/{created['id']}/stages/quality.compliance_report/approve", json={})

    response = client.post(f"/api/projects/{created['id']}/jobs/publish.prepare_package")

    assert response.status_code == 202
    job = response.json()
    assert job["stage"] == "publish.prepare_package"
    assert job["status"] == "completed"

    package_file = tmp_path / "projects" / created["id"] / "publish-package.json"
    package = json.loads(package_file.read_text())
    assert package["title"] == "Kolorowa przygoda"
    assert package["package_status"] == "ready"
    assert package["package_path"].endswith("publish/kolorowa-przygoda")
    assert package["episode_output_path"].endswith("full-episode.mp4")
    assert package["reel_output_paths"][0].endswith("reel-01.mp4")
    assert "compliance-report.json" in package["included_manifests"]
    assert package["publishing_metadata"]["audience"] == "3-5"
    assert package["operator_checklist"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/publish-package")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == package

    project = client.get(f"/api/projects/{created['id']}").json()
    stage = next(item for item in project["pipeline"] if item["stage"] == "publish.prepare_package")
    assert stage["status"] == "completed"
    assert stage["job_id"] == job["id"]


def test_anti_repetition_report_flags_similar_project_in_same_series(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    series = create_minimal_series(client)
    first = create_project_with_episode_spec(
        client,
        series_id=series["id"],
        title="Colors Action Song",
        topic="basic colors",
        objective="Dziecko 3-5 lat rozpoznaje i powtarza pięć kolorów po angielsku.",
        vocabulary=["red", "blue", "yellow", "green", "purple"],
    )
    second = create_project_with_episode_spec(
        client,
        series_id=series["id"],
        title="Colors Action Song",
        topic="basic colors",
        objective="Dziecko 3-5 lat rozpoznaje i powtarza pięć kolorów po angielsku.",
        vocabulary=["red", "blue", "yellow", "green", "purple"],
    )

    response = client.post(f"/api/projects/{second['id']}/anti-repetition/run")

    assert response.status_code == 200
    report = response.json()
    assert report["project_id"] == second["id"]
    assert report["series_id"] == series["id"]
    assert report["status"] == "blocker"
    assert report["score"] >= 0.7
    assert report["compared_projects_count"] == 1
    assert report["closest_matches"][0]["project_id"] == first["id"]
    assert "similar title" in report["closest_matches"][0]["reasons"]

    saved_response = client.get(f"/api/projects/{second['id']}/anti-repetition")
    assert saved_response.status_code == 200
    assert saved_response.json()["id"] == report["id"]


def test_anti_repetition_ignores_projects_from_other_series(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    first_series = create_minimal_series(client, "Colors Songs")
    second_series = create_minimal_series(client, "Routine Songs")
    create_project_with_episode_spec(
        client,
        series_id=first_series["id"],
        title="Colors Action Song",
        topic="basic colors",
        objective="Dziecko 3-5 lat rozpoznaje i powtarza pięć kolorów po angielsku.",
        vocabulary=["red", "blue", "yellow", "green", "purple"],
    )
    second = create_project_with_episode_spec(
        client,
        series_id=second_series["id"],
        title="Colors Action Song",
        topic="basic colors",
        objective="Dziecko 3-5 lat rozpoznaje i powtarza pięć kolorów po angielsku.",
        vocabulary=["red", "blue", "yellow", "green", "purple"],
    )

    response = client.post(f"/api/projects/{second['id']}/anti-repetition/run")

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "ok"
    assert report["score"] == 0
    assert report["compared_projects_count"] == 0
    assert report["closest_matches"] == []


def test_next_action_surfaces_anti_repetition_blocker_before_pipeline_run(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    series = create_minimal_series(client)
    create_project_with_episode_spec(
        client,
        series_id=series["id"],
        title="Colors Action Song",
        topic="basic colors",
        objective="Dziecko 3-5 lat rozpoznaje i powtarza pięć kolorów po angielsku.",
        vocabulary=["red", "blue", "yellow", "green", "purple"],
    )
    second = create_project_with_episode_spec(
        client,
        series_id=series["id"],
        title="Colors Action Song",
        topic="basic colors",
        objective="Dziecko 3-5 lat rozpoznaje i powtarza pięć kolorów po angielsku.",
        vocabulary=["red", "blue", "yellow", "green", "purple"],
    )

    missing_report_action = client.get(f"/api/projects/{second['id']}/next-action").json()
    assert missing_report_action["action_type"] == "run_anti_repetition_check"

    client.post(f"/api/projects/{second['id']}/anti-repetition/run")
    blocker_action = client.get(f"/api/projects/{second['id']}/next-action").json()

    assert blocker_action["action_type"] == "fix_repetition_risk"
    assert blocker_action["severity"] == "blocker"
    assert "zbyt podobny" in blocker_action["message"]


def test_artifact_inventory_lists_project_manifest_files(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")
    client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")
    client.post(f"/api/projects/{created['id']}/stages/storyboard.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/keyframes.generate")
    client.post(f"/api/projects/{created['id']}/stages/keyframes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/video.scenes.generate")
    client.post(f"/api/projects/{created['id']}/stages/video.scenes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/render.full_episode")
    client.post(f"/api/projects/{created['id']}/jobs/render.reels")
    client.post(f"/api/projects/{created['id']}/jobs/quality.compliance_report")
    client.post(f"/api/projects/{created['id']}/stages/quality.compliance_report/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/publish.prepare_package")

    response = client.get(f"/api/projects/{created['id']}/artifacts")

    assert response.status_code == 200
    inventory = response.json()
    filenames = [item["file_name"] for item in inventory]
    assert filenames == [
        "brief.json",
        "lyrics.json",
        "storyboard.json",
        "keyframes.json",
        "video-scenes.json",
        "full-episode.json",
        "reels.json",
        "compliance-report.json",
        "publish-package.json",
    ]
    publish_item = next(item for item in inventory if item["file_name"] == "publish-package.json")
    assert publish_item["artifact_type"] == "publish_package"
    assert publish_item["available"] is True
    assert publish_item["relative_path"].endswith("publish-package.json")


def test_approve_review_stage_marks_it_completed_and_writes_review(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Zatwierdzany brief",
            "topic": "sprzatanie zabawek",
            "age_range": "3-5",
            "emotional_tone": "spokoj",
            "educational_goal": "dziecko odkłada zabawki po zabawie",
            "characters": [],
        },
    ).json()

    response = client.post(
        f"/api/projects/{created['id']}/stages/brief.generate/approve",
        json={"note": "Brief jest bezpieczny i gotowy do tekstu."},
    )

    assert response.status_code == 200
    project = response.json()
    brief_stage = next(item for item in project["pipeline"] if item["stage"] == "brief.generate")
    assert brief_stage["status"] == "completed"

    review_file = tmp_path / "projects" / created["id"] / "reviews" / "brief.generate.approval.json"
    review = json.loads(review_file.read_text())
    assert review["stage"] == "brief.generate"
    assert review["status"] == "completed"
    assert review["note"] == "Brief jest bezpieczny i gotowy do tekstu."


def test_cannot_approve_stage_that_is_not_waiting_for_review(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Za wczesna akceptacja",
            "topic": "liczenie",
            "age_range": "3-5",
            "emotional_tone": "ciekawosc",
            "educational_goal": "dziecko liczy do pięciu",
            "characters": [],
        },
    ).json()

    response = client.post(f"/api/projects/{created['id']}/stages/audio.generate_or_import/approve", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == "Stage is not waiting for review"
