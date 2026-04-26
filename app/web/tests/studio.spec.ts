import { expect, test } from "@playwright/test";

test("operator sees a server-first generation cockpit", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Studio piosenek i klipów AI" })).toBeVisible();
  await expect(page.getByText("generowanie na serwerze")).toBeVisible();
  await expect(page.getByTestId("server-generation")).toContainText("Generacja serwerowa");
  await expect(page.getByTestId("server-generation")).toContainText("Zapisz profil serwera");
  await expect(page.getByText("Mock", { exact: false })).toHaveCount(0);
  await expect(page.getByText("mock", { exact: false })).toHaveCount(0);

  await page.getByLabel("Tytuł projektu").fill("Szczoteczka bohater");
  await page.getByLabel("Temat").fill("mycie zębów");
  await page.getByLabel("Wiek").fill("3-5");
  await page.getByLabel("Emocja").fill("radość");
  await page.getByLabel("Cel edukacyjny").fill("dziecko pamięta o porannym myciu zębów");
  await page.getByLabel("Postacie").fill("toothbrush_friend_v1");
  await page.getByRole("button", { name: "Utwórz projekt" }).click();

  await expect(page.getByTestId("selected-project-title")).toContainText("Szczoteczka bohater");
  await expect(page.getByTestId("server-generation").getByRole("button", { name: "Generuj na serwerze" })).toBeDisabled();
  await expect(page.getByTestId("run-lyrics-button")).toBeDisabled();

  await expect(page.getByLabel("Nazwa profilu")).toHaveValue("Production GPU worker");
  await expect(page.getByLabel("Użytkownik SSH")).toHaveValue("daniel");
  await expect(page.getByLabel("Remote root")).toHaveValue("/home/daniel/aikiddo-worker");
});

