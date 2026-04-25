# Mock Studio MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the first working local app slice for AI Kids Music Studio: Next.js operator UI, FastAPI API, filesystem project persistence, and a mock GPU server adapter.

**Architecture:** FastAPI owns project/job state and persists project artifacts under `projects/`. Next.js calls the API through a small client module and renders a premium operator cockpit. The mock GPU adapter implements the same conceptual boundary that the future SSH/Tailscale server adapter will use.

**Tech Stack:** Python 3.12, FastAPI, pytest, Next.js, TypeScript, Tailwind CSS, GSAP, Playwright, Browser Use.

---

### Task 1: Repository and Backend Test Harness

**Files:**
- Create: `.gitignore`
- Create: `app/api/requirements.txt`
- Create: `app/api/requirements-dev.txt`
- Create: `app/api/pytest.ini`
- Create: `app/api/tests/test_projects.py`

- [ ] **Step 1: Write failing API tests**

Create tests for `GET /health`, `POST /api/projects`, persisted `brief.json`, `POST /api/server/test-connection`, `POST /api/projects/{id}/jobs/{stage}`, and `GET /api/jobs/{job_id}`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app/api && python3 -m pytest -q`

Expected: FAIL because `studio_api` does not exist.

### Task 2: FastAPI Project and Mock Adapter

**Files:**
- Create: `app/api/studio_api/__init__.py`
- Create: `app/api/studio_api/models.py`
- Create: `app/api/studio_api/storage.py`
- Create: `app/api/studio_api/mock_server.py`
- Create: `app/api/studio_api/main.py`

- [ ] **Step 1: Implement minimal models and storage**

Add Pydantic models for projects, stages, and jobs. Persist projects to `projects/<project_id>/project.json` and `brief.json`.

- [ ] **Step 2: Implement mock server adapter**

Add deterministic mock connection and job creation with statuses suitable for UI testing.

- [ ] **Step 3: Implement FastAPI routes**

Wire health, project, job, and mock server endpoints.

- [ ] **Step 4: Run backend tests**

Run: `cd app/api && python3 -m pytest -q`

Expected: PASS.

### Task 3: Next.js Shell and Dependencies

**Files:**
- Create: `app/web/package.json`
- Create: `app/web/next.config.ts`
- Create: `app/web/tsconfig.json`
- Create: `app/web/postcss.config.mjs`
- Create: `app/web/app/layout.tsx`
- Create: `app/web/app/globals.css`
- Create: `app/web/app/page.tsx`
- Create: `app/web/lib/api.ts`
- Create: `app/web/playwright.config.ts`
- Create: `app/web/tests/studio.spec.ts`

- [ ] **Step 1: Add frontend package and config**

Install Next.js, React, Tailwind CSS, GSAP, lucide-react, and Playwright.

- [ ] **Step 2: Add API client**

Create typed functions for health, projects, creating projects, server connection testing, and running jobs.

- [ ] **Step 3: Add initial Playwright test**

Test that the cockpit loads, displays server status, creates a project, and can trigger a mock job.

### Task 4: `gpt-taste` Operator Cockpit UI

**Files:**
- Modify: `app/web/app/page.tsx`
- Modify: `app/web/app/globals.css`

- [ ] **Step 1: Produce `gpt-taste` design plan**

Before writing UI code, document deterministic layout/font/component/motion choices and verify hero, grid, labels, and contrast constraints.

- [ ] **Step 2: Implement UI**

Build the cockpit with project form, stage board, project list, server status, and polished motion.

- [ ] **Step 3: Run frontend checks**

Run: `cd app/web && npm run lint && npm run build`

Expected: PASS.

### Task 5: End-to-End Local Verification

**Files:**
- Modify only if verification exposes issues.

- [ ] **Step 1: Start FastAPI**

Run: `cd app/api && uvicorn studio_api.main:app --reload --port 8000`

- [ ] **Step 2: Start Next.js**

Run: `cd app/web && npm run dev -- --port 3000`

- [ ] **Step 3: Run Playwright**

Run: `cd app/web && npm run test:e2e`

Expected: PASS.

- [ ] **Step 4: Verify in Browser Use**

Open `http://localhost:3000`, inspect the UI visually, create a project, and trigger a mock job.

### Follow-up Completed: Local Server Profile

**Files:**
- Modify: `app/api/studio_api/models.py`
- Modify: `app/api/studio_api/storage.py`
- Modify: `app/api/studio_api/mock_server.py`
- Modify: `app/api/studio_api/main.py`
- Modify: `app/web/lib/api.ts`
- Modify: `app/web/app/page.tsx`
- Modify: `app/web/tests/studio.spec.ts`

- [x] Add a local server profile model for future SSH/Tailscale configuration.
- [x] Persist the profile to `projects/.studio/server-profile.json`.
- [x] Keep credential contents out of the profile.
- [x] Show and save the profile from the cockpit UI.
- [x] Make Playwright e2e use isolated ports and an isolated data directory.

### Follow-up Completed: Human Approval Gates

**Files:**
- Modify: `app/api/studio_api/models.py`
- Modify: `app/api/studio_api/storage.py`
- Modify: `app/api/studio_api/main.py`
- Modify: `app/api/tests/test_projects.py`
- Modify: `app/web/lib/api.ts`
- Modify: `app/web/app/page.tsx`
- Modify: `app/web/tests/studio.spec.ts`

- [x] Add an approval endpoint for stages in `needs_review`.
- [x] Reject approval for stages that are not waiting for review.
- [x] Persist approval manifests under `projects/<project_id>/reviews/`.
- [x] Add pipeline card approval controls in the cockpit.
- [x] Extend e2e to approve brief and lyrics stages.

### Follow-up Completed: Sequential Pipeline Guard

**Files:**
- Modify: `app/api/studio_api/main.py`
- Modify: `app/api/tests/test_projects.py`
- Modify: `app/web/app/page.tsx`
- Modify: `app/web/tests/studio.spec.ts`

- [x] Reject stage submission when the previous stage is not completed.
- [x] Require brief approval before `lyrics.generate`.
- [x] Disable the lyrics action in the UI until the brief is completed.
- [x] Verify the enabled/disabled transition in Playwright.
