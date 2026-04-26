export type StageStatus = "pending" | "queued" | "running" | "needs_review" | "completed" | "failed" | "cancelled";

export type PipelineStage = {
  stage: string;
  status: StageStatus;
  job_id: string | null;
  updated_at: string;
};

export type Brief = {
  id: string;
  title: string;
  topic: string;
  age_range: string;
  emotional_tone: string;
  educational_goal: string;
  characters: string[];
  created_at: string;
  forbidden_motifs: string[];
};

export type Project = {
  id: string;
  title: string;
  brief: Brief;
  series_id: string | null;
  episode_spec: EpisodeSpec | null;
  pipeline: PipelineStage[];
  created_at: string;
  updated_at: string;
};

export type Job = {
  id: string;
  project_id: string;
  stage: string;
  status: StageStatus;
  adapter: "mock" | "ssh";
  message: string;
  created_at: string;
  updated_at: string;
};

export type StageApproval = {
  id: string;
  project_id: string;
  stage: string;
  status: "completed";
  note: string;
  approved_at: string;
};

export type ProjectNextAction = {
  action_type:
    | "approve"
    | "run"
    | "done"
    | "define_series"
    | "complete_episode_spec"
    | "approve_episode_spec"
    | "run_anti_repetition_check"
    | "fix_rejected_stage"
    | "fix_repetition_risk"
    | "complete_publish_package"
    | "enter_performance_metrics";
  stage: string | null;
  label: string;
  message: string;
  severity: "info" | "warning" | "blocker";
};

export type StageCatalogItem = {
  stage: string;
  label: string;
  display_name: string;
  future_stage: string;
  description: string;
};

export type SeriesCharacter = {
  name: string;
  role: string;
  visual_description: string;
  personality: string;
  voice_notes: string;
};

export type SeriesBibleInput = {
  name: string;
  status?: "draft" | "active" | "archived";
  target_age_min: number;
  target_age_max: number;
  primary_language: string;
  secondary_language?: string | null;
  learning_domain: string;
  series_premise: string;
  main_characters: SeriesCharacter[];
  visual_style: string;
  music_style: string;
  voice_rules: string;
  safety_rules: string[];
  forbidden_content: string[];
  thumbnail_rules?: string;
  made_for_kids_default: boolean;
};

export type SeriesBible = SeriesBibleInput & {
  id: string;
  status: "draft" | "active" | "archived";
  created_at: string;
  updated_at: string;
};

export type LearningObjective = {
  statement: string;
  domain: string;
  vocabulary_terms: string[];
  success_criteria: string[];
};

export type DerivativePlan = {
  make_shorts: boolean;
  make_reels: boolean;
  make_parent_teacher_page: boolean;
  make_lyrics_page: boolean;
};

export type EpisodeSpecInput = {
  working_title: string;
  topic: string;
  target_age_min?: number | null;
  target_age_max?: number | null;
  learning_objective: LearningObjective;
  format: "song_video" | "short" | "compilation_seed" | "lesson_clip";
  target_duration_sec: number;
  audience_context: "home" | "classroom" | "both";
  search_keywords: string[];
  hook_idea?: string;
  derivative_plan: DerivativePlan;
  made_for_kids: boolean;
  risk_notes?: string;
};

export type EpisodeSpec = EpisodeSpecInput & {
  project_id: string;
  series_id: string | null;
  approval_status: "draft" | "approved" | "needs_changes";
  approved_at: string | null;
  approved_by: string | null;
  approval_note: string;
  created_at: string;
  updated_at: string;
};

export type AntiRepetitionReport = {
  id: string;
  project_id: string;
  series_id: string | null;
  status: "ok" | "warning" | "review_recommended" | "blocker";
  score: number;
  compared_projects_count: number;
  closest_matches: {
    project_id: string;
    title: string;
    score: number;
    reasons: string[];
  }[];
  signals: {
    title_similarity: number | null;
    topic_similarity: number | null;
    objective_similarity: number | null;
    vocabulary_overlap: number | null;
    lyrics_similarity: number | null;
    storyboard_similarity: number | null;
  };
  generated_at: string;
};

export type ServerConnection = {
  mode: "mock" | "ssh";
  reachable: boolean;
  message: string;
};

