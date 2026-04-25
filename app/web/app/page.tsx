"use client";

import { useEffect, useMemo, useState } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Activity, ArrowRight, CheckCircle2, Clapperboard, KeyRound, ListMusic, Loader2, Music2, Play, Server, Wand2 } from "lucide-react";
import {
  approveStage,
  createProject,
  fetchProjects,
  fetchServerProfile,
  Project,
  ProjectInput,
  runStage,
  saveServerProfile,
  ServerConnection,
  ServerProfile,
  ServerProfileInput,
  testServerConnection
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
  failed: "błąd"
};

function splitCharacters(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function statusClass(status: string) {
  if (status === "completed") return "bg-[var(--teal)] text-[#07110f]";
  if (status === "needs_review") return "bg-[var(--acid)] text-[#101200]";
  if (status === "failed") return "bg-[var(--coral)] text-white";
  if (status === "running" || status === "queued") return "bg-[var(--violet)] text-white";
  return "bg-white/10 text-white/70";
}

export default function Home() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [connection, setConnection] = useState<ServerConnection | null>(null);
  const [serverProfile, setServerProfile] = useState<ServerProfile | null>(null);
  const [form, setForm] = useState({
    title: "",
    topic: "",
    age_range: "3-5",
    emotional_tone: "radość",
    educational_goal: "",
    characters: "toothbrush_friend_v1"
  });
  const [serverForm, setServerForm] = useState<ServerProfileInput>({
    mode: "mock",
    label: "GPU tower draft",
    host: "gpu-studio.tailnet.local",
    username: "studio",
    port: 22,
    remote_root: "/srv/ai-kids-studio",
    ssh_key_path: "~/.ssh/ai_kids_studio",
    tailscale_name: "gpu-studio"
  });
  const [jobMessage, setJobMessage] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isSavingServer, setIsSavingServer] = useState(false);
  const [approvingStage, setApprovingStage] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadStudio() {
      try {
        const [projectList, server] = await Promise.all([fetchProjects(), testServerConnection()]);
        setProjects(projectList);
        setSelectedProject(projectList[0] ?? null);
        setConnection(server);
        try {
          const profile = await fetchServerProfile();
          setServerProfile(profile);
          setServerForm({
            mode: profile.mode,
            label: profile.label,
            host: profile.host,
            username: profile.username,
            port: profile.port,
            remote_root: profile.remote_root,
            ssh_key_path: profile.ssh_key_path,
            tailscale_name: profile.tailscale_name
          });
        } catch {
          setServerProfile(null);
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

  const selectedSummary = useMemo(() => {
    if (!selectedProject) return "Brak projektu";
    return `${selectedProject.brief.topic} · ${selectedProject.brief.age_range} · ${selectedProject.brief.emotional_tone}`;
  }, [selectedProject]);

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
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się utworzyć projektu.");
    } finally {
      setIsCreating(false);
    }
  }

  async function handleRunLyrics() {
    if (!selectedProject) return;
    setIsRunning(true);
    setError("");
    setJobMessage("");

    try {
      const job = await runStage(selectedProject.id, "lyrics.generate");
      const updatedProjects = await fetchProjects();
      setProjects(updatedProjects);
      setSelectedProject(updatedProjects.find((project) => project.id === selectedProject.id) ?? selectedProject);
      setJobMessage(job.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się uruchomić etapu.");
    } finally {
      setIsRunning(false);
    }
  }

  async function handleSaveServerProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSavingServer(true);
    setError("");

    try {
      const saved = await saveServerProfile(serverForm);
      setServerProfile(saved);
      const server = await testServerConnection();
      setConnection(server);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się zapisać profilu serwera.");
    } finally {
      setIsSavingServer(false);
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
      setJobMessage(`${stageLabels[stage] ?? stage} zatwierdzony.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Nie udało się zatwierdzić etapu.");
    } finally {
      setApprovingStage(null);
    }
  }

  const revealWords = "Pipeline zachowuje kontrakty przyszłego serwera GPU już teraz: kolejka, manifest, status, artefakty i bramka akceptacji człowieka."
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
            <p className="text-xs text-white/48">lokalny tryb mock</p>
          </div>
        </div>
        <button
          className="group flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm text-white transition hover:bg-white hover:text-[var(--ink)]"
          type="button"
          onClick={() => testServerConnection().then(setConnection)}
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
            Pierwszy lokalny kokpit produkcyjny: brief, pipeline, status mock serwera i bramki akceptacji bez czekania na fizyczny GPU.
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
              onClick={handleRunLyrics}
              disabled={!selectedProject || isRunning}
            >
              {isRunning ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              Uruchom tekst
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
              <p className="mt-1 text-sm text-white/52">Brief zapisze się lokalnie w katalogu projektu.</p>
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
            <p className="text-sm font-bold">{connection?.message ?? "Łączenie z mock serwerem..."}</p>
            <p className="mt-5 text-5xl font-black">{connection?.reachable ? "ready" : "wait"}</p>
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
              Zapisz profil
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
                  onClick={() => setSelectedProject(project)}
                >
                  <span className="block text-sm font-bold">{project.title}</span>
                  <span className="mt-1 block text-xs text-white/48">{project.brief.topic}</span>
                </button>
              ))
            )}
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
              onClick={handleRunLyrics}
              disabled={!selectedProject || isRunning}
            >
              {isRunning ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              Uruchom tekst
            </button>
          </div>
          {jobMessage ? (
            <div className="mt-5 rounded-2xl border border-[var(--acid)]/30 bg-[var(--acid)]/12 p-4 text-sm text-[var(--acid)]">
              {jobMessage}
            </div>
          ) : null}
          {error ? <div className="mt-5 rounded-2xl bg-[var(--coral)] p-4 text-sm font-bold text-white">{error}</div> : null}
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
              </div>
            ))}
          </div>
        </article>

        <article className="studio-card overflow-hidden rounded-[1.4rem] md:col-span-5">
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
        </article>
      </section>

      <footer className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-5 py-16 text-sm text-white/55 md:flex-row md:items-center md:justify-between md:px-8">
        <p>Mock adapter dzisiaj. SSH, Tailscale i GPU worker w następnym pionowym wycinku.</p>
        <div className="flex gap-3">
          <span className="rounded-full border border-white/12 px-3 py-2">FastAPI</span>
          <span className="rounded-full border border-white/12 px-3 py-2">Next.js</span>
          <span className="rounded-full border border-white/12 px-3 py-2">Local projects</span>
        </div>
      </footer>
    </main>
  );
}
