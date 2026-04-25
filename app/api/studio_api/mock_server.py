from uuid import uuid4

from .models import HUMAN_REVIEW_STAGES, Brief, Job, KeyframeFrame, KeyframesArtifact, LyricsArtifact, ServerConnection, ServerProfile, StageStatus, StoryboardArtifact, StoryboardScene, VideoSceneClip, VideoScenesArtifact, utc_now


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

    def generate_storyboard(self, brief: Brief, lyrics: LyricsArtifact | None = None) -> StoryboardArtifact:
        chorus_anchor = lyrics.chorus[0] if lyrics else f"{brief.topic.capitalize()}, hej, hej, raz i dwa!"
        scenes = [
            StoryboardScene(
                id="scene_01_opening",
                duration_seconds=12,
                lyric_anchor=chorus_anchor,
                action="Bohater wchodzi do jasnego, spokojnego świata i pokazuje temat odcinka.",
                visual_prompt=f"warm 3D children animation, friendly character, topic {brief.topic}, soft color palette, calm pacing",
                camera="Powolny najazd kamery, bez gwałtownych cięć.",
                safety_note="Brak straszenia, agresji i nadmiernego migotania.",
            ),
            StoryboardScene(
                id="scene_02_discovery",
                duration_seconds=16,
                lyric_anchor="Robimy mały krok, a radość z nami gra.",
                action="Postać odkrywa prostą czynność lub pojęcie i zaprasza widza do powtórzenia.",
                visual_prompt=f"cozy animated playroom, educational moment about {brief.topic}, expressive but gentle character gestures",
                camera="Statyczny plan średni z lekkim ruchem bocznym.",
                safety_note="Gesty są bezpieczne do naśladowania przez dziecko.",
            ),
            StoryboardScene(
                id="scene_03_repeat",
                duration_seconds=18,
                lyric_anchor="Tra la la, razem łatwiej każdy dzień,",
                action="Refren wraca w powtarzalnym układzie z czytelnym rytmem ruchu.",
                visual_prompt="repeatable chorus choreography, simple shapes, parent-trustworthy kids content, no sensory overload",
                camera="Szeroki plan z delikatnym kołysaniem.",
                safety_note="Powtarzalność wspiera zapamiętanie, bez presji na dalsze oglądanie.",
            ),
            StoryboardScene(
                id="scene_04_resolution",
                duration_seconds=14,
                lyric_anchor="Śpiewamy jasno, bez pośpiechu, dobry sen.",
                action="Historia zamyka się spokojnym sukcesem i miękkim pożegnaniem.",
                visual_prompt=f"gentle finale, characters smiling, {brief.topic} completed, soft evening light, safe preschool animation",
                camera="Wolne oddalenie, fade do spokojnego koloru.",
                safety_note="Zakończenie jest domknięte i nie zachęca do kompulsywnego oglądania.",
            ),
        ]
        return StoryboardArtifact(
            title=brief.title,
            topic=brief.topic,
            age_range=brief.age_range,
            scenes=scenes,
            safety_checks=[
                "Sceny są spokojne i czytelne dla wieku " + brief.age_range + ".",
                "Brak przemocy, straszenia i niebezpiecznych zachowań.",
                "Historia ma domknięcie i nie używa manipulacyjnych zachęt do oglądania.",
            ],
            created_at=utc_now(),
        )

    def generate_keyframes(self, brief: Brief, storyboard: StoryboardArtifact | None = None) -> KeyframesArtifact:
        scenes = storyboard.scenes if storyboard else self.generate_storyboard(brief).scenes
        frames = [
            KeyframeFrame(
                id=f"keyframe_{index + 1:02d}",
                scene_id=scene.id,
                timestamp_seconds=max(1, min(scene.duration_seconds - 1, scene.duration_seconds // 2)),
                image_prompt=f"{scene.visual_prompt}, single polished keyframe, consistent character design, preschool-safe composition",
                composition=scene.camera,
                palette=["warm coral", "soft teal", "sunlit cream", "gentle violet"],
                continuity_note=f"Keep the same hero proportions and soft expression from {scene.id}.",
            )
            for index, scene in enumerate(scenes)
        ]
        return KeyframesArtifact(
            title=brief.title,
            topic=brief.topic,
            age_range=brief.age_range,
            frames=frames,
            consistency_notes=[
                "Postać ma tę samą sylwetkę, proporcje i paletę w każdej klatce.",
                "Światło pozostaje miękkie, bez ostrych kontrastów i migotania.",
                "Kompozycje zostawiają bezpieczny margines dla napisów i ruchu kamery.",
            ],
            created_at=utc_now(),
        )

    def generate_video_scenes(self, brief: Brief, keyframes: KeyframesArtifact | None = None) -> VideoScenesArtifact:
        frames = keyframes.frames if keyframes else self.generate_keyframes(brief).frames
        scenes = [
            VideoSceneClip(
                id=f"video_scene_{index + 1:02d}",
                scene_id=frame.scene_id,
                source_keyframe_id=frame.id,
                duration_seconds=8 + (index * 2),
                motion_prompt=f"{frame.image_prompt}, gentle motion, soft character animation, no rapid flashes, smooth preschool pacing",
                camera_motion=frame.composition,
                transition="soft dissolve" if index > 0 else "fade in from warm color",
                safety_note="Motion remains calm, readable, and free from strobing.",
            )
            for index, frame in enumerate(frames)
        ]
        return VideoScenesArtifact(
            title=brief.title,
            topic=brief.topic,
            age_range=brief.age_range,
            scenes=scenes,
            render_notes=[
                "Każda scena zachowuje spokojne tempo i miękkie przejścia.",
                "Ruch kamery bazuje na zatwierdzonych keyframes, bez nagłych skoków.",
                "Klipy są gotowe do późniejszego złożenia w pełny odcinek.",
            ],
            created_at=utc_now(),
        )
