# Mock Studio MVP Design

**Goal:** Build the first local slice of AI Kids Music Studio with a Next.js operator panel, a FastAPI backend, and a mock GPU server adapter that preserves the future SSH integration boundary.

## Scope

The first MVP supports creating a production project, entering a brief, viewing pipeline stages, and running simulated generation jobs. It does not call real AI models, ComfyUI, SSH, or FFmpeg yet. Those systems are represented by a backend adapter interface so the UI and API contracts remain stable when the real GPU server is added.

## Architecture

The app is split into two local processes:

- `app/api`: FastAPI service that owns project state, filesystem persistence, pipeline status, and the mock GPU adapter.
- `app/web`: Next.js app that provides the operator cockpit.

Project data is stored under `projects/<project_id>/`. The backend writes `project.json`, `brief.json`, and mock job manifests there. This keeps the data model close to the long-term artifact layout and avoids introducing PostgreSQL before the workflow shape is known.

## Backend Contracts

The backend exposes:

- `GET /health`: backend status and active adapter mode.
- `GET /api/projects`: list local projects.
- `POST /api/projects`: create a project from title, topic, age range, emotional tone, educational goal, and optional characters.
- `GET /api/projects/{project_id}`: read project details and pipeline state.
- `GET /api/projects/{project_id}/jobs`: list all job manifests for a project in creation order.
- `POST /api/projects/{project_id}/jobs/{stage}`: submit a mock job for a pipeline stage.
- `GET /api/jobs/{job_id}`: read job status.
- `POST /api/server/test-connection`: return mock server connectivity status.

The mock adapter returns deterministic progress states quickly enough for local testing: `queued`, `running`, then `needs_review` for human-gated stages or `completed` for ungated stages.

## Frontend Experience

The first screen is the actual studio cockpit, not a marketing landing page. It includes:

- project creation form;
- project list;
- selected project detail area;
- pipeline stage board;
- mock server status;
- local server profile form for the future GPU host;
- human approval controls for stages waiting on review;
- action buttons for running mock stages.

The UI follows the requested `gpt-taste` direction for premium visual quality, but adapts it to an operational studio tool: rich, cinematic, and polished without turning the product into a generic landing page.

## Future SSH Boundary

The backend will later gain an SSH adapter with the same methods as the mock adapter:

- `test_connection()`;
- `submit_job(project, stage, manifest)`;
- `get_job(job_id)`;
- `sync_artifacts(project_id)`.

Tailscale and SSH configuration will be added after the Linux GPU server exists. The current mock adapter deliberately mirrors that boundary.

The first MVP already stores a local server profile in `projects/.studio/server-profile.json`. This profile contains only connection metadata: mode, label, host, username, port, remote root, SSH key path, and Tailscale name. It does not store passwords, private key contents, tokens, or other credentials.

Human-gated stages can be approved through `POST /api/projects/{project_id}/stages/{stage}/approve`. Approval is allowed only while a stage is in `needs_review`; otherwise the API returns a conflict. Each approval writes a review manifest under `projects/<project_id>/reviews/<stage>.approval.json`.

Pipeline execution is sequential in the MVP. A stage cannot start until the immediately previous stage is `completed`; for example, `lyrics.generate` is blocked until `brief.generate` has been approved. The UI mirrors this by disabling the lyrics action until the brief gate is complete.

The mock `lyrics.generate` stage creates a reviewable `lyrics.json` artifact in the project directory. The artifact includes song structure, chorus, verses, rhythm notes, and safety notes. The cockpit renders this artifact as a human-readable review panel before the operator approves the lyrics stage.

The mock `storyboard.generate` stage creates a reviewable `storyboard.json` artifact after the character and audio gates are complete. The artifact contains shot-by-shot scene descriptions, palette notes, camera language, and continuity constraints so the later keyframe/video stages can consume a stable creative brief. The cockpit promotes the storyboard artifact above lyrics once it exists, giving the operator the latest review target.

The mock `keyframes.generate` stage creates a reviewable `keyframes.json` artifact after storyboard approval. Each frame maps back to a storyboard scene and includes timestamp, image prompt, composition, palette, and continuity notes. The cockpit promotes keyframes above storyboard once they exist so the operator always sees the next human review surface.

The mock `video.scenes.generate` stage creates a reviewable `video-scenes.json` artifact after keyframes approval. Each clip maps back to a source keyframe and includes duration, motion prompt, camera motion, transition, and safety note. The cockpit promotes video scenes above keyframes so the review surface follows the active pipeline stage.

The mock `render.full_episode` stage creates a completed `full-episode.json` manifest after video scene approval. The manifest records slug, total duration, scene count, mock output path, poster frame, audio mix note, and assembly notes. Because this stage is not human-gated in the MVP pipeline, it completes immediately and the cockpit promotes the episode manifest as the latest artifact.

The mock `render.reels` stage creates a completed `reels.json` manifest after the full episode render. It contains three vertical short-form clips with source episode slug, source scene ids, duration, 9:16 aspect ratio, hook, mock output path, caption, safety note, and distribution guidance. This keeps the future SSH worker contract clear: full episodes and short clips are separate render outputs, but both are represented as deterministic manifests in local mock mode.

The mock `quality.compliance_report` stage creates a reviewable `compliance-report.json` artifact after reels are rendered. The report summarizes language, sensory pacing, story completion, and distribution checks, links back to the full episode and reel output paths, and records operator notes for the later real-file validation pass. Because this stage is human-gated, it remains `needs_review` until the operator approves it.

The mock `publish.prepare_package` stage creates a completed `publish-package.json` artifact after compliance approval. The package manifest records the publish folder path, episode and reel outputs, included manifests, publishing metadata, and a final operator checklist. This closes the mock pipeline with a stable handoff contract for the future real packaging worker.

The backend also exposes `GET /api/projects/{project_id}/artifacts` as a manifest inventory for the selected project. It returns the generated artifact filenames, normalized artifact types, project-relative paths, availability, and filesystem update timestamps. The cockpit renders this inventory as a compact artifact register so operators can see the full production trail while reviewing the latest artifact panel.

The backend exposes `GET /api/projects/{project_id}/jobs` as a project job ledger. It returns saved job manifests in creation order, including stage, adapter, status, message, and timestamps. The cockpit renders this as a compact history panel beside the artifact register so operators can audit what ran locally before the real SSH worker is introduced.

## Testing

Backend behavior is covered with pytest and FastAPI TestClient. The first tests verify project creation, brief persistence, mock server connection status, and mock job submission/status retrieval.

Frontend verification uses Next.js build checks plus Browser Use and Playwright against the local dev server. The first browser pass verifies the page renders, the project form can be filled, and a mock job can be triggered.
