"use client";

import { useEffect, useMemo, useState } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Activity, Archive, ArrowRight, BookOpenCheck, CheckCircle2, Clapperboard, Download, Film, Images, KeyRound, ListChecks, ListMusic, Loader2, Music2, PackageCheck, PanelsTopLeft, Play, RotateCcw, Server, Sparkles, Target, Wand2, XCircle } from "lucide-react";
import {
  AntiRepetitionReport,
  approveEpisodeSpec,
  approveStage,
  ArtifactInventoryItem,
  buildApiUrl,
  cancelJob,
  ComplianceReportArtifact,
  createSeries,
  createProject,
  EpisodeSpecInput,
  fetchArtifactInventory,
  fetchComplianceReportArtifact,
  fetchFullEpisodeArtifact,
  fetchJobArtifactText,
  fetchJobArtifacts,
  fetchJobDetail,
  fetchJobEvents,
  fetchJobLog,
  fetchKeyframesArtifact,
  fetchProjectApprovals,
  fetchProjectJobs,
  fetchProjectNextAction,
  fetchPublishPackageArtifact,
  fetchAntiRepetitionReport,
  fetchProjects,
  fetchSeries,
  fetchLyricsArtifact,
  fetchReelsArtifact,
  fetchServerProfile,
  fetchSshQueueStatus,
  fetchStoryboardArtifact,
  fetchVideoScenesArtifact,
  FullEpisodeArtifact,
  GenerationArtifact,
  GenerationJobDetail,
  Job,
  JobEvent,
  JobLog,
  KeyframesArtifact,
  linkProjectSeries,
  LyricsArtifact,
  Project,
  ProjectInput,
  ProjectNextAction,
  PublishPackageArtifact,
  ReelsArtifact,
  retryJob,
  runAntiRepetition,
  runStage,
  saveEpisodeSpec,
  saveServerProfile,
  ServerConnection,
  ServerProfile,
  ServerProfileInput,
  SeriesBible,
  SeriesBibleInput,
  StageApproval,
  StoryboardArtifact,
  testServerConnection,
  VideoScenesArtifact,
  WorkerQueueStatus
} from "../lib/api";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const stageLabels: Record<string, string> = {
  "brief.generate": "Brief",
  "lyrics.generate": "Tekst",
  "characters.import_or_approve": "Postacie",
  "audio.generate_or_import": "Audio",
  "storyboard.generate": "Storyboard",
  "keyframes.generate": "Keyframes",
  "video.scenes.generate": "Sceny",
  "render.full_episode": "Odcinek",
  "render.reels": "Rolki",
  "quality.compliance_report": "Kontrola",
  "publish.prepare_package": "Paczka"
};

const statusLabels: Record<string, string> = {
  pending: "czeka",
  queued: "w kolejce",
  running: "pracuje",
  needs_review: "do akceptacji",
  completed: "gotowe",
  failed: "błąd",
  cancelled: "anulowany"
};