test("operator sees primary publish package downloads", async ({ page }) => {
  const now = "2026-04-26T12:00:00+00:00";
  const project = {
    id: "project_publish",
    title: "Brush Song",
    brief: {
      id: "brief_publish",
      title: "Brush Song",
      topic: "tooth brushing",
      age_range: "3-5",
      emotional_tone: "calm",
      educational_goal: "child remembers morning brushing",
      characters: ["toothbrush_friend_v1"],
      forbidden_motifs: [],
      created_at: now
    },
    series_id: null,
    episode_spec: null,
    pipeline: [
      "brief.generate",
      "lyrics.generate",
      "characters.import_or_approve",
      "audio.generate_or_import",
      "storyboard.generate",
      "keyframes.generate",
      "video.scenes.generate",
      "render.full_episode",
      "render.reels",
      "quality.compliance_report",
      "publish.prepare_package"
    ].map((stage) => ({ stage, status: "completed", job_id: stage === "publish.prepare_package" ? "job_publish" : `job_${stage}`, updated_at: now })),
    created_at: now,
    updated_at: now
  };
  const artifacts = [
    {
      artifact_id: "publish_reel_99_mp4",
      type: "publish_reel_video",
      filename: "publish/brush-song/reels/old-reel-99.mp4",
      mime_type: "video/mp4",
      size_bytes: 1024,
      sha256: "decoydecoydecoydecoydecoydecoydecoydecoydecoydecoydecoydec0",
      storage_key: "projects/project_publish/jobs/job_publish/publish/brush-song/reels/old-reel-99.mp4",
      public: false,
      download_url: "/api/projects/project_publish/jobs/job_publish/artifacts/publish_reel_99_mp4",
      role: "technical_artifact",
      is_primary: false,
      stage: "publish.prepare_package"
    },
    {
      artifact_id: "publish_package_zip",
      type: "publish_archive",
      filename: "publish/brush-song.zip",
      mime_type: "application/zip",
      size_bytes: 5242880,
      sha256: "abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abcd",
      storage_key: "projects/project_publish/jobs/job_publish/publish/brush-song.zip",
      public: false,
      download_url: "/api/projects/project_publish/jobs/job_publish/artifacts/publish_package_zip",
      role: "publish_package_zip",
      is_primary: true,
      stage: "publish.prepare_package"
    },
    {
      artifact_id: "publish_full_episode_mp4",
      type: "publish_video",
      filename: "publish/brush-song/videos/full-episode.mp4",
      mime_type: "video/mp4",
      size_bytes: 10485760,
      sha256: "def456def456def456def456def456def456def456def456def456def456def0",
      storage_key: "projects/project_publish/jobs/job_publish/publish/brush-song/videos/full-episode.mp4",
      public: false,
      download_url: "/api/projects/project_publish/jobs/job_publish/artifacts/publish_full_episode_mp4",
      role: "full_episode_mp4",
      is_primary: true,
      stage: "publish.prepare_package"
    },
    {
      artifact_id: "publish_reel_01_mp4",
      type: "publish_reel_video",
      filename: "publish/brush-song/reels/reel-01.mp4",
      mime_type: "video/mp4",
      size_bytes: 2097152,
      sha256: "9876549876549876549876549876549876549876549876549876549876549876",
      storage_key: "projects/project_publish/jobs/job_publish/publish/brush-song/reels/reel-01.mp4",
      public: false,
      download_url: "/api/projects/project_publish/jobs/job_publish/artifacts/publish_reel_01_mp4",
      role: "vertical_reel_mp4",
      is_primary: true,
      stage: "publish.prepare_package"
    }
  ];
  const publish = {
    status: "ready",
    primary_artifacts: artifacts.filter((artifact) => artifact.is_primary),
    supporting_artifacts: artifacts.filter((artifact) => !artifact.is_primary),
    missing_roles: []
  };

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const json = (payload: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });

    if (path === "/api/projects") return json([project]);
    if (path === "/api/series") return json([]);
    if (path === "/api/server/profile") return json({ detail: "Server profile not found" }, 404);
    if (path === "/api/queue/ssh-default") return json({ adapter: "ssh", auto_dispatch: true, queued_count: 0, queued_job_ids: [], current_lock: null, current_job_id: null, oldest_queued_job_id: null });
    if (path === "/api/projects/project_publish/jobs") return json([{ id: "job_publish", project_id: "project_publish", stage: "publish.prepare_package", status: "completed", adapter: "ssh", message: "Publish package ready.", created_at: now, updated_at: now }]);
    if (path === "/api/jobs/job_publish") {
      return json({
        id: "job_publish",
        job_id: "job_publish",
        project_id: "project_publish",
        stage: "publish.prepare_package",
        status: "succeeded",
        phase: "completed",
        message: "Publish package ready.",
        adapter: "ssh",
        preview: null,
        artifacts,
        publish,
        log_url: "/api/projects/project_publish/jobs/job_publish/log",
        error: null,
        attempt_id: "attempt_publish",
        failure_reason: null,
        queue_position: 0,
        runner: null,
        created_at: now,
        started_at: now,
        finished_at: now,
        updated_at: now
      });
    }
    if (path === "/api/jobs/job_publish/events") return json([]);
    if (path === "/api/projects/project_publish/jobs/job_publish/artifacts") return json(artifacts);
    if (path === "/api/projects/project_publish/jobs/job_publish/log") return json({ job_id: "job_publish", log: "ready", lines: ["ready"] });
    if (path === "/api/projects/project_publish/artifacts/publish-package") {
      return json({
        title: "Brush Song",
        topic: "tooth brushing",
        age_range: "3-5",
        package_status: "ready",
        package_path: "publish/brush-song",
        episode_output_path: "renders/brush-song/full-episode.mp4",
        reel_output_paths: ["renders/brush-song/reel-01.mp4"],
        included_manifests: ["publish_package.json", "publish_assets_manifest.json"],
        publishing_metadata: { made_for_kids: "true" },
        operator_checklist: ["Review final files before upload."],
        created_at: now
      });
    }
    if (path === "/api/projects/project_publish/artifacts") return json([]);
    if (path === "/api/projects/project_publish/approvals") return json([]);
    if (path === "/api/projects/project_publish/next-action") return json({ action_type: "done", stage: null, label: "Done", message: "Pipeline complete.", severity: "info" });
    if (path.startsWith("/api/projects/project_publish/artifacts/")) return json({ detail: "Not found" }, 404);
    return json({ detail: "Not found" }, 404);
  });

  await page.goto("/");

  await expect(page.getByTestId("publish-package-artifact")).toBeVisible();
  await expect(page.getByTestId("publish-primary-downloads")).toContainText("Finalny ZIP");
  await expect(page.getByTestId("publish-primary-downloads")).toContainText("brush-song.zip");
  await expect(page.getByTestId("publish-primary-downloads")).toContainText("full-episode.mp4");
  await expect(page.getByTestId("publish-primary-downloads")).toContainText("reel-01.mp4");
  await expect(page.getByTestId("publish-primary-downloads")).not.toContainText("old-reel-99.mp4");
  await expect(page.getByTestId("publish-primary-downloads").getByRole("link", { name: /brush-song.zip/i })).toHaveAttribute(
    "href",
    "http://127.0.0.1:8010/api/projects/project_publish/jobs/job_publish/artifacts/publish_package_zip"
  );
});
