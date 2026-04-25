export type StageStatus = "pending" | "queued" | "running" | "needs_review" | "completed" | "failed";

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
  pipeline: PipelineStage[];
  created_at: string;
  updated_at: string;
};

export type Job = {
  id: string;
  project_id: string;
  stage: string;
  status: StageStatus;
  adapter: "mock";
  message: string;
  created_at: string;
  updated_at: string;
};

export type ServerConnection = {
  mode: "mock";
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

export type ProjectInput = {
  title: string;
  topic: string;
  age_range: string;
  emotional_tone: string;
  educational_goal: string;
  characters: string[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

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

export function approveStage(projectId: string, stage: string, note = "") {
  return request<Project>(`/api/projects/${projectId}/stages/${stage}/approve`, {
    method: "POST",
    body: JSON.stringify({ note })
  });
}

export function runStage(projectId: string, stage: string) {
  return request<Job>(`/api/projects/${projectId}/jobs/${stage}`, {
    method: "POST"
  });
}
