from uuid import uuid4

from .models import (
    HUMAN_REVIEW_STAGES,
    Brief,
    FullEpisodeArtifact,
    Job,
    KeyframeFrame,
    KeyframesArtifact,
    LyricsArtifact,
    ReelClip,
    ReelsArtifact,
    ServerConnection,
    ServerProfile,
    StageStatus,
    StoryboardArtifact,
    StoryboardScene,
    VideoSceneClip,
    VideoScenesArtifact,
    utc_now,
)


def _slugify(value: str) -> str:
    normalized = value.lower()
    replacements = {
        "ą": "a",
        "ć": "c",
        "ę": "e",
        "ł": "l",
        "ń": "n",
        "ó": "o",
        "ś": "s",
        "ż": "z",
        "ź": "z",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return "-".join("".join(character if character.isalnum() else " " for character in normalized).split())


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

    def generate_full_episode(self, brief: Brief, video_scenes: VideoScenesArtifact | None = None) -> FullEpisodeArtifact:
        scenes = video_scenes.scenes if video_scenes else self.generate_video_scenes(brief).scenes
        duration_seconds = sum(scene.duration_seconds for scene in scenes)
        episode_slug = _slugify(brief.title)
        return FullEpisodeArtifact(
            title=brief.title,
            topic=brief.topic,
            age_range=brief.age_range,
            episode_slug=episode_slug,
            duration_seconds=duration_seconds,
            scene_count=len(scenes),
            output_path=f"renders/{episode_slug}/full-episode.mp4",
            poster_frame=scenes[0].source_keyframe_id if scenes else "keyframe_01",
            audio_mix="mock stereo mix with gentle limiter and child-safe loudness target",
            assembly_notes=[
                "Sceny są złożone w kolejności storyboardu.",
                "Przejścia używają miękkich dissolve/fade bez gwałtownych błysków.",
                "Manifest jest gotowy jako wejście dla renderów reels i kontroli jakości.",
            ],
            created_at=utc_now(),
        )

    def generate_reels(self, brief: Brief, episode: FullEpisodeArtifact | None = None) -> ReelsArtifact:
        episode_slug = episode.episode_slug if episode else _slugify(brief.title)
        topic = brief.topic.strip()
        reels = [
            ReelClip(
                id="reel_01",
                source_episode_slug=episode_slug,
                source_scene_ids=["scene_01_opening", "scene_02_discovery"],
                duration_seconds=18,
                aspect_ratio="9:16",
                hook=f"{topic.capitalize()} w jednym spokojnym refrenie.",
                output_path=f"renders/{episode_slug}/reel-01.mp4",
                caption=f"Krótka piosenka o: {topic}. Bez pośpiechu, z jasnym domknięciem.",
                safety_note="Rolka nie zawiera presji na dalsze oglądanie ani gwałtownych błysków.",
            ),
            ReelClip(
                id="reel_02",
                source_episode_slug=episode_slug,
                source_scene_ids=["scene_02_discovery", "scene_03_repeat"],
                duration_seconds=20,
                aspect_ratio="9:16",
                hook="Mały krok, prosty rytm i powtórka, którą dziecko łatwo zapamięta.",
                output_path=f"renders/{episode_slug}/reel-02.mp4",
                caption="Wyciąg z edukacyjnej części odcinka, przygotowany do pionowego kadru.",
                safety_note="Gesty są spokojne i bezpieczne do naśladowania przez dziecko.",
            ),
            ReelClip(
                id="reel_03",
                source_episode_slug=episode_slug,
                source_scene_ids=["scene_03_repeat", "scene_04_resolution"],
                duration_seconds=16,
                aspect_ratio="9:16",
                hook="Refren i miękkie zakończenie bez cliffhangera.",
                output_path=f"renders/{episode_slug}/reel-03.mp4",
                caption="Zamknięty fragment z refrenem, gotowy do publikacji jako short.",
                safety_note="Zakończenie jest kompletne i nie używa manipulacyjnych zachęt.",
            ),
        ]
        return ReelsArtifact(
            title=brief.title,
            topic=topic,
            age_range=brief.age_range,
            reels=reels,
            distribution_notes=[
                "Każda rolka ma pionowy kadr 9:16 i mieści się w limicie krótkiego formatu.",
                "Hooki są opisowe, bez obietnic nagród za dalsze oglądanie.",
                "Manifest może być użyty później przez adapter SSH do faktycznego renderu shortów.",
            ],
            created_at=utc_now(),
        )
