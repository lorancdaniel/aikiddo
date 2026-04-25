from uuid import uuid4

from .models import HUMAN_REVIEW_STAGES, Brief, Job, LyricsArtifact, ServerConnection, ServerProfile, StageStatus, utc_now


class MockGpuServer:
    adapter = "mock"

    def test_connection(self, profile: ServerProfile | None = None) -> ServerConnection:
        if profile is not None:
            message = f"Mock GPU server profile '{profile.label}' is ready for local development."
        else:
            message = "Mock GPU server is ready for local development."
        return ServerConnection(
            mode="mock",
            reachable=True,
            message=message,
        )

    def submit_job(self, project_id: str, stage: str) -> Job:
        now = utc_now()
        status = StageStatus.NEEDS_REVIEW if stage in HUMAN_REVIEW_STAGES else StageStatus.COMPLETED
        return Job(
            id=f"job_{uuid4().hex[:12]}",
            project_id=project_id,
            stage=stage,
            status=status,
            adapter="mock",
            message=f"Mock job for {stage} finished locally.",
            created_at=now,
            updated_at=now,
        )

    def generate_lyrics(self, brief: Brief) -> LyricsArtifact:
        topic = brief.topic.strip()
        return LyricsArtifact(
            title=brief.title,
            topic=topic,
            age_range=brief.age_range,
            structure=["zwrotka 1", "refren", "zwrotka 2", "refren"],
            chorus=[
                f"{topic.capitalize()}, hej, hej, raz i dwa!",
                "Robimy mały krok, a radość z nami gra.",
                "Tra la la, razem łatwiej każdy dzień,",
                "Śpiewamy jasno, bez pośpiechu, dobry sen.",
            ],
            verses=[
                [
                    "Rano słonko puka cicho w mały dom,",
                    "Małe ręce wiedzą, gdzie zaczynać chcą.",
                    "Jedna prosta sprawa, potem druga też,",
                    "Kiedy razem nucisz, wszystko łatwe jest.",
                ],
                [
                    "Kolorowy rytm prowadzi nas przez świat,",
                    "Każdy dobry nawyk rośnie tak jak kwiat.",
                    "Mama, tata, uśmiech, spokojniejszy plan,",
                    "Mały bohater mówi: dobrze radę mam.",
                ],
            ],
            rhythm_notes=[
                "Prosty refren do powtórzenia po każdej zwrotce.",
                "Tempo umiarkowane, bez przebodźcowania.",
                "Frazy krótkie, przyjazne dla wieku " + brief.age_range + ".",
            ],
            safety_notes=[
                "Brak straszenia i presji.",
                "Brak zachęt do niebezpiecznych zachowań.",
                "Język prosty i wspierający.",
            ],
            created_at=utc_now(),
        )