export type ServerProfile = {
  mode: "mock" | "ssh";
  label: string;
  host: string;
  username: string;
  port: number;
  remote_root: string;
  ssh_key_path: string;
  tailscale_name: string;
  updated_at: string;
};

export type ServerProfileInput = Omit<ServerProfile, "updated_at">;

export type GenerationArtifact = {
  artifact_id: string;
  type: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  storage_key: string;
  public: boolean;
};

export type GenerationArtifactView = GenerationArtifact & {
  download_url: string;
  role: string;
  is_primary: boolean;
  stage: string | null;
};

export type PublishJobSummary = {
  status: "ready" | "missing" | "incomplete";
  primary_artifacts: GenerationArtifactView[];
  supporting_artifacts: GenerationArtifactView[];
  missing_roles: string[];
};

export type GenerationPreview = {
  title: string;
  lyrics: string;
  song_plan: Record<string, unknown>;
  safety_notes: string[];
};

export type GenerationJobDetail = {
  id: string;
  job_id: string;
  project_id: string;
  stage: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  phase: string;
  message: string;
  adapter: "mock" | "ssh";
  preview: GenerationPreview | null;
  artifacts: GenerationArtifactView[];
  publish: PublishJobSummary | null;
  log_url: string | null;
  error: { code: string; message: string } | null;
  attempt_id: string | null;
  failure_reason: string | null;
  queue_position: number;
  runner: {
    mode: "single_flight";
    resource: string;
    state: "waiting" | "acquired" | "released";
    auto_dispatch: boolean;
    trigger: "manual" | "auto_drain" | null;
    lock_id: string | null;
    attempt_id: string | null;
    heartbeat_at: string | null;
    lease_expires_at: string | null;
  } | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
};

export type JobRetryResult = {
  retried_from_job_id: string;
  job: GenerationJobDetail;
};

export type JobEvent = {
  cursor: number;
  job_id: string;
  event: string;
  message: string;
  created_at: string;
};

export type WorkerQueueStatus = {
  resource: string;
  adapter: "ssh";
  auto_dispatch: boolean;
  queued_count: number;
  queued_job_ids: string[];
  current_lock: {
    lock_id: string;
    resource_key: string;
    adapter: "ssh";
    job_id: string;
    attempt_id: string | null;
    acquired_at: string;
    heartbeat_at: string;
    lease_expires_at: string;
  } | null;
  current_job_id: string | null;
  oldest_queued_job_id: string | null;
};

export type LockHeartbeatResult = {
  status: "renewed" | "rejected";
  reason: string | null;
  heartbeat_at: string | null;
  lease_expires_at: string | null;
};

export type StaleLockRecoveryResult = {
  status: "recovered" | "idle";
  reason: string | null;
  recovered_job_id: string | null;
  previous_status: string | null;
  new_status: string | null;
  failure_reason: string | null;
  released_lock_id: string | null;
  dispatched_next: {
    status: "dispatched" | "idle";
    reason: string | null;
    job_id: string | null;
  } | null;
};

export type JobLog = {
  job_id: string;
  log: string;
  lines: string[];
};

export type LyricsArtifact = {
  title: string;
  topic: string;
  age_range: string;
  structure: string[];
  chorus: string[];
  verses: string[][];
  rhythm_notes: string[];
  safety_notes: string[];
  created_at: string;
};

export type StoryboardScene = {
  id: string;
  duration_seconds: number;
  lyric_anchor: string;
  action: string;
  visual_prompt: string;
  camera: string;
  safety_note: string;
};

export type StoryboardArtifact = {
  title: string;
  topic: string;
  age_range: string;
  scenes: StoryboardScene[];
  safety_checks: string[];
  created_at: string;
};

export type KeyframeFrame = {
  id: string;
  scene_id: string;
  timestamp_seconds: number;
  image_prompt: string;
  composition: string;
  palette: string[];
  continuity_note: string;
};

export type KeyframesArtifact = {
  title: string;
  topic: string;
  age_range: string;
  frames: KeyframeFrame[];
  consistency_notes: string[];
  created_at: string;
};

export type VideoSceneClip = {
  id: string;
  scene_id: string;
  source_keyframe_id: string;
  duration_seconds: number;
  motion_prompt: string;
  camera_motion: string;
  transition: string;
  safety_note: string;
};

