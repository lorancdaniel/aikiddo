import re
from uuid import uuid4

from .models import (
    AntiRepetitionMatch,
    AntiRepetitionReport,
    AntiRepetitionSignals,
    Project,
    StoryboardArtifact,
    LyricsArtifact,
    utc_now,
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "dla",
    "do",
    "i",
    "is",
    "oraz",
    "the",
    "to",
    "w",
    "z",
}


def normalize_text(value: str) -> str:
    lowered = value.lower()
    without_punctuation = re.sub(r"[^\w\sąćęłńóśźż-]", " ", lowered, flags=re.UNICODE)
    return re.sub(r"\s+", " ", without_punctuation).strip()


def tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token and token not in STOPWORDS}


def token_overlap(left: str, right: str) -> float:
    left_tokens = tokens(left)
    right_tokens = tokens(right)
    if not left_tokens or not right_tokens:
        return 0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def char_trigrams(value: str) -> set[str]:
    normalized = normalize_text(value).replace(" ", "")
    if len(normalized) < 3:
        return {normalized} if normalized else set()
    return {normalized[index : index + 3] for index in range(len(normalized) - 2)}


def set_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0
    return len(left & right) / len(left | right)


def shingle_similarity(left: str, right: str, size: int = 3) -> float:
    def shingles(value: str) -> set[str]:
        parts = [part for part in normalize_text(value).split() if part not in STOPWORDS]
        if len(parts) < size:
            return set(parts)
        return {" ".join(parts[index : index + size]) for index in range(len(parts) - size + 1)}

    return set_similarity(shingles(left), shingles(right))


def vocabulary_overlap(left: list[str], right: list[str]) -> float:
    left_terms = {normalize_text(term) for term in left if normalize_text(term)}
    right_terms = {normalize_text(term) for term in right if normalize_text(term)}
    if not left_terms or not right_terms:
        return 0
    return len(left_terms & right_terms) / max(len(left_terms), len(right_terms))


def lyrics_text(lyrics: LyricsArtifact | None) -> str:
    if lyrics is None:
        return ""
    lines = lyrics.structure + lyrics.chorus
    for verse in lyrics.verses:
        lines.extend(verse)
    return " ".join(lines)


def storyboard_text(storyboard: StoryboardArtifact | None) -> str:
    if storyboard is None:
        return ""
    return " ".join(f"{scene.action} {scene.visual_prompt} {scene.lyric_anchor}" for scene in storyboard.scenes)


def status_from_score(score: float) -> str:
    if score >= 0.70:
        return "blocker"
    if score >= 0.55:
        return "review_recommended"
    if score >= 0.35:
        return "warning"
    return "ok"


def reasons_from_signals(signals: AntiRepetitionSignals) -> list[str]:
    reasons: list[str] = []
    if (signals.title_similarity or 0) >= 0.55:
        reasons.append("similar title")
    if (signals.topic_similarity or 0) >= 0.55:
        reasons.append("similar topic")
    if (signals.objective_similarity or 0) >= 0.55:
        reasons.append("similar learning objective")
    if (signals.vocabulary_overlap or 0) >= 0.55:
        reasons.append("similar vocabulary")
    if (signals.lyrics_similarity or 0) >= 0.55:
        reasons.append("similar lyrics")
    if (signals.storyboard_similarity or 0) >= 0.55:
        reasons.append("similar storyboard")
    return reasons or ["low similarity"]


def compare_projects(
    current: Project,
    other: Project,
    current_lyrics: LyricsArtifact | None = None,
    other_lyrics: LyricsArtifact | None = None,
    current_storyboard: StoryboardArtifact | None = None,
    other_storyboard: StoryboardArtifact | None = None,
) -> tuple[float, AntiRepetitionSignals]:
    if current.episode_spec is None or other.episode_spec is None:
        return 0, AntiRepetitionSignals()

    current_objective = current.episode_spec.learning_objective
    other_objective = other.episode_spec.learning_objective
    signals = AntiRepetitionSignals(
        title_similarity=set_similarity(char_trigrams(current.episode_spec.working_title), char_trigrams(other.episode_spec.working_title)),
        topic_similarity=token_overlap(current.episode_spec.topic, other.episode_spec.topic),
        objective_similarity=token_overlap(current_objective.statement, other_objective.statement),
        vocabulary_overlap=vocabulary_overlap(current_objective.vocabulary_terms, other_objective.vocabulary_terms),
        lyrics_similarity=shingle_similarity(lyrics_text(current_lyrics), lyrics_text(other_lyrics)),
        storyboard_similarity=shingle_similarity(storyboard_text(current_storyboard), storyboard_text(other_storyboard)),
    )
    score = (
        0.20 * (signals.title_similarity or 0)
        + 0.15 * (signals.topic_similarity or 0)
        + 0.20 * (signals.objective_similarity or 0)
        + 0.20 * (signals.vocabulary_overlap or 0)
        + 0.20 * (signals.lyrics_similarity or 0)
        + 0.05 * (signals.storyboard_similarity or 0)
    )
    return round(score, 3), signals


def build_anti_repetition_report(
    project: Project,
    candidate_projects: list[Project],
    current_lyrics: LyricsArtifact | None = None,
    current_storyboard: StoryboardArtifact | None = None,
    other_lyrics_by_project: dict[str, LyricsArtifact | None] | None = None,
    other_storyboard_by_project: dict[str, StoryboardArtifact | None] | None = None,
) -> AntiRepetitionReport:
    matches: list[AntiRepetitionMatch] = []
    strongest_signals = AntiRepetitionSignals()
    strongest_score = 0.0
    other_lyrics_by_project = other_lyrics_by_project or {}
    other_storyboard_by_project = other_storyboard_by_project or {}

    for candidate in candidate_projects:
        score, signals = compare_projects(
            project,
            candidate,
            current_lyrics=current_lyrics,
            other_lyrics=other_lyrics_by_project.get(candidate.id),
            current_storyboard=current_storyboard,
            other_storyboard=other_storyboard_by_project.get(candidate.id),
        )
        if score > strongest_score:
            strongest_score = score
            strongest_signals = signals
        matches.append(
            AntiRepetitionMatch(
                project_id=candidate.id,
                title=candidate.title,
                score=score,
                reasons=reasons_from_signals(signals),
            )
        )

    sorted_matches = sorted(matches, key=lambda match: match.score, reverse=True)
    return AntiRepetitionReport(
        id=f"anti_repetition_{uuid4().hex[:12]}",
        project_id=project.id,
        series_id=project.series_id,
        status=status_from_score(strongest_score),
        score=round(strongest_score, 3),
        compared_projects_count=len(candidate_projects),
        closest_matches=sorted_matches[:3],
        signals=strongest_signals,
        generated_at=utc_now(),
    )