function splitCharacters(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function splitList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseAgeRange(value: string) {
  const matches = value.match(/\d+/g)?.map(Number) ?? [];
  return {
    min: matches[0] ?? 3,
    max: matches[1] ?? matches[0] ?? 5
  };
}

function statusClass(status: string) {
  if (status === "completed") return "bg-[var(--teal)] text-[#07110f]";
  if (status === "needs_review") return "bg-[var(--acid)] text-[#101200]";
  if (status === "failed" || status === "cancelled") return "bg-[var(--coral)] text-white";
  if (status === "running" || status === "queued") return "bg-[var(--violet)] text-white";
  return "bg-white/10 text-white/70";
}

function fileNameFromPath(path: string) {
  return path.split("/").filter(Boolean).at(-1) ?? path;
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function getStageStatus(project: Project | null, stage: string) {
  return project?.pipeline.find((item) => item.stage === stage)?.status;
}

function canRunPipelineStage(project: Project | null, stage: string) {
  if (!project) return false;
  const stageIndex = project.pipeline.findIndex((item) => item.stage === stage);
  if (stageIndex < 1) return false;
  const currentStage = project.pipeline[stageIndex];
  const previousStage = project.pipeline[stageIndex - 1];
  return currentStage.status === "pending" && previousStage.status === "completed";
}

function createSeriesDefaults(project: Project | null): SeriesBibleInput & { safety_rules_text: string; forbidden_content_text: string } {
  const age = parseAgeRange(project?.brief.age_range ?? "3-5");
  return {
    name: project ? `${project.brief.topic} series` : "",
    status: "draft",
    target_age_min: age.min,
    target_age_max: age.max,
    primary_language: "pl",
    secondary_language: "en",
    learning_domain: project?.brief.educational_goal ?? "",
    series_premise: "",
    main_characters: [],
    visual_style: "",
    music_style: "",
    voice_rules: "",
    safety_rules: [],
    forbidden_content: [],
    thumbnail_rules: "",
    made_for_kids_default: true,
    safety_rules_text: "no unsafe actions, no fear pressure",
    forbidden_content_text: "violence, brand mascots, endless-watch prompts"
  };
}

function createEpisodeSpecDefaults(project: Project | null): EpisodeSpecInput & { vocabulary_text: string; search_keywords_text: string; success_criteria_text: string } {
  const age = parseAgeRange(project?.brief.age_range ?? "3-5");
  return {
    working_title: project?.title ?? "",
    topic: project?.brief.topic ?? "",
    target_age_min: age.min,
    target_age_max: age.max,
    learning_objective: {
      statement: project?.brief.educational_goal ?? "",
      domain: "vocabulary",
      vocabulary_terms: [],
      success_criteria: []
    },
    format: "song_video",
    target_duration_sec: 150,
    audience_context: "both",
    search_keywords: [],
    hook_idea: "",
    derivative_plan: {
      make_shorts: true,
      make_reels: true,
      make_parent_teacher_page: true,
      make_lyrics_page: true
    },
    made_for_kids: true,
    risk_notes: "",
    vocabulary_text: "",
    search_keywords_text: "",
    success_criteria_text: ""
  };
}

export default function Home() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [seriesList, setSeriesList] = useState<SeriesBible[]>([]);
  const [connection, setConnection] = useState<ServerConnection | null>(null);
  const [serverProfile, setServerProfile] = useState<ServerProfile | null>(null);
  const [lyricsArtifact, setLyricsArtifact] = useState<LyricsArtifact | null>(null);
  const [storyboardArtifact, setStoryboardArtifact] = useState<StoryboardArtifact | null>(null);
  const [keyframesArtifact, setKeyframesArtifact] = useState<KeyframesArtifact | null>(null);
  const [videoScenesArtifact, setVideoScenesArtifact] = useState<VideoScenesArtifact | null>(null);
  const [fullEpisodeArtifact, setFullEpisodeArtifact] = useState<FullEpisodeArtifact | null>(null);
  const [reelsArtifact, setReelsArtifact] = useState<ReelsArtifact | null>(null);
  const [complianceReportArtifact, setComplianceReportArtifact] = useState<ComplianceReportArtifact | null>(null);
  const [publishPackageArtifact, setPublishPackageArtifact] = useState<PublishPackageArtifact | null>(null);
  const [antiRepetitionReport, setAntiRepetitionReport] = useState<AntiRepetitionReport | null>(null);
  const [serverJobDetail, setServerJobDetail] = useState<GenerationJobDetail | null>(null);
  const [serverArtifacts, setServerArtifacts] = useState<GenerationArtifact[]>([]);
  const [serverLog, setServerLog] = useState<JobLog | null>(null);
  const [serverEvents, setServerEvents] = useState<JobEvent[]>([]);
  const [queueStatus, setQueueStatus] = useState<WorkerQueueStatus | null>(null);
  const [artifactPreview, setArtifactPreview] = useState<{ artifactId: string; content: string } | null>(null);
  const [artifactInventory, setArtifactInventory] = useState<ArtifactInventoryItem[]>([]);
  const [projectJobs, setProjectJobs] = useState<Job[]>([]);
  const [stageApprovals, setStageApprovals] = useState<StageApproval[]>([]);
  const [nextAction, setNextAction] = useState<ProjectNextAction | null>(null);
  const [form, setForm] = useState({
    title: "",
    topic: "",
    age_range: "3-5",
    emotional_tone: "radość",
    educational_goal: "",
    characters: "toothbrush_friend_v1"
  });
  const [serverForm, setServerForm] = useState<ServerProfileInput>({
    mode: "ssh",
    label: "Production GPU worker",
    host: "gpu-worker.tailnet",
    username: "daniel",
    port: 22,
    remote_root: "/home/daniel/aikiddo-worker",
    ssh_key_path: "~/.ssh/id_ed25519",
    tailscale_name: "gpu-worker"
  });
  const [seriesForm, setSeriesForm] = useState(createSeriesDefaults(null));
  const [episodeSpecForm, setEpisodeSpecForm] = useState(createEpisodeSpecDefaults(null));
  const [jobMessage, setJobMessage] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [isSavingSeries, setIsSavingSeries] = useState(false);
  const [isSavingEpisodeSpec, setIsSavingEpisodeSpec] = useState(false);
  const [isApprovingEpisodeSpec, setIsApprovingEpisodeSpec] = useState(false);
  const [isRunningAntiRepetition, setIsRunningAntiRepetition] = useState(false);
  const [runningStage, setRunningStage] = useState<string | null>(null);
  const [jobAction, setJobAction] = useState<"cancel" | "retry" | null>(null);
  const [isSavingServer, setIsSavingServer] = useState(false);
  const [approvingStage, setApprovingStage] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadStudio() {
      try {
        const [projectList, savedSeries] = await Promise.all([fetchProjects(), fetchSeries()]);
        setProjects(projectList);
        setSeriesList(savedSeries);
        const firstProject = projectList[0] ?? null;
        setSelectedProject(firstProject);
        syncStrategyForms(firstProject);
        if (firstProject) await loadArtifacts(firstProject.id);
        try {
          const profile = await fetchServerProfile();
          if (profile.mode === "ssh") {
            setServerProfile(profile);
            setServerForm({
              mode: "ssh",
              label: profile.label,
              host: profile.host,
              username: profile.username,
              port: profile.port,
              remote_root: profile.remote_root,
              ssh_key_path: profile.ssh_key_path,
              tailscale_name: profile.tailscale_name
            });
            setConnection(await testServerConnection());
          }
        } catch {
          setServerProfile(null);
        }
        try {
          setQueueStatus(await fetchSshQueueStatus());
        } catch {
          setQueueStatus(null);
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Nie udało się wczytać studia.");
      }
    }

    loadStudio();
  }, []);

  useGSAP(() => {
    gsap.from(".hero-line", {
      y: 28,
      opacity: 0,
      duration: 0.9,
      ease: "power3.out",
      stagger: 0.08
    });

    gsap.to(".reveal-word", {
      opacity: 1,
      y: 0,
      stagger: 0.025,
      scrollTrigger: {
        trigger: ".pipeline-copy",
        start: "top 82%",
        end: "bottom 58%",
        scrub: true
      }
    });

    const stageCards = gsap.utils.toArray<HTMLElement>(".stage-card");
    if (stageCards.length > 0) {
      gsap.fromTo(
        stageCards,
        { scale: 0.94, opacity: 0.55 },
        {
          scale: 1,
          opacity: 1,
          duration: 0.8,
          ease: "power2.out",
          stagger: 0.04,
          scrollTrigger: {
            trigger: ".stage-grid",
            start: "top 80%"
          }
        }
      );
    }
  }, []);

  useEffect(() => {
    if (serverJobDetail?.status !== "queued" && serverJobDetail?.status !== "running") return;
    const jobId = serverJobDetail.id;

    const interval = window.setInterval(async () => {
      try {
        const jobDetail = await fetchJobDetail(jobId);
        setServerJobDetail(jobDetail);
        setServerArtifacts(jobDetail.artifacts);
        setServerEvents(await fetchJobEvents(jobId));
        setQueueStatus(await fetchSshQueueStatus());
      } catch {
        window.clearInterval(interval);
      }
    }, 2000);

    return () => window.clearInterval(interval);
  }, [serverJobDetail?.id, serverJobDetail?.status]);

  const selectedSummary = useMemo(() => {
    if (!selectedProject) return "Brak projektu";
    return `${selectedProject.brief.topic} · ${selectedProject.brief.age_range} · ${selectedProject.brief.emotional_tone}`;
  }, [selectedProject]);

  const selectedSeries = useMemo(() => {
    if (!selectedProject?.series_id) return null;
    return seriesList.find((series) => series.id === selectedProject.series_id) ?? null;
  }, [selectedProject, seriesList]);

  const publishPrimaryArtifacts = useMemo(() => {
    if (!selectedProject || serverJobDetail?.stage !== "publish.prepare_package" || serverJobDetail.publish?.status !== "ready") return [];
    return serverJobDetail.publish.primary_artifacts;
  }, [selectedProject, serverJobDetail?.publish, serverJobDetail?.stage]);

  const canRunLyrics = getStageStatus(selectedProject, "brief.generate") === "completed";

  function syncStrategyForms(project: Project | null) {
    setSeriesForm(createSeriesDefaults(project));
    if (project?.episode_spec) {
      setEpisodeSpecForm({
        ...project.episode_spec,
        vocabulary_text: project.episode_spec.learning_objective.vocabulary_terms.join(", "),
        search_keywords_text: project.episode_spec.search_keywords.join(", "),
        success_criteria_text: project.episode_spec.learning_objective.success_criteria.join(", ")
      });
    } else {
      setEpisodeSpecForm(createEpisodeSpecDefaults(project));
    }
  }

  async function loadArtifacts(projectId: string) {
    try {
      setLyricsArtifact(await fetchLyricsArtifact(projectId));
    } catch {
      setLyricsArtifact(null);
    }
    try {
      setStoryboardArtifact(await fetchStoryboardArtifact(projectId));
    } catch {
      setStoryboardArtifact(null);
    }
    try {
      setKeyframesArtifact(await fetchKeyframesArtifact(projectId));
    } catch {
      setKeyframesArtifact(null);
    }
    try {
      setVideoScenesArtifact(await fetchVideoScenesArtifact(projectId));
    } catch {
      setVideoScenesArtifact(null);
    }
    try {
      setFullEpisodeArtifact(await fetchFullEpisodeArtifact(projectId));
    } catch {
      setFullEpisodeArtifact(null);
    }
    try {
      setReelsArtifact(await fetchReelsArtifact(projectId));
    } catch {
      setReelsArtifact(null);
    }
    try {
      setComplianceReportArtifact(await fetchComplianceReportArtifact(projectId));
    } catch {
      setComplianceReportArtifact(null);
    }
    try {
      setPublishPackageArtifact(await fetchPublishPackageArtifact(projectId));
    } catch {
      setPublishPackageArtifact(null);
    }
    try {
      setAntiRepetitionReport(await fetchAntiRepetitionReport(projectId));
    } catch {
      setAntiRepetitionReport(null);
    }

    let jobsForProject: Job[] = [];
    try {
      jobsForProject = await fetchProjectJobs(projectId);
      setProjectJobs(jobsForProject);
    } catch {
      jobsForProject = [];
      setProjectJobs([]);
    }

    const latestServerJob = [...jobsForProject].reverse().find((job) => job.adapter === "ssh") ?? null;
    if (latestServerJob) {
      try {
        const jobDetail = await fetchJobDetail(latestServerJob.id);
        setServerJobDetail(jobDetail);
        setServerArtifacts(jobDetail.artifacts);
        setServerEvents(await fetchJobEvents(jobDetail.id));
        try {
          setServerArtifacts(await fetchJobArtifacts(projectId, latestServerJob.id));
        } catch {
          setServerArtifacts(jobDetail.artifacts);
        }
        try {
          setServerLog(await fetchJobLog(projectId, latestServerJob.id));
        } catch {
          setServerLog(null);
        }
      } catch {
        setServerJobDetail(null);
        setServerArtifacts([]);
        setServerLog(null);
        setServerEvents([]);
        setArtifactPreview(null);
      }
    } else {
      setServerJobDetail(null);
      setServerArtifacts([]);
      setServerLog(null);
      setServerEvents([]);
      setArtifactPreview(null);
    }
    try {
      setQueueStatus(await fetchSshQueueStatus());
    } catch {
      setQueueStatus(null);
    }
    try {
      setArtifactInventory(await fetchArtifactInventory(projectId));
    } catch {
      setArtifactInventory([]);
    }
    try {
      setStageApprovals(await fetchProjectApprovals(projectId));
    } catch {
      setStageApprovals([]);
    }
    try {
      setNextAction(await fetchProjectNextAction(projectId));
    } catch {
      setNextAction(null);
    }
  }

  async function handleCreateProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsCreating(true);
    setError("");
    setJobMessage("");

    try {
      const created = await createProject({
        title: form.title,
        topic: form.topic,
        age_range: form.age_range,
        emotional_tone: form.emotional_tone,
        educational_goal: form.educational_goal,
        characters: splitCharacters(form.characters)
      });
      setProjects((current) => [created, ...current.filter((project) => project.id !== created.id)]);
      setSelectedProject(created);
      syncStrategyForms(created);
      setLyricsArtifact(null);
      setStoryboardArtifact(null);
      setKeyframesArtifact(null);
      setVideoScenesArtifact(null);
      setFullEpisodeArtifact(null);
      setReelsArtifact(null);
      setComplianceReportArtifact(null);
      setPublishPackageArtifact(null);
      setAntiRepetitionReport(null);
      setServerJobDetail(null);
      setServerArtifacts([]);
      setServerLog(null);
      setServerEvents([]);
      setArtifactPreview(null);
      setArtifactInventory([]);
      setProjectJobs([]);
      setStageApprovals([]);
      await loadArtifacts(created.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się utworzyć projektu.");
    } finally {
      setIsCreating(false);
    }
  }

  async function handleRunStage(stage: string) {
    if (!selectedProject) return;
    setRunningStage(stage);
    setError("");
    setJobMessage("");

    try {
      const job = await runStage(selectedProject.id, stage);
      const updatedProjects = await fetchProjects();
      setProjects(updatedProjects);
      setSelectedProject(updatedProjects.find((project) => project.id === selectedProject.id) ?? selectedProject);
      await loadArtifacts(selectedProject.id);
      const jobDetail = await fetchJobDetail(job.id);
      setServerJobDetail(jobDetail);
      setServerEvents(await fetchJobEvents(job.id));
      setQueueStatus(await fetchSshQueueStatus());
      setJobMessage(job.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się uruchomić etapu.");
    } finally {
      setRunningStage(null);
    }
  }

  async function handleCancelServerJob() {
    if (!selectedProject || !serverJobDetail) return;
    setJobAction("cancel");
    setError("");
    setJobMessage("");

    try {
      const cancelled = await cancelJob(serverJobDetail.id);
      setServerJobDetail(cancelled);
      setServerArtifacts(cancelled.artifacts);
      setServerEvents(await fetchJobEvents(cancelled.id));
      setQueueStatus(await fetchSshQueueStatus());
      const updatedProjects = await fetchProjects();
      setProjects(updatedProjects);
      setSelectedProject(updatedProjects.find((project) => project.id === selectedProject.id) ?? selectedProject);
      setJobMessage(cancelled.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się anulować joba.");
    } finally {
      setJobAction(null);
    }
  }

  async function handleRetryServerJob() {
    if (!selectedProject || !serverJobDetail) return;
    setJobAction("retry");
    setError("");
    setJobMessage("");

    try {
      const retried = await retryJob(serverJobDetail.id);
      setServerJobDetail(retried.job);
      setServerArtifacts(retried.job.artifacts);
      setServerEvents(await fetchJobEvents(retried.job.id));
      setQueueStatus(await fetchSshQueueStatus());
      const updatedProjects = await fetchProjects();
      setProjects(updatedProjects);
      setSelectedProject(updatedProjects.find((project) => project.id === selectedProject.id) ?? selectedProject);
      setJobMessage(retried.job.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się ponowić joba.");
    } finally {
      setJobAction(null);
    }
  }

  async function handleSaveServerProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSavingServer(true);
    setError("");

    try {
      const saved = await saveServerProfile({ ...serverForm, mode: "ssh" });
      setServerProfile(saved);
      const server = await testServerConnection();
      setConnection(server);
      setQueueStatus(await fetchSshQueueStatus());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się zapisać profilu serwera.");
    } finally {
      setIsSavingServer(false);
    }
  }

  async function handlePreviewArtifact(artifact: GenerationArtifact) {
    if (!selectedProject || !serverJobDetail) return;
    setError("");
    try {
      const content = await fetchJobArtifactText(selectedProject.id, serverJobDetail.id, artifact.artifact_id);
      setArtifactPreview({ artifactId: artifact.artifact_id, content });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się pobrać artefaktu z serwera.");
    }
  }

  async function refreshSelectedProject(projectId: string) {
    const updatedProjects = await fetchProjects();
    const updatedProject = updatedProjects.find((project) => project.id === projectId) ?? null;
    setProjects(updatedProjects);
    setSelectedProject(updatedProject);
    syncStrategyForms(updatedProject);
    if (updatedProject) await loadArtifacts(updatedProject.id);
  }

  async function handleCreateSeries(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProject) return;
    setIsSavingSeries(true);
    setError("");
    setJobMessage("");

    try {
      const createdSeries = await createSeries({
        name: seriesForm.name,
        status: "draft",
        target_age_min: Number(seriesForm.target_age_min),
        target_age_max: Number(seriesForm.target_age_max),
        primary_language: seriesForm.primary_language,
        secondary_language: seriesForm.secondary_language || null,
        learning_domain: seriesForm.learning_domain,
        series_premise: seriesForm.series_premise,
        main_characters: seriesForm.main_characters,
        visual_style: seriesForm.visual_style,
        music_style: seriesForm.music_style,
        voice_rules: seriesForm.voice_rules,
        safety_rules: splitList(seriesForm.safety_rules_text),
        forbidden_content: splitList(seriesForm.forbidden_content_text),
        thumbnail_rules: seriesForm.thumbnail_rules ?? "",
        made_for_kids_default: seriesForm.made_for_kids_default
      });
      const updatedProject = await linkProjectSeries(selectedProject.id, createdSeries.id);
      const updatedSeries = await fetchSeries();
      setSeriesList(updatedSeries);
      setSelectedProject(updatedProject);
      setProjects((current) => [updatedProject, ...current.filter((project) => project.id !== updatedProject.id)]);
      syncStrategyForms(updatedProject);
      await loadArtifacts(updatedProject.id);
      setJobMessage(`Seria ${createdSeries.name} zapisana i przypięta do projektu.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się zapisać serii.");
    } finally {
      setIsSavingSeries(false);
    }
  }

  async function handleSaveEpisodeSpec(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProject) return;
    setIsSavingEpisodeSpec(true);
    setError("");
    setJobMessage("");

    try {
      await saveEpisodeSpec(selectedProject.id, {
        working_title: episodeSpecForm.working_title,
        topic: episodeSpecForm.topic,
        target_age_min: episodeSpecForm.target_age_min === null ? null : Number(episodeSpecForm.target_age_min),
        target_age_max: episodeSpecForm.target_age_max === null ? null : Number(episodeSpecForm.target_age_max),
        learning_objective: {
          statement: episodeSpecForm.learning_objective.statement,
          domain: episodeSpecForm.learning_objective.domain,
          vocabulary_terms: splitList(episodeSpecForm.vocabulary_text),
          success_criteria: splitList(episodeSpecForm.success_criteria_text)
        },
        format: episodeSpecForm.format,
        target_duration_sec: Number(episodeSpecForm.target_duration_sec),
        audience_context: episodeSpecForm.audience_context,
        search_keywords: splitList(episodeSpecForm.search_keywords_text),
        hook_idea: episodeSpecForm.hook_idea ?? "",
        derivative_plan: episodeSpecForm.derivative_plan,
        made_for_kids: episodeSpecForm.made_for_kids,
        risk_notes: episodeSpecForm.risk_notes ?? ""
      });
      await refreshSelectedProject(selectedProject.id);
      setJobMessage("Episode Spec zapisany.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się zapisać Episode Spec.");
    } finally {
      setIsSavingEpisodeSpec(false);
    }
  }

  async function handleApproveEpisodeSpec() {
    if (!selectedProject) return;
    setIsApprovingEpisodeSpec(true);
    setError("");
    setJobMessage("");

    try {
      const updated = await approveEpisodeSpec(selectedProject.id, "Episode Spec approved for production.");
      setSelectedProject(updated);
      setProjects((current) => [updated, ...current.filter((project) => project.id !== updated.id)]);
      syncStrategyForms(updated);
      await loadArtifacts(updated.id);
      setJobMessage("Episode Spec zatwierdzony.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się zatwierdzić Episode Spec.");
    } finally {
      setIsApprovingEpisodeSpec(false);
    }
  }

  async function handleRunAntiRepetition() {
    if (!selectedProject) return;
    setIsRunningAntiRepetition(true);
    setError("");
    setJobMessage("");

    try {
      const report = await runAntiRepetition(selectedProject.id);
      setAntiRepetitionReport(report);
      await loadArtifacts(selectedProject.id);
      setJobMessage(`Anti-Repetition: ${report.status} (${report.score.toFixed(2)}).`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się uruchomić Anti-Repetition.");
    } finally {
      setIsRunningAntiRepetition(false);
    }
  }

  async function handleApproveStage(stage: string) {
    if (!selectedProject) return;
    setApprovingStage(stage);
    setError("");

    try {
      const updated = await approveStage(selectedProject.id, stage, `Operator approved ${stage}.`);
      setSelectedProject(updated);
      setProjects((current) => [updated, ...current.filter((project) => project.id !== updated.id)]);
      await loadArtifacts(updated.id);
      setJobMessage(`${stageLabels[stage] ?? stage} zatwierdzony.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się zatwierdzić etapu.");
    } finally {
      setApprovingStage(null);
    }
  }

  const revealWords = "Pipeline zachowuje kontrakty serwera GPU: kolejka, manifest, status, artefakty i bramka akceptacji człowieka."
    .split(" ");

  return (
    <main className="ambient-studio grain min-h-screen w-full max-w-full overflow-x-hidden text-[var(--paper)]">
      <nav className="mx-auto flex w-full max-w-7xl items-center justify-between px-5 py-6 md:px-8">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-full bg-[var(--acid)] text-[var(--ink)]">
            <Music2 size={20} />
          </div>
          <div>
            <p className="text-sm font-semibold">AI Kids Music Studio</p>
            <p className="text-xs text-white/48">generowanie na serwerze</p>
          </div>
        </div>
        <button
          className="group flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm text-white transition hover:bg-white hover:text-[var(--ink)]"
          type="button"
          onClick={() => testServerConnection().then(setConnection)}
          disabled={serverProfile?.mode !== "ssh"}
        >
          <Server size={16} />
          Sprawdź serwer
        </button>
      </nav>

      <section className="mx-auto grid w-full max-w-7xl gap-10 px-5 pb-20 pt-10 md:grid-cols-[1.08fr_0.92fr] md:px-8 md:pb-32 md:pt-20">
        <div className="flex flex-col justify-center">
          <h1 className="hero-line max-w-6xl text-[clamp(3rem,5vw,5.5rem)] font-black leading-[0.94] tracking-normal">
            Studio piosenek i klipów AI
          </h1>
          <p className="hero-line mt-7 max-w-2xl text-lg leading-8 text-white/70">
            Kokpit produkcyjny: brief, pipeline, manifesty serwerowe, status generacji i bramki akceptacji człowieka przed kosztownym renderem.
          </p>
          <div className="hero-line mt-9 flex flex-wrap gap-3">
            <a
              className="group inline-flex items-center gap-2 rounded-full bg-[var(--acid)] px-5 py-3 text-sm font-bold text-[var(--ink)] transition hover:scale-[1.02]"
              href="#project-form"
            >
              Nowy projekt
              <ArrowRight size={16} className="transition group-hover:translate-x-1" />
            </a>
            <button
              className="inline-flex items-center gap-2 rounded-full border border-white/18 bg-white px-5 py-3 text-sm font-bold text-[var(--ink)] transition hover:scale-[1.02]"
              type="button"
              onClick={() => handleRunStage("lyrics.generate")}
              disabled={!selectedProject || serverProfile?.mode !== "ssh" || runningStage !== null || !canRunLyrics || getStageStatus(selectedProject, "lyrics.generate") !== "pending"}
            >
              {runningStage === "lyrics.generate" ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              Uruchom na serwerze
            </button>
          </div>
        </div>

        <div className="group overflow-hidden rounded-[2rem] border border-white/12 bg-black/30">
          <div
            className="min-h-[440px] bg-cover bg-center opacity-90 contrast-125 transition-transform duration-700 ease-out group-hover:scale-105"
            style={{
              backgroundImage:
                "linear-gradient(180deg, rgba(12,12,13,0.08), rgba(12,12,13,0.72)), url(https://picsum.photos/seed/music-studio-console/1200/1400)"
            }}
          />
        </div>
      </section>

      <section className="mx-auto grid-flow-dense grid w-full max-w-7xl grid-cols-1 gap-4 px-5 py-20 md:grid-cols-12 md:px-8 md:py-32">
        <form
          id="project-form"
          className="studio-card rounded-[1.4rem] p-5 md:col-span-5 md:p-7"
          onSubmit={handleCreateProject}
        >
          <div className="mb-6 flex items-center justify-between gap-4">
            <div>
              <h2 className="text-2xl font-black">Nowy projekt</h2>
              <p className="mt-1 text-sm text-white/52">Brief zapisze się w serwerowym katalogu projektu.</p>
            </div>
            <Wand2 className="text-[var(--acid)]" size={24} />
          </div>
          <div className="grid gap-3">
            <label className="grid gap-2 text-sm text-white/70">
              Tytuł projektu
              <input className="field" required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
            </label>
            <label className="grid gap-2 text-sm text-white/70">
              Temat
              <input className="field" required value={form.topic} onChange={(event) => setForm({ ...form, topic: event.target.value })} />
            </label>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="grid gap-2 text-sm text-white/70">
                Wiek
                <input className="field" required value={form.age_range} onChange={(event) => setForm({ ...form, age_range: event.target.value })} />
              </label>
              <label className="grid gap-2 text-sm text-white/70">
                Emocja
                <input className="field" required value={form.emotional_tone} onChange={(event) => setForm({ ...form, emotional_tone: event.target.value })} />
              </label>
            </div>
            <label className="grid gap-2 text-sm text-white/70">
              Cel edukacyjny
              <textarea className="field min-h-24 resize-none" required value={form.educational_goal} onChange={(event) => setForm({ ...form, educational_goal: event.target.value })} />
            </label>
            <label className="grid gap-2 text-sm text-white/70">
              Postacie
              <input className="field" value={form.characters} onChange={(event) => setForm({ ...form, characters: event.target.value })} />
            </label>
          </div>
          <button
            className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--acid)] px-4 py-3 font-black text-[var(--ink)] transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
            type="submit"
            disabled={isCreating}
          >
            {isCreating ? <Loader2 size={18} className="animate-spin" /> : <CheckCircle2 size={18} />}
            Utwórz projekt
          </button>
        </form>

        <article className="studio-card rounded-[1.4rem] p-5 md:col-span-4 md:p-7">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-2xl font-black">Serwer GPU</h2>
              <p className="mt-1 text-sm text-white/52">{serverProfile?.label ?? "profil roboczy"}</p>
            </div>
            <Activity className="text-[var(--teal)]" size={24} />
          </div>
          <div className="mt-6 rounded-2xl bg-[var(--mist)] p-5 text-[var(--ink)]">
            <p className="text-sm font-bold">{connection?.message ?? "Sprawdzam profil serwera..."}</p>
            <p className="mt-5 text-5xl font-black">{connection?.reachable ? "ready" : "wait"}</p>
          </div>
          <div className="mt-5 rounded-2xl border border-white/10 bg-black/22 p-4" data-testid="server-generation">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-lg font-black">Generacja serwerowa</p>
                <p className="mt-1 text-sm leading-6 text-white/52">
                  {serverProfile?.mode === "ssh"
                    ? "Backend tworzy job, pilnuje manifestu i zapisuje artefakty po stronie serwera."
                    : "Zapisz profil serwera, żeby uruchamiać generacje."}
                </p>
              </div>
              <span className={`status-pill ${serverJobDetail?.status === "failed" ? "bg-[var(--coral)] text-white" : "bg-white/10 text-white/70"}`}>
                {serverJobDetail?.status ?? "idle"}
              </span>
            </div>
            <button
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-3 text-sm font-black text-[var(--ink)] transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
              type="button"
              onClick={() => handleRunStage("lyrics.generate")}
              disabled={!selectedProject || serverProfile?.mode !== "ssh" || runningStage !== null || getStageStatus(selectedProject, "lyrics.generate") !== "pending"}
            >
              {runningStage === "lyrics.generate" ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              Generuj na serwerze
            </button>
            {queueStatus ? (
              <div className="mt-4 grid gap-2 rounded-xl border border-white/10 bg-white/7 p-3 text-xs font-bold text-white/58">
                <div className="flex items-center justify-between gap-3">
                  <span>Queue status</span>
                  <span className="rounded-full bg-white/10 px-2 py-1 text-white/70">
                    {queueStatus.queued_count} queued
                  </span>
                </div>
                <div className="grid gap-1 text-white/42">
                  <span>Lock: {queueStatus.current_job_id ?? "free"}</span>
                  <span>Oldest: {queueStatus.oldest_queued_job_id ?? "none"}</span>
                </div>
              </div>
            ) : null}
            {serverJobDetail ? (
              <div className="mt-4 grid gap-3 text-sm text-white/68">
                <div className="rounded-xl bg-white/7 p-3">
                  <p className="font-black text-white">Job</p>
                  <p className="mt-1 break-all text-xs text-white/48">{serverJobDetail.id}</p>
                  <p className="mt-2 text-xs font-bold text-white/42">{serverJobDetail.phase}</p>
                  {serverJobDetail?.runner ? (
                    <div className="mt-2 flex flex-wrap gap-2 text-xs font-black">
                      <span className="rounded-full bg-white/10 px-2 py-1 text-white/54">
                        {serverJobDetail.runner.state === "waiting" ? "SSH worker busy" : serverJobDetail.runner.state === "acquired" ? "SSH worker acquired" : "SSH worker released"}
                      </span>
                      {serverJobDetail.queue_position > 0 ? (
                        <span className="rounded-full bg-[var(--acid)]/15 px-2 py-1 text-[var(--acid)]">
                          Position {serverJobDetail.queue_position}
                        </span>
                      ) : null}
                      {serverJobDetail.runner.auto_dispatch ? (
                        <span className="rounded-full bg-[var(--teal)]/15 px-2 py-1 text-[var(--teal)]">
                          Queue auto-dispatch enabled
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                  {serverJobDetail?.error ? (
                    <p className="mt-2 rounded-lg bg-[var(--coral)]/18 px-2 py-1 text-xs font-bold text-[var(--coral)]">
                      {serverJobDetail.error.message}
                    </p>
                  ) : null}
                  {serverJobDetail.status === "queued" || serverJobDetail.status === "running" || serverJobDetail.status === "failed" || serverJobDetail.status === "cancelled" || serverJobDetail.phase === "awaiting_review" ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {serverJobDetail.status === "queued" || serverJobDetail.status === "running" ? (
                        <button
                          className="inline-flex items-center gap-2 rounded-full border border-[var(--coral)]/40 px-3 py-1.5 text-xs font-black text-[var(--coral)] transition hover:bg-[var(--coral)] hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                          type="button"
                          onClick={handleCancelServerJob}
                          disabled={jobAction !== null}
                        >
                          {jobAction === "cancel" ? <Loader2 size={14} className="animate-spin" /> : <XCircle size={14} />}
                          Anuluj
                        </button>
                      ) : null}
                      {serverJobDetail.status === "failed" || serverJobDetail.status === "cancelled" || serverJobDetail.phase === "awaiting_review" ? (
                        <button
                          className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1.5 text-xs font-black text-[var(--ink)] transition hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-50"
                          type="button"
                          onClick={handleRetryServerJob}
                          disabled={jobAction !== null}
                        >
                          {jobAction === "retry" ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
                          Ponów
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                  {serverEvents.length ? (
                    <div className="mt-3 grid gap-1 border-t border-white/10 pt-3 text-xs text-white/48">
                      {serverEvents.slice(-5).map((event) => (
                        <div key={event.cursor} className="flex items-center justify-between gap-3">
                          <span className="font-black text-white/64">{event.event}</span>
                          <span>{new Date(event.created_at).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" })}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
                {serverJobDetail.preview ? (
                  <div className="rounded-xl border border-white/10 bg-white/7 p-3" data-testid="server-preview">
                    <p className="font-black text-white">{serverJobDetail.preview.title}</p>
                    <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-white/62">
                      {serverJobDetail.preview.lyrics}
                    </pre>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {serverJobDetail.preview.safety_notes.map((note) => (
                        <span key={note} className="rounded-full bg-white/10 px-3 py-1 text-xs font-bold text-white/62">
                          {note}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
                {serverArtifacts.length ? (
                  <div className="grid gap-2">
                    {serverArtifacts.map((artifact) => {
                      const canPreview = artifact.mime_type.startsWith("text/") || artifact.mime_type === "application/json";
                      const downloadUrl =
                        selectedProject
                          ? buildApiUrl(`/api/projects/${selectedProject.id}/jobs/${serverJobDetail.id}/artifacts/${artifact.artifact_id}`)
                          : "";

                      return (
                        <div key={artifact.artifact_id} className="rounded-xl bg-[var(--mist)] p-3 text-[var(--ink)]">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div>
                              <p className="text-xs font-black uppercase">{artifact.type}</p>
                              <p className="mt-1 break-all text-sm font-black">{fileNameFromPath(artifact.filename)}</p>
                            </div>
                            <div className="flex items-center gap-2">
                              {canPreview ? (
                                <button
                                  className="rounded-full bg-[var(--ink)] px-3 py-1 text-xs font-black text-white transition hover:scale-[1.03]"
                                  type="button"
                                  onClick={() => handlePreviewArtifact(artifact)}
                                >
                                  Preview
                                </button>
                              ) : null}
                              <a
                                className="rounded-full border border-[var(--ink)]/20 px-3 py-1 text-xs font-black text-[var(--ink)] transition hover:bg-[var(--ink)] hover:text-white"
                                href={downloadUrl}
                                rel="noreferrer"
                                target="_blank"
                              >
                                Download
                              </a>
                            </div>
                          </div>
                          <p className="mt-2 break-all text-xs font-semibold text-[var(--ink)]/58">
                            {artifact.mime_type} · {artifact.size_bytes} bytes · {artifact.sha256.slice(0, 12)}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                ) : null}
                {artifactPreview ? (
                  <div className="rounded-xl border border-[var(--acid)]/30 bg-[var(--acid)]/10 p-3">
                    <p className="font-black text-[var(--acid)]">Preview {artifactPreview.artifactId}</p>
                    <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-white/72">
                      {artifactPreview.content}
                    </pre>
                  </div>
                ) : null}
                {serverLog?.lines.length ? (
                  <div className="rounded-xl border border-white/10 bg-black/22 p-3">
                    <p className="font-black text-white">Log</p>
                    <div className="mt-2 space-y-1 text-xs text-white/52">
                      {serverLog.lines.map((line) => (
                        <p key={line}>{line}</p>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          <form className="mt-5 grid gap-3" onSubmit={handleSaveServerProfile}>
            <label className="grid gap-2 text-sm text-white/70">
              Nazwa profilu
              <input className="field" required value={serverForm.label} onChange={(event) => setServerForm({ ...serverForm, label: event.target.value })} />
            </label>
            <label className="grid gap-2 text-sm text-white/70">
              Host
              <input className="field" required value={serverForm.host} onChange={(event) => setServerForm({ ...serverForm, host: event.target.value })} />
            </label>
            <div className="grid gap-3 md:grid-cols-[1fr_0.55fr]">
              <label className="grid gap-2 text-sm text-white/70">
                Użytkownik SSH
                <input className="field" required value={serverForm.username} onChange={(event) => setServerForm({ ...serverForm, username: event.target.value })} />
              </label>
              <label className="grid gap-2 text-sm text-white/70">
                Port
                <input
                  className="field"
                  required
                  type="number"
                  min={1}
                  max={65535}
                  value={serverForm.port}
                  onChange={(event) => setServerForm({ ...serverForm, port: Number(event.target.value) })}
                />
              </label>
            </div>
            <label className="grid gap-2 text-sm text-white/70">
              Remote root
              <input className="field" required value={serverForm.remote_root} onChange={(event) => setServerForm({ ...serverForm, remote_root: event.target.value })} />
            </label>
            <label className="grid gap-2 text-sm text-white/70">
              Ścieżka klucza
              <input className="field" required value={serverForm.ssh_key_path} onChange={(event) => setServerForm({ ...serverForm, ssh_key_path: event.target.value })} />
            </label>
            <label className="grid gap-2 text-sm text-white/70">
              Tailscale
              <input className="field" required value={serverForm.tailscale_name} onChange={(event) => setServerForm({ ...serverForm, tailscale_name: event.target.value })} />
            </label>
            <button
              className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--acid)] px-4 py-3 font-black text-[var(--ink)] transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
              type="submit"
              disabled={isSavingServer}
            >
              {isSavingServer ? <Loader2 size={18} className="animate-spin" /> : <KeyRound size={18} />}
              Zapisz profil serwera
            </button>
          </form>
          <div className="mt-5 flex items-center gap-2 text-sm text-white/58">
            <Server size={16} />
            Hasła i zawartość kluczy nie są zapisywane.
          </div>
        </article>

        <article className="studio-card rounded-[1.4rem] p-5 md:col-span-3 md:p-7">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-2xl font-black">Projekty</h2>
            <ListMusic size={23} className="text-[var(--coral)]" />
          </div>
          <div className="space-y-3">
            {projects.length === 0 ? (
              <p className="text-sm leading-6 text-white/55">Lista jest pusta.</p>
            ) : (
              projects.map((project) => (
                <button
                  key={project.id}
                  className="group w-full rounded-2xl border border-white/10 bg-white/7 p-4 text-left transition hover:border-[var(--acid)] hover:bg-white/12"
                  type="button"
                  onClick={async () => {
                    setSelectedProject(project);
                    syncStrategyForms(project);
                    await loadArtifacts(project.id);
                  }}
                >
                  <span className="block text-sm font-bold">{project.title}</span>
                  <span className="mt-1 block text-xs text-white/48">{project.brief.topic}</span>
                </button>
              ))
            )}
          </div>
        </article>

        <article className="studio-card rounded-[1.4rem] p-5 md:col-span-12 md:p-7" data-testid="content-strategy">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <h2 className="text-3xl font-black">Content Strategy</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-white/55">
                Warstwa decyzyjna nad pipeline: seria, cel edukacyjny i publikowalność zanim zaczniemy palić czas operatora.
              </p>
            </div>
            <div className="flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-sm font-black text-white/72">
              <Target size={16} />
              {selectedProject?.episode_spec?.approval_status ?? "draft"}
            </div>
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-[0.92fr_1.08fr]">
            <form className="rounded-2xl border border-white/10 bg-black/20 p-4 md:p-5" onSubmit={handleCreateSeries}>
              <div className="mb-5 flex items-center justify-between gap-3">
                <div>
                  <p className="text-lg font-black">Series Bible</p>
                  <p className="mt-1 text-xs text-white/48">
                    {selectedSeries ? `Przypięta seria: ${selectedSeries.name}` : "Brak przypiętej serii"}
                  </p>
                </div>
                <BookOpenCheck className="text-[var(--teal)]" size={22} />
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="grid gap-2 text-sm text-white/70">
                  Nazwa serii
                  <input className="field" required value={seriesForm.name} onChange={(event) => setSeriesForm({ ...seriesForm, name: event.target.value })} />
                </label>
                <label className="grid gap-2 text-sm text-white/70">
                  Domena nauki
                  <input className="field" required value={seriesForm.learning_domain} onChange={(event) => setSeriesForm({ ...seriesForm, learning_domain: event.target.value })} />
                </label>
                <label className="grid gap-2 text-sm text-white/70 md:col-span-2">
                  Założenie serii
                  <textarea className="field min-h-20 resize-none" required value={seriesForm.series_premise} onChange={(event) => setSeriesForm({ ...seriesForm, series_premise: event.target.value })} />
                </label>
                <label className="grid gap-2 text-sm text-white/70">
                  Styl wizualny serii
                  <input className="field" required value={seriesForm.visual_style} onChange={(event) => setSeriesForm({ ...seriesForm, visual_style: event.target.value })} />
                </label>
                <label className="grid gap-2 text-sm text-white/70">
                  Styl muzyczny serii
                  <input className="field" required value={seriesForm.music_style} onChange={(event) => setSeriesForm({ ...seriesForm, music_style: event.target.value })} />
                </label>
                <label className="grid gap-2 text-sm text-white/70">
                  Reguły głosu
                  <input className="field" required value={seriesForm.voice_rules} onChange={(event) => setSeriesForm({ ...seriesForm, voice_rules: event.target.value })} />
                </label>
                <label className="grid gap-2 text-sm text-white/70">
                  Zasady bezpieczeństwa
                  <input className="field" required value={seriesForm.safety_rules_text} onChange={(event) => setSeriesForm({ ...seriesForm, safety_rules_text: event.target.value })} />
                </label>
                <label className="grid gap-2 text-sm text-white/70 md:col-span-2">
                  Zakazane treści
                  <input className="field" required value={seriesForm.forbidden_content_text} onChange={(event) => setSeriesForm({ ...seriesForm, forbidden_content_text: event.target.value })} />
                </label>
              </div>
              <button
                className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--acid)] px-4 py-3 font-black text-[var(--ink)] transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
                type="submit"
                disabled={!selectedProject || isSavingSeries}
              >
                {isSavingSeries ? <Loader2 size={18} className="animate-spin" /> : <CheckCircle2 size={18} />}
                Zapisz serię
              </button>
            </form>

            <form className="rounded-2xl border border-white/10 bg-white/7 p-4 md:p-5" onSubmit={handleSaveEpisodeSpec}>
              <div className="mb-5 flex items-center justify-between gap-3">
                <div>
                  <p className="text-lg font-black">Episode Spec</p>
                  <p className="mt-1 text-xs text-white/48">Learning objective, format i plan pochodnych.</p>
                </div>
                <ListChecks className="text-[var(--acid)]" size={22} />
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="grid gap-2 text-sm text-white/70">
                  Roboczy tytuł
                  <input className="field" required value={episodeSpecForm.working_title} onChange={(event) => setEpisodeSpecForm({ ...episodeSpecForm, working_title: event.target.value })} />
                </label>
                <label className="grid gap-2 text-sm text-white/70">
                  Zakres odcinka
                  <input className="field" required value={episodeSpecForm.topic} onChange={(event) => setEpisodeSpecForm({ ...episodeSpecForm, topic: event.target.value })} />
                </label>
                <label className="grid gap-2 text-sm text-white/70 md:col-span-2">
                  Learning objective
                  <textarea
                    className="field min-h-20 resize-none"
                    required
                    value={episodeSpecForm.learning_objective.statement}
                    onChange={(event) =>
                      setEpisodeSpecForm({
                        ...episodeSpecForm,
                        learning_objective: { ...episodeSpecForm.learning_objective, statement: event.target.value }
                      })
                    }
                  />
                </label>
                <label className="grid gap-2 text-sm text-white/70">
                  Słownictwo
                  <input className="field" value={episodeSpecForm.vocabulary_text} onChange={(event) => setEpisodeSpecForm({ ...episodeSpecForm, vocabulary_text: event.target.value })} />
                </label>
                <label className="grid gap-2 text-sm text-white/70">
                  Słowa kluczowe
                  <input className="field" value={episodeSpecForm.search_keywords_text} onChange={(event) => setEpisodeSpecForm({ ...episodeSpecForm, search_keywords_text: event.target.value })} />
                </label>
              </div>
              <div className="mt-5 grid gap-3 md:grid-cols-2">
                <button
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-3 font-black text-[var(--ink)] transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
                  type="submit"
                  disabled={!selectedProject || isSavingEpisodeSpec}
                >
                  {isSavingEpisodeSpec ? <Loader2 size={18} className="animate-spin" /> : <Target size={18} />}
                  Zapisz Episode Spec
                </button>
                <button
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--teal)] px-4 py-3 font-black text-[#07110f] transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
                  type="button"
                  onClick={handleApproveEpisodeSpec}
                  disabled={!selectedProject?.episode_spec || isApprovingEpisodeSpec}
                >
                  {isApprovingEpisodeSpec ? <Loader2 size={18} className="animate-spin" /> : <CheckCircle2 size={18} />}
                  Zatwierdź Episode Spec
                </button>
              </div>
            </form>
          </div>

          <div className="mt-4 rounded-2xl border border-white/10 bg-[var(--mist)] p-4 text-[var(--ink)] md:p-5" data-testid="repetition-risk">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-lg font-black">Repetition Risk</p>
                <p className="mt-1 text-sm font-semibold leading-6">
                  {antiRepetitionReport
                    ? `${antiRepetitionReport.status} · score ${antiRepetitionReport.score.toFixed(2)} · compared ${antiRepetitionReport.compared_projects_count}`
                    : "Brak raportu dla tego projektu."}
                </p>
              </div>
              <button
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--ink)] px-4 py-3 text-sm font-black text-white transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                onClick={handleRunAntiRepetition}
                disabled={!selectedProject?.episode_spec || selectedProject.episode_spec.approval_status !== "approved" || isRunningAntiRepetition}
              >
                {isRunningAntiRepetition ? <Loader2 size={16} className="animate-spin" /> : <Target size={16} />}
                Uruchom Anti-Repetition
              </button>
            </div>
            {antiRepetitionReport?.closest_matches.length ? (
              <div className="mt-4 grid gap-2">
                {antiRepetitionReport.closest_matches.map((match) => (
                  <div key={match.project_id} className="rounded-xl bg-black/8 px-3 py-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-black">{match.title}</p>
                      <span className="rounded-full bg-[var(--ink)] px-2 py-1 text-xs font-black text-white">{match.score.toFixed(2)}</span>
                    </div>
                    <p className="mt-1 text-xs font-semibold text-[var(--ink)]/62">{match.reasons.join(", ")}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </article>

        <article className="studio-card rounded-[1.4rem] p-5 md:col-span-7 md:p-7">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <h2 data-testid="selected-project-title" className="text-3xl font-black">
                {selectedProject?.title ?? "Wybierz projekt"}
              </h2>
              <p className="mt-2 text-sm text-white/55">{selectedSummary}</p>
            </div>
            <button
              className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-black text-[var(--ink)] transition hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-50"
              type="button"
              data-testid="run-lyrics-button"
              onClick={() => handleRunStage("lyrics.generate")}
              disabled={!selectedProject || serverProfile?.mode !== "ssh" || runningStage !== null || !canRunLyrics || getStageStatus(selectedProject, "lyrics.generate") !== "pending"}
            >
              {runningStage === "lyrics.generate" ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              Uruchom na serwerze
            </button>
          </div>
          {jobMessage ? (
            <div className="mt-5 rounded-2xl border border-[var(--acid)]/30 bg-[var(--acid)]/12 p-4 text-sm text-[var(--acid)]">
              {jobMessage}
            </div>
          ) : null}
          {error ? <div className="mt-5 rounded-2xl bg-[var(--coral)] p-4 text-sm font-bold text-white">{error}</div> : null}
          <div className="mt-5 rounded-2xl border border-white/10 bg-[var(--mist)] p-4 text-[var(--ink)]" data-testid="next-action">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-black">Następny krok</p>
                <p className="mt-2 text-sm font-semibold leading-6">{nextAction?.message ?? "Wybierz projekt, żeby zobaczyć prowadzenie pipeline."}</p>
              </div>
              {nextAction ? (
                <span className="rounded-full bg-[var(--ink)] px-3 py-1 text-xs font-black uppercase text-white">
                  {nextAction.action_type}
                </span>
              ) : null}
            </div>
          </div>
          <div className="stage-grid mt-7 grid gap-3 md:grid-cols-2">
            {(selectedProject?.pipeline ?? []).map((stage) => (
              <div
                key={stage.stage}
                data-testid={`stage-${stage.stage}`}
                className="stage-card group overflow-hidden rounded-2xl border border-white/10 bg-white/7 p-4 transition hover:border-white/30 hover:bg-white/12"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-bold">{stageLabels[stage.stage] ?? stage.stage}</span>
                  <span className={`status-pill ${statusClass(stage.status)}`}>{statusLabels[stage.status] ?? stage.status}</span>
                </div>
                <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/10">
                  <div
                    className={`h-full rounded-full ${
                      stage.status === "completed"
                        ? "w-full bg-[var(--teal)]"
                        : stage.status === "pending"
                          ? "w-[12%] bg-white/20"
                          : "w-[72%] bg-[var(--acid)]"
                    }`}
                  />
                </div>
                {stage.status === "needs_review" ? (
                  <button
                    className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--acid)] px-3 py-2 text-sm font-black text-[var(--ink)] transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
                    type="button"
                    data-testid={`approve-${stage.stage}`}
                    onClick={() => handleApproveStage(stage.stage)}
                    disabled={approvingStage === stage.stage}
                  >
                    {approvingStage === stage.stage ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
                    Zatwierdź
                  </button>
                ) : null}
                {canRunPipelineStage(selectedProject, stage.stage) ? (
                  <button
                    className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white px-3 py-2 text-sm font-black text-[var(--ink)] transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
                    type="button"
                    data-testid={`run-${stage.stage}`}
                    onClick={() => handleRunStage(stage.stage)}
                    disabled={serverProfile?.mode !== "ssh" || runningStage !== null}
                  >
                    {runningStage === stage.stage ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
                    Serwer
                  </button>
                ) : null}
              </div>
            ))}
          </div>
          <div className="mt-7 rounded-2xl border border-white/10 bg-black/20 p-4" data-testid="artifact-inventory">
            <div className="flex items-center justify-between gap-3">
              <p className="font-black">Rejestr artefaktów</p>
              <span className="status-pill bg-white/10 text-white/70">{artifactInventory.length}</span>
            </div>
            {artifactInventory.length === 0 ? (
              <p className="mt-3 text-sm text-white/45">Manifesty pojawią się po uruchomieniu etapów.</p>
            ) : (
              <div className="mt-4 grid gap-2">
                {artifactInventory.map((artifact) => (
                  <div key={artifact.file_name} className="flex items-center justify-between gap-3 rounded-xl bg-white/7 px-3 py-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-black">{artifact.file_name}</p>
                      <p className="truncate text-xs text-white/42">{artifact.relative_path}</p>
                    </div>
                    <span className="status-pill shrink-0 bg-[var(--teal)] text-[#07110f]">ready</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="mt-4 rounded-2xl border border-white/10 bg-white/7 p-4" data-testid="job-history">
            <div className="flex items-center justify-between gap-3">
              <p className="font-black">Historia jobów</p>
              <span className="status-pill bg-white/10 text-white/70">{projectJobs.length}</span>
            </div>
            {projectJobs.length === 0 ? (
              <p className="mt-3 text-sm text-white/45">Joby pojawią się po uruchomieniu pierwszego etapu.</p>
            ) : (
              <div className="mt-4 grid max-h-72 gap-2 overflow-y-auto pr-1">
                {projectJobs.map((job) => (
                  <div key={job.id} className="grid gap-3 rounded-xl bg-black/24 px-3 py-3 md:grid-cols-[1fr_auto] md:items-center">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-black">{stageLabels[job.stage] ?? job.stage}</p>
                      <p className="truncate text-xs text-white/42">{job.stage} · {job.id}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="status-pill bg-white/10 text-white/64">{job.adapter}</span>
                      <span className={`status-pill ${statusClass(job.status)}`}>{statusLabels[job.status] ?? job.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="mt-4 rounded-2xl border border-white/10 bg-black/20 p-4" data-testid="approval-history">
            <div className="flex items-center justify-between gap-3">
              <p className="font-black">Akceptacje</p>
              <span className="status-pill bg-white/10 text-white/70">{stageApprovals.length}</span>
            </div>
            {stageApprovals.length === 0 ? (
              <p className="mt-3 text-sm text-white/45">Tutaj pojawią się decyzje operatora.</p>
            ) : (
              <div className="mt-4 grid max-h-64 gap-2 overflow-y-auto pr-1">
                {stageApprovals.map((approval) => (
                  <div key={approval.id} className="rounded-xl bg-white/7 px-3 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-black">{stageLabels[approval.stage] ?? approval.stage}</p>
                        <p className="truncate text-xs text-white/42">{approval.stage}</p>
                      </div>
                      <span className="status-pill shrink-0 bg-[var(--teal)] text-[#07110f]">gotowe</span>
                    </div>
                    {approval.note ? <p className="mt-3 text-sm leading-6 text-white/62">{approval.note}</p> : null}
                  </div>
                ))}
              </div>
            )}
          </div>
        </article>

        <article className="studio-card overflow-hidden rounded-[1.4rem] md:col-span-5">
          {publishPackageArtifact ? (
            <div className="p-5 md:p-7" data-testid="publish-package-artifact">
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-3xl font-black">Paczka publikacji</h2>
                  <p className="mt-2 text-sm text-white/52">{publishPackageArtifact.topic} · {publishPackageArtifact.age_range}</p>
                </div>
                <PackageCheck className="text-[var(--acid)]" size={28} />
              </div>
              <div className="rounded-2xl bg-[var(--mist)] p-5 text-[var(--ink)]">
                <p className="text-sm font-black">Status paczki</p>
                <p className="mt-3 text-4xl font-black leading-tight">Ready</p>
                <p className="mt-4 text-sm font-semibold">{publishPackageArtifact.package_path}</p>
              </div>
              {publishPrimaryArtifacts.length ? (
                <div className="mt-4 grid grid-flow-dense grid-cols-1 gap-3 md:grid-cols-2" data-testid="publish-primary-downloads">
                  {publishPrimaryArtifacts.map((artifact) => {
                    const isArchive = artifact.role === "publish_package_zip";
                    const downloadUrl =
                      selectedProject && serverJobDetail
                        ? buildApiUrl(`/api/projects/${selectedProject.id}/jobs/${serverJobDetail.id}/artifacts/${artifact.artifact_id}`)
                        : "";
                    return (
                      <a
                        key={artifact.artifact_id}
                        className={`group overflow-hidden rounded-2xl border transition duration-500 hover:-translate-y-0.5 ${
                          isArchive
                            ? "border-[var(--acid)]/50 bg-[var(--acid)] p-5 text-[#101200] md:col-span-2"
                            : "border-white/10 bg-white/7 p-4 text-white"
                        }`}
                        href={downloadUrl}
                        rel="noreferrer"
                        target="_blank"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="min-w-0">
                            <p className={`text-xs font-black uppercase ${isArchive ? "text-[#101200]/62" : "text-white/42"}`}>
                              {isArchive ? "Finalny ZIP" : artifact.type}
                            </p>
                            <p className="mt-2 truncate text-lg font-black">{fileNameFromPath(artifact.filename)}</p>
                            <p className={`mt-2 text-xs font-bold ${isArchive ? "text-[#101200]/62" : "text-white/45"}`}>
                              {artifact.mime_type} · {formatBytes(artifact.size_bytes)}
                            </p>
                          </div>
                          <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full transition duration-500 group-hover:scale-105 ${isArchive ? "bg-[#101200] text-white" : "bg-white text-[var(--ink)]"}`}>
                            {isArchive ? <Archive size={18} /> : <Download size={18} />}
                          </span>
                        </div>
                      </a>
                    );
                  })}
                </div>
              ) : null}
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/7 p-4">
                <p className="text-sm font-black text-[var(--teal)]">Pliki wyjściowe</p>
                <p className="mt-3 text-sm leading-6 text-white/70">{publishPackageArtifact.episode_output_path}</p>
                <div className="mt-3 space-y-2 text-sm text-white/58">
                  {publishPackageArtifact.reel_output_paths.map((path) => (
                    <p key={path}>{path}</p>
                  ))}
                </div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3">
                {Object.entries(publishPackageArtifact.publishing_metadata).map(([key, value]) => (
                  <div key={key} className="rounded-2xl bg-black/25 p-4">
                    <p className="text-xs font-black uppercase text-white/38">{key}</p>
                    <p className="mt-2 text-sm font-black text-white">{value}</p>
                  </div>
                ))}
              </div>
              <div className="mt-4 rounded-2xl bg-[var(--mist)] p-4 text-[var(--ink)]">
                <p className="text-sm font-black">Manifesty</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {publishPackageArtifact.included_manifests.map((manifest) => (
                    <span key={manifest} className="rounded-full bg-white/70 px-3 py-1 text-xs font-black text-[var(--ink)]">
                      {manifest}
                    </span>
                  ))}
                </div>
              </div>
              <div className="mt-4 rounded-2xl bg-black/25 p-4">
                <p className="text-sm font-black text-[var(--acid)]">Checklist</p>
                <ul className="mt-3 space-y-2 text-sm text-white/68">
                  {publishPackageArtifact.operator_checklist.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : complianceReportArtifact ? (
            <div className="p-5 md:p-7" data-testid="compliance-report-artifact">
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-3xl font-black">Kontrola jakości</h2>
                  <p className="mt-2 text-sm text-white/52">{complianceReportArtifact.topic} · {complianceReportArtifact.age_range}</p>
                </div>
                <ListChecks className="text-[var(--acid)]" size={28} />
              </div>
              <div className="rounded-2xl bg-[var(--mist)] p-5 text-[var(--ink)]">
                <p className="text-sm font-black">Status raportu</p>
                <p className="mt-3 text-3xl font-black leading-tight">Gotowy do akceptacji człowieka</p>
                <p className="mt-4 text-sm font-semibold">{complianceReportArtifact.episode_output_path}</p>
              </div>
              <div className="mt-4 grid gap-3">
                {complianceReportArtifact.checks.map((check) => (
                  <div key={check.id} className="rounded-2xl border border-white/10 bg-white/7 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-black">{check.label}</p>
                      <span className={`status-pill ${check.status === "pass" ? "bg-[var(--teal)] text-[#07110f]" : "bg-[var(--acid)] text-[#101200]"}`}>
                        {check.status === "pass" ? "pass" : "review"}
                      </span>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-white/68">{check.evidence}</p>
                  </div>
                ))}
              </div>
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/7 p-4">
                <p className="text-sm font-black text-[var(--teal)]">Outputy rolek</p>
                <div className="mt-3 space-y-2 text-sm text-white/70">
                  {complianceReportArtifact.reel_output_paths.map((path) => (
                    <p key={path}>{path}</p>
                  ))}
                </div>
              </div>
              <div className="mt-4 rounded-2xl bg-black/25 p-4">
                <p className="text-sm font-black text-[var(--acid)]">Notatki operatora</p>
                <ul className="mt-3 space-y-2 text-sm text-white/68">
                  {complianceReportArtifact.operator_notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : reelsArtifact ? (
            <div className="p-5 md:p-7" data-testid="reels-artifact">
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-3xl font-black">Rolki</h2>
                  <p className="mt-2 text-sm text-white/52">{reelsArtifact.topic} · {reelsArtifact.age_range}</p>
                </div>
                <PanelsTopLeft className="text-[var(--acid)]" size={28} />
              </div>
              <div className="grid gap-4">
                {reelsArtifact.reels.map((reel, index) => (
                  <div key={reel.id} className="group overflow-hidden rounded-2xl border border-white/10 bg-white/7">
                    <div
                      className="min-h-64 bg-cover bg-center p-4 transition-transform duration-700 ease-out group-hover:scale-[1.02]"
                      style={{
                        backgroundImage:
                          `linear-gradient(180deg, rgba(12,12,13,0.04), rgba(12,12,13,0.9)), url(https://picsum.photos/seed/${reel.id}-${reel.source_episode_slug}/720/1100)`
                      }}
                    >
                      <div className="flex flex-wrap gap-2 text-xs font-black">
                        <span className="rounded-full bg-[var(--acid)] px-3 py-1 text-[var(--ink)]">Rolka {index + 1}</span>
                        <span className="rounded-full bg-black/45 px-3 py-1 text-white">{reel.aspect_ratio}</span>
                        <span className="rounded-full bg-black/45 px-3 py-1 text-white">{reel.duration_seconds}s</span>
                      </div>
                      <p className="mt-32 max-w-xs text-2xl font-black leading-tight">{reel.hook}</p>
                    </div>
                    <div className="p-4">
                      <p className="text-sm font-black text-[var(--teal)]">{reel.output_path}</p>
                      <p className="mt-2 text-sm leading-6 text-white/70">{reel.caption}</p>
                      <p className="mt-3 text-xs text-white/45">{reel.safety_note}</p>
                      <div className="mt-4 flex flex-wrap gap-2">
                        {reel.source_scene_ids.map((sceneId) => (
                          <span key={`${reel.id}-${sceneId}`} className="rounded-full border border-white/10 bg-white/8 px-3 py-1 text-xs text-white/60">
                            {sceneId}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 rounded-2xl bg-[var(--mist)] p-4 text-[var(--ink)]">
                <p className="text-sm font-black">Dystrybucja</p>
                <ul className="mt-3 space-y-2 text-sm font-semibold">
                  {reelsArtifact.distribution_notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : fullEpisodeArtifact ? (
            <div className="p-5 md:p-7" data-testid="full-episode-artifact">
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-3xl font-black">Odcinek</h2>
                  <p className="mt-2 text-sm text-white/52">{fullEpisodeArtifact.topic} · {fullEpisodeArtifact.age_range}</p>
                </div>
                <Sparkles className="text-[var(--acid)]" size={28} />
              </div>
              <div
                className="overflow-hidden rounded-2xl border border-white/10 bg-cover bg-center p-5"
                style={{
                  backgroundImage:
                    `linear-gradient(180deg, rgba(12,12,13,0.18), rgba(12,12,13,0.9)), url(https://picsum.photos/seed/${fullEpisodeArtifact.episode_slug}/900/620)`
                }}
              >
                <p className="text-sm font-black text-[var(--acid)]">{fullEpisodeArtifact.episode_slug}</p>
                <p className="mt-28 max-w-sm text-3xl font-black leading-tight">{fullEpisodeArtifact.title}</p>
                <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-2xl bg-black/35 p-3">
                    <p className="text-white/45">Czas</p>
                    <p className="mt-1 font-black">{fullEpisodeArtifact.duration_seconds}s</p>
                  </div>
                  <div className="rounded-2xl bg-black/35 p-3">
                    <p className="text-white/45">Sceny</p>
                    <p className="mt-1 font-black">{fullEpisodeArtifact.scene_count}</p>
                  </div>
                </div>
              </div>
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/7 p-4">
                <p className="text-sm font-black text-[var(--teal)]">Manifest renderu</p>
                <p className="mt-2 text-sm leading-6 text-white/70">{fullEpisodeArtifact.output_path}</p>
                <p className="mt-3 text-xs text-white/45">{fullEpisodeArtifact.audio_mix}</p>
              </div>
              <div className="mt-4 rounded-2xl bg-[var(--mist)] p-4 text-[var(--ink)]">
                <p className="text-sm font-black">Składanie odcinka</p>
                <ul className="mt-3 space-y-2 text-sm font-semibold">
                  {fullEpisodeArtifact.assembly_notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : videoScenesArtifact ? (
            <div className="p-5 md:p-7" data-testid="video-scenes-artifact">
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-3xl font-black">Sceny wideo</h2>
                  <p className="mt-2 text-sm text-white/52">{videoScenesArtifact.topic} · {videoScenesArtifact.age_range}</p>
                </div>
                <Film className="text-[var(--acid)]" size={28} />
              </div>
              <div className="grid gap-4">
                {videoScenesArtifact.scenes.map((scene, index) => (
                  <div key={scene.id} className="group overflow-hidden rounded-2xl border border-white/10 bg-white/7">
                    <div
                      className="min-h-44 bg-cover bg-center p-4 transition-transform duration-700 ease-out group-hover:scale-[1.02]"
                      style={{
                        backgroundImage:
                          `linear-gradient(180deg, rgba(12,12,13,0.05), rgba(12,12,13,0.88)), url(https://picsum.photos/seed/${scene.id}-${scene.source_keyframe_id}/900/560)`
                      }}
                    >
                      <p className="text-sm font-black text-[var(--acid)]">Klip {index + 1} · {scene.duration_seconds}s</p>
                      <p className="mt-20 max-w-sm text-xl font-black leading-tight">{scene.camera_motion}</p>
                    </div>
                    <div className="p-4">
                      <div className="flex flex-wrap gap-2 text-xs text-white/55">
                        <span className="rounded-full border border-white/10 bg-white/8 px-3 py-1">{scene.source_keyframe_id}</span>
                        <span className="rounded-full border border-white/10 bg-white/8 px-3 py-1">{scene.transition}</span>
                      </div>
                      <p className="mt-4 text-sm font-black text-[var(--teal)]">Motion prompt</p>
                      <p className="mt-2 text-sm leading-6 text-white/70">{scene.motion_prompt}</p>
                      <p className="mt-3 text-xs text-white/45">{scene.safety_note}</p>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 rounded-2xl bg-[var(--mist)] p-4 text-[var(--ink)]">
                <p className="text-sm font-black">Notatki renderu</p>
                <ul className="mt-3 space-y-2 text-sm font-semibold">
                  {videoScenesArtifact.render_notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : keyframesArtifact ? (
            <div className="p-5 md:p-7" data-testid="keyframes-artifact">
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-3xl font-black">Keyframes</h2>
                  <p className="mt-2 text-sm text-white/52">{keyframesArtifact.topic} · {keyframesArtifact.age_range}</p>
                </div>
                <Images className="text-[var(--acid)]" size={28} />
              </div>
              <div className="grid gap-4">
                {keyframesArtifact.frames.map((frame, index) => (
                  <div key={frame.id} className="group overflow-hidden rounded-2xl border border-white/10 bg-white/7">
                    <div
                      className="min-h-44 bg-cover bg-center p-4 transition-transform duration-700 ease-out group-hover:scale-[1.02]"
                      style={{
                        backgroundImage:
                          `linear-gradient(180deg, rgba(12,12,13,0.06), rgba(12,12,13,0.86)), url(https://picsum.photos/seed/${frame.id}-${frame.scene_id}/900/560)`
                      }}
                    >
                      <p className="text-sm font-black text-[var(--acid)]">Klatka {index + 1} · {frame.timestamp_seconds}s</p>
                      <p className="mt-20 max-w-sm text-xl font-black leading-tight">{frame.composition}</p>
                    </div>
                    <div className="p-4">
                      <p className="text-sm font-black text-[var(--teal)]">Prompt obrazu</p>
                      <p className="mt-2 text-sm leading-6 text-white/70">{frame.image_prompt}</p>
                      <div className="mt-4 flex flex-wrap gap-2">
                        {frame.palette.map((color) => (
                          <span key={`${frame.id}-${color}`} className="rounded-full border border-white/10 bg-white/8 px-3 py-1 text-xs text-white/60">
                            {color}
                          </span>
                        ))}
                      </div>
                      <p className="mt-3 text-xs text-white/45">{frame.continuity_note}</p>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 rounded-2xl bg-[var(--mist)] p-4 text-[var(--ink)]">
                <p className="text-sm font-black">Spójność wizualna</p>
                <ul className="mt-3 space-y-2 text-sm font-semibold">
                  {keyframesArtifact.consistency_notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : storyboardArtifact ? (
            <div className="p-5 md:p-7" data-testid="storyboard-artifact">
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-3xl font-black">Storyboard</h2>
                  <p className="mt-2 text-sm text-white/52">{storyboardArtifact.topic} · {storyboardArtifact.age_range}</p>
                </div>
                <Clapperboard className="text-[var(--acid)]" size={28} />
              </div>
              <div className="grid gap-4">
                {storyboardArtifact.scenes.map((scene, index) => (
                  <div key={scene.id} className="group overflow-hidden rounded-2xl border border-white/10 bg-white/7">
                    <div
                      className="min-h-36 bg-cover bg-center p-4 transition-transform duration-700 ease-out group-hover:scale-[1.02]"
                      style={{
                        backgroundImage:
                          `linear-gradient(180deg, rgba(12,12,13,0.08), rgba(12,12,13,0.84)), url(https://picsum.photos/seed/${scene.id}/900/520)`
                      }}
                    >
                      <p className="text-sm font-black text-[var(--acid)]">Scena {index + 1} · {scene.duration_seconds}s</p>
                      <p className="mt-16 text-xl font-black leading-tight">{scene.action}</p>
                    </div>
                    <div className="p-4">
                      <p className="text-sm font-black text-[var(--teal)]">Prompt wizualny</p>
                      <p className="mt-2 text-sm leading-6 text-white/70">{scene.visual_prompt}</p>
                      <p className="mt-3 text-xs text-white/45">{scene.camera}</p>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 rounded-2xl bg-[var(--mist)] p-4 text-[var(--ink)]">
                <p className="text-sm font-black">Kontrola bezpieczeństwa</p>
                <ul className="mt-3 space-y-2 text-sm font-semibold">
                  {storyboardArtifact.safety_checks.map((check) => (
                    <li key={check}>{check}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : lyricsArtifact ? (
            <div className="p-5 md:p-7" data-testid="lyrics-artifact">
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-3xl font-black">Podgląd tekstu</h2>
                  <p className="mt-2 text-sm text-white/52">{lyricsArtifact.topic} · {lyricsArtifact.age_range}</p>
                </div>
                <Clapperboard className="text-[var(--acid)]" size={28} />
              </div>
              <div className="rounded-2xl bg-[var(--mist)] p-5 text-[var(--ink)]">
                <p className="text-xs font-black uppercase">Refren</p>
                <div className="mt-4 space-y-2 text-lg font-black leading-snug">
                  {lyricsArtifact.chorus.map((line) => (
                    <p key={line}>{line}</p>
                  ))}
                </div>
              </div>
              <div className="mt-4 grid gap-4">
                {lyricsArtifact.verses.map((verse, index) => (
                  <div key={`verse-${index}`} className="rounded-2xl border border-white/10 bg-white/7 p-4">
                    <p className="text-sm font-black text-[var(--acid)]">Zwrotka {index + 1}</p>
                    <div className="mt-3 space-y-1 text-sm leading-6 text-white/74">
                      {verse.map((line) => (
                        <p key={line}>{line}</p>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/7 p-4">
                <p className="text-sm font-black text-[var(--teal)]">Notatki bezpieczeństwa</p>
                <ul className="mt-3 space-y-2 text-sm text-white/68">
                  {lyricsArtifact.safety_notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : (
            <div
              className="group min-h-[360px] bg-cover bg-center p-7 transition-transform duration-700 ease-out hover:scale-[1.02]"
              style={{
                backgroundImage:
                  "linear-gradient(180deg, rgba(12,12,13,0.1), rgba(12,12,13,0.86)), url(https://picsum.photos/seed/animated-children-music/1000/900)"
              }}
            >
              <Clapperboard className="text-[var(--acid)]" size={30} />
              <p className="pipeline-copy mt-36 max-w-sm text-2xl font-black leading-tight">
                {revealWords.map((word, index) => (
                  <span key={`${word}-${index}`} className="reveal-word inline-block translate-y-2 pr-1.5 opacity-20">
                    {word}
                  </span>
                ))}
              </p>
            </div>
          )}
        </article>
      </section>

      <footer className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-5 py-16 text-sm text-white/55 md:flex-row md:items-center md:justify-between md:px-8">
        <p>Generacje przechodzą przez SSH worker, manifesty i artefakty zapisywane po stronie serwera.</p>
        <div className="flex gap-3">
          <span className="rounded-full border border-white/12 px-3 py-2">FastAPI</span>
          <span className="rounded-full border border-white/12 px-3 py-2">Next.js</span>
          <span className="rounded-full border border-white/12 px-3 py-2">SSH worker</span>
        </div>
      </footer>
    </main>
  );
}