export type VideoScenesArtifact = {
  title: string;
  topic: string;
  age_range: string;
  scenes: VideoSceneClip[];
  render_notes: string[];
  created_at: string;
};

export type FullEpisodeArtifact = {
  title: string;
  topic: string;
  age_range: string;
  episode_slug: string;
  duration_seconds: number;
  scene_count: number;
  output_path: string;
  poster_frame: string;
  audio_mix: string;
  assembly_notes: string[];
  created_at: string;
};

export type ReelClip = {
  id: string;
  source_episode_slug: string;
  source_scene_ids: string[];
  duration_seconds: number;
  aspect_ratio: string;
  hook: string;
  output_path: string;
  caption: string;
  safety_note: string;
};

export type ReelsArtifact = {
  title: string;
  topic: string;
  age_range: string;
  reels: ReelClip[];
  distribution_notes: string[];
  created_at: string;
};

export type ComplianceCheck = {
  id: string;
  label: string;
  status: "pass" | "review";
  evidence: string;
};

export type ComplianceReportArtifact = {
  title: string;
  topic: string;
  age_range: string;
  overall_status: "ready_for_human_review";
  episode_output_path: string;
  reel_output_paths: string[];
  checks: ComplianceCheck[];
  operator_notes: string[];
  created_at: string;
};

export type PublishPackageArtifact = {
  title: string;
  topic: string;
  age_range: string;
  package_status: "ready";
  package_path: string;
  episode_output_path: string;
  reel_output_paths: string[];
  included_manifests: string[];
  publishing_metadata: Record<string, string>;
  operator_checklist: string[];
  created_at: string;
};

export type ArtifactInventoryItem = {
  artifact_type: string;
  file_name: string;
  relative_path: string;
  available: boolean;
  updated_at: string | null;
};

