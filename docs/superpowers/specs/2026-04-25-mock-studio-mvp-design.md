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

## Testing

Backend behavior is covered with pytest and FastAPI TestClient. The first tests verify project creation, brief persistence, mock server connection status, and mock job submission/status retrieval.

Frontend verification uses Next.js build checks plus Browser Use and Playwright against the local dev server. The first browser pass verifies the page renders, the project form can be filled, and a mock job can be triggered.