export type ProjectInput = {
  title: string;
  topic: string;
  age_range: string;
  emotional_tone: string;
  educational_goal: string;
  characters: string[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export function buildApiUrl(path: string) {
  return `${API_URL}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers
    }
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function fetchProjects() {
  return request<Project[]>("/api/projects");
}

export function fetchStageCatalog() {
  return request<StageCatalogItem[]>("/api/stages/catalog");
}

export function fetchSeries() {
  return request<SeriesBible[]>("/api/series");
}

export function createSeries(input: SeriesBibleInput) {
  return request<SeriesBible>("/api/series", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function linkProjectSeries(projectId: string, seriesId: string) {
  return request<Project>(`/api/projects/${projectId}/series`, {
    method: "PUT",
    body: JSON.stringify({ series_id: seriesId })
  });
}

export function saveEpisodeSpec(projectId: string, input: EpisodeSpecInput) {
  return request<EpisodeSpec>(`/api/projects/${projectId}/episode-spec`, {
    method: "PUT",
    body: JSON.stringify(input)
  });
}

export function approveEpisodeSpec(projectId: string, note = "") {
  return request<Project>(`/api/projects/${projectId}/episode-spec/approve`, {
    method: "POST",
    body: JSON.stringify({ note })
  });
}

export function fetchAntiRepetitionReport(projectId: string) {
  return request<AntiRepetitionReport>(`/api/projects/${projectId}/anti-repetition`);
}

export function runAntiRepetition(projectId: string) {
  return request<AntiRepetitionReport>(`/api/projects/${projectId}/anti-repetition/run`, {
    method: "POST"
  });
}

export function fetchProjectJobs(projectId: string) {
  return request<Job[]>(`/api/projects/${projectId}/jobs`);
}

export function fetchProjectApprovals(projectId: string) {
  return request<StageApproval[]>(`/api/projects/${projectId}/approvals`);
}

export function fetchProjectNextAction(projectId: string) {
  return request<ProjectNextAction>(`/api/projects/${projectId}/next-action`);
}

export function createProject(input: ProjectInput) {
  return request<Project>("/api/projects", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function testServerConnection() {
  return request<ServerConnection>("/api/server/test-connection", {
    method: "POST"
  });
}

export function fetchServerProfile() {
  return request<ServerProfile>("/api/server/profile");
}

export function saveServerProfile(input: ServerProfileInput) {
  return request<ServerProfile>("/api/server/profile", {
    method: "PUT",
    body: JSON.stringify(input)
  });
}

export function fetchJobDetail(jobId: string) {
  return request<GenerationJobDetail>(`/api/jobs/${jobId}`);
}

export function cancelJob(jobId: string) {
  return request<GenerationJobDetail>(`/api/jobs/${jobId}/cancel`, {
    method: "POST"
  });
}

export function retryJob(jobId: string) {
  return request<JobRetryResult>(`/api/jobs/${jobId}/retry`, {
    method: "POST"
  });
}

export function fetchJobEvents(jobId: string, after = 0) {
  return request<JobEvent[]>(`/api/jobs/${jobId}/events?after=${after}`);
}

export function fetchSshQueueStatus() {
  return request<WorkerQueueStatus>("/api/queue/ssh-default");
}

export function heartbeatJobLock(input: { job_id: string; lock_id: string; attempt_id: string | null; resource_key?: string }) {
  return request<LockHeartbeatResult>("/api/jobs/locks/heartbeat", {
    method: "POST",
    body: JSON.stringify({ adapter: "ssh", resource_key: input.resource_key ?? "ssh_default", job_id: input.job_id, lock_id: input.lock_id, attempt_id: input.attempt_id })
  });
}

export function recoverStaleJobLock(resource_key = "ssh_default") {
  return request<StaleLockRecoveryResult>("/api/jobs/locks/recover-stale", {
    method: "POST",
    body: JSON.stringify({ adapter: "ssh", resource_key })
  });
}

export function fetchJobArtifacts(projectId: string, jobId: string) {
  return request<GenerationArtifact[]>(`/api/projects/${projectId}/jobs/${jobId}/artifacts`);
}

export function fetchJobLog(projectId: string, jobId: string) {
  return request<JobLog>(`/api/projects/${projectId}/jobs/${jobId}/log`);
}

export function fetchJobArtifactText(projectId: string, jobId: string, artifactId: string) {
  return fetch(`${API_URL}/api/projects/${projectId}/jobs/${jobId}/artifacts/${artifactId}`, {
    headers: { Accept: "text/plain, application/json" }
  }).then(async (response) => {
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || `Request failed: ${response.status}`);
    }
    return response.text();
  });
}

export function approveStage(projectId: string, stage: string, note = "") {
  return request<Project>(`/api/projects/${projectId}/stages/${stage}/approve`, {
    method: "POST",
    body: JSON.stringify({ note })
  });
}

export function fetchLyricsArtifact(projectId: string) {
  return request<LyricsArtifact>(`/api/projects/${projectId}/artifacts/lyrics`);
}

export function fetchStoryboardArtifact(projectId: string) {
  return request<StoryboardArtifact>(`/api/projects/${projectId}/artifacts/storyboard`);
}

export function fetchKeyframesArtifact(projectId: string) {
  return request<KeyframesArtifact>(`/api/projects/${projectId}/artifacts/keyframes`);
}

export function fetchVideoScenesArtifact(projectId: string) {
  return request<VideoScenesArtifact>(`/api/projects/${projectId}/artifacts/video-scenes`);
}

export function fetchFullEpisodeArtifact(projectId: string) {
  return request<FullEpisodeArtifact>(`/api/projects/${projectId}/artifacts/full-episode`);
}

export function fetchReelsArtifact(projectId: string) {
  return request<ReelsArtifact>(`/api/projects/${projectId}/artifacts/reels`);
}

export function fetchComplianceReportArtifact(projectId: string) {
  return request<ComplianceReportArtifact>(`/api/projects/${projectId}/artifacts/compliance-report`);
}

export function fetchPublishPackageArtifact(projectId: string) {
  return request<PublishPackageArtifact>(`/api/projects/${projectId}/artifacts/publish-package`);
}

export function fetchArtifactInventory(projectId: string) {
  return request<ArtifactInventoryItem[]>(`/api/projects/${projectId}/artifacts`);
}

export function runStage(projectId: string, stage: string) {
  return request<Job>(`/api/projects/${projectId}/jobs/${stage}`, {
    method: "POST"
  });
}
