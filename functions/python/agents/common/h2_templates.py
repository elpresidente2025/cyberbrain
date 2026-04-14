"""H2 매치업 템플릿 및 결정론 kind 배정 (PR 5).

여론조사·가상대결 글의 H2 세트를 **결정론 템플릿**으로 생성하기 위한 모듈.
SubheadingAgent 의 매치업 모드에서 사용하며, LLM 호출 없이 5-kind 배정을
수행한다 (예산 0 소비). pipeline.py 의 `_apply_poll_focus_contract_once`
(247줄) 를 대체할 수 있는 결정론 경로가 이 모듈이다.

5-kind:
- primary_matchup   — 주요 매치업 (speaker·opponent 양자 대결)
- secondary_matchup — 부가 매치업 (secondaryPairs 중 하나)
- policy            — 정책·비전 해법
- recognition       — 인지도·접점 확대
- closing           — 마무리·다짐

사용 흐름:
    1. `select_matchup_kind_sequence()` — 각 섹션에 어떤 kind 를 부여할지 결정
    2. `build_matchup_heading()` — 해당 kind 의 템플릿으로 H2 문자열 생성
    3. `build_matchup_pair_sentence()` — answer_lead 용 결정론 문장
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "MATCHUP_KIND_IDS",
    "MATCHUP_CONTEST_TOKENS",
    "MATCHUP_POLICY_TOKENS",
    "MATCHUP_RECOGNITION_TOKENS",
    "MATCHUP_CLOSING_TOKENS",
    "MATCHUP_KIND_TEMPLATES",
    "MATCHUP_HEADING_CUES",
    "build_matchup_pair_sentence",
    "build_matchup_heading",
    "score_matchup_kind_candidates",
    "select_matchup_kind_sequence",
]


MATCHUP_KIND_IDS: Tuple[str, ...] = (
    "primary_matchup",
    "secondary_matchup",
    "policy",
    "recognition",
    "closing",
)

# pipeline.py `_apply_poll_focus_contract_once` 에서 사용 중인 토큰 세트와
# 동일 내용. PR 6 에서 pipeline 을 이 모듈로 교체할 때 중복 제거 예정.
MATCHUP_CONTEST_TOKENS: Tuple[str, ...] = (
    "가상대결", "양자대결", "대결", "접전", "경쟁력", "약진",
)
MATCHUP_POLICY_TOKENS: Tuple[str, ...] = (
    "경제", "비전", "정책", "산업", "일자리", "미래", "혁신", "발전",
)
MATCHUP_RECOGNITION_TOKENS: Tuple[str, ...] = (
    "인지도", "알려", "각인", "접점",
)
MATCHUP_CLOSING_TOKENS: Tuple[str, ...] = (
    "함께", "미래", "약속", "마무리", "끝으로",
)

# kind 마다 요구되는 제목 cue — heading alignment 평가에 쓰인다.
MATCHUP_HEADING_CUES: Dict[str, Tuple[str, ...]] = {
    "primary_matchup": ("이유", "배경", "근거"),
    "secondary_matchup": ("경쟁력", "접전", "구도"),
    "policy": ("해법", "정책", "대안"),
    "recognition": ("인지도", "접점", "알려"),
    "closing": ("이유", "주목", "약속", "결심"),
}

# 기본 템플릿. `bundle.allowedH2Kinds[*].template` 이 주입되면 그것이 우선.
# 이 기본 템플릿은 사용자 메타데이터가 없을 때의 결정론 fallback.
# `{speaker}` / `{opponent}` / `{speaker_percent}` / `{opponent_percent}` 자리표시자 지원.
MATCHUP_KIND_TEMPLATES: Dict[str, Dict[str, str]] = {
    "primary_matchup": {
        "template": "{speaker} 대 {opponent}, 이번 매치업의 핵심 배경",
        "template_with_percent": "{speaker_percent} 대 {opponent_percent}, {speaker} 약진의 배경",
    },
    "secondary_matchup": {
        "template": "{opponent} 구도 속 {speaker} 경쟁력 진단",
        "template_with_percent": "{speaker_percent}·{opponent_percent} 경쟁 구도, {speaker} 약진 요인",
    },
    "policy": {
        "template": "{speaker}가 제시한 정책 해법 3가지",
    },
    "recognition": {
        "template": "{speaker} 인지도 확대 전략과 접점",
    },
    "closing": {
        "template": "{speaker}를 주목해야 할 결정적 이유",
    },
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]*>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", str(text))
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def _count_token_hits(text: str, tokens: Sequence[str]) -> int:
    if not text or not tokens:
        return 0
    hits = 0
    for token in tokens:
        token_str = str(token or "").strip()
        if token_str and token_str in text:
            hits += 1
    return hits


def _apply_placeholders(template: str, substitutions: Dict[str, str]) -> str:
    result = str(template or "")
    for key, value in substitutions.items():
        result = result.replace("{" + key + "}", str(value or ""))
    return result.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_matchup_pair_sentence(
    *,
    speaker: str,
    opponent: str,
    speaker_percent: str = "",
    opponent_percent: str = "",
) -> str:
    """`_build_poll_focus_pair_sentence` 와 호환되는 answer_lead 문장.

    percent 정보가 모두 있으면 "{speaker}·{opponent} 가상대결에서는
    {speaker_percent} 대 {opponent_percent}로 나타났습니다." 형태로 생성.
    percent 가 비어 있으면 비결정성을 피하기 위해 빈 문자열 반환.
    """
    s = str(speaker or "").strip()
    o = str(opponent or "").strip()
    sp = str(speaker_percent or "").strip()
    op = str(opponent_percent or "").strip()
    if not (s and o and sp and op):
        return ""
    return f"{s}·{o} 가상대결에서는 {sp} 대 {op}로 나타났습니다."


def build_matchup_heading(
    kind: str,
    *,
    speaker: str,
    opponent: str = "",
    speaker_percent: str = "",
    opponent_percent: str = "",
    template_override: str = "",
) -> str:
    """주어진 kind 의 템플릿을 치환해 H2 inner 문자열을 생성한다.

    `template_override` 가 주어지면 그것이 우선. 없으면 percent 포함 여부로
    `template_with_percent` 또는 `template` 를 선택.
    """
    kind_key = str(kind or "").strip()
    if kind_key not in MATCHUP_KIND_TEMPLATES:
        return ""

    subs = {
        "speaker": str(speaker or "").strip(),
        "opponent": str(opponent or "").strip(),
        "speaker_percent": str(speaker_percent or "").strip(),
        "opponent_percent": str(opponent_percent or "").strip(),
    }
    if not subs["speaker"]:
        return ""

    if template_override:
        return _apply_placeholders(template_override, subs)

    config = MATCHUP_KIND_TEMPLATES[kind_key]
    has_percent = bool(subs["speaker_percent"] and subs["opponent_percent"])
    if has_percent and config.get("template_with_percent"):
        return _apply_placeholders(config["template_with_percent"], subs)
    return _apply_placeholders(config.get("template", ""), subs)


def score_matchup_kind_candidates(
    section_text: str,
    *,
    section_index: int,
    section_count: int,
    primary_opponent: str = "",
    speaker_percent: str = "",
    opponent_percent: str = "",
    secondary_opponents: Optional[Sequence[str]] = None,
    allowed_kind_ids: Optional[Sequence[str]] = None,
) -> Dict[str, int]:
    """섹션 본문에서 kind 후보별 점수를 계산한다 (결정론).

    pipeline.py `_apply_poll_focus_contract_once` 의 점수 로직과 동일 규칙:
    - 마지막 섹션은 closing 에 +120 가산점
    - primary_opponent + 대결 신호 → primary_matchup (percent 병존 시 130, 단일 110)
    - secondary_opponents 중 매칭 → secondary_matchup 100
    - policy/recognition/closing 토큰 hit count 기반 soft score
    """
    text = _strip_html(section_text)
    if not text:
        return {}

    allowed = set(str(item).strip() for item in (allowed_kind_ids or MATCHUP_KIND_IDS))
    scores: Dict[str, int] = {}

    if section_count and section_index == section_count - 1 and "closing" in allowed:
        scores["closing"] = 120

    if "primary_matchup" in allowed and primary_opponent:
        opponent_clean = str(primary_opponent).strip()
        if opponent_clean and opponent_clean in text:
            contest_hit = any(token in text for token in MATCHUP_CONTEST_TOKENS)
            sp = str(speaker_percent or "").strip()
            op = str(opponent_percent or "").strip()
            pct_match = (sp and sp in text) or (op and op in text)
            if contest_hit or pct_match:
                both_pct = bool(sp and op and sp in text and op in text)
                scores["primary_matchup"] = 130 if both_pct else 110

    if "secondary_matchup" in allowed:
        for opponent in (secondary_opponents or ())[:3]:
            candidate = str(opponent or "").strip()
            if not candidate or candidate in {primary_opponent}:
                continue
            if candidate in text:
                contest_hit = any(token in text for token in MATCHUP_CONTEST_TOKENS)
                if contest_hit:
                    scores["secondary_matchup"] = max(
                        scores.get("secondary_matchup", 0), 100
                    )
                    break

    if "policy" in allowed:
        hits = _count_token_hits(text, MATCHUP_POLICY_TOKENS)
        if hits:
            scores["policy"] = max(scores.get("policy", 0), 20 + hits)
    if "recognition" in allowed:
        hits = _count_token_hits(text, MATCHUP_RECOGNITION_TOKENS)
        # recognition 은 policy 점수가 있는 섹션에선 제외 (동일 로직 재현)
        if hits and "policy" not in scores:
            scores["recognition"] = max(scores.get("recognition", 0), 20 + hits)
    if "closing" in allowed:
        hits = _count_token_hits(text, MATCHUP_CLOSING_TOKENS)
        if hits:
            closing_bonus = 15 if section_count and section_index >= section_count - 2 else 0
            scores["closing"] = max(
                scores.get("closing", 0), 20 + hits + closing_bonus
            )

    return scores


def select_matchup_kind_sequence(
    section_texts: Sequence[str],
    *,
    primary_opponent: str = "",
    speaker_percent: str = "",
    opponent_percent: str = "",
    secondary_opponents: Optional[Sequence[str]] = None,
    allowed_kind_ids: Optional[Sequence[str]] = None,
) -> List[str]:
    """여러 섹션에 대해 kind 를 순서대로 배정한다 (used-once 제약).

    같은 kind 를 두 번 쓰지 않고, 점수 ranking → fallback order 순으로 결정.
    """
    total = len(section_texts)
    if total == 0:
        return []

    allowed = list(
        str(item).strip() for item in (allowed_kind_ids or MATCHUP_KIND_IDS)
        if str(item).strip()
    )
    used: set = set()
    assignments: List[str] = []

    for index, section_text in enumerate(section_texts):
        candidates = score_matchup_kind_candidates(
            section_text,
            section_index=index,
            section_count=total,
            primary_opponent=primary_opponent,
            speaker_percent=speaker_percent,
            opponent_percent=opponent_percent,
            secondary_opponents=secondary_opponents,
            allowed_kind_ids=allowed,
        )
        ranked = sorted(
            candidates.items(),
            key=lambda item: (-item[1], item[0]),
        )
        chosen = ""
        for kind, _score in ranked:
            if kind in allowed and kind not in used:
                chosen = kind
                break
        if not chosen:
            if index == 0:
                fallback_order = [
                    "primary_matchup",
                    "policy",
                    "secondary_matchup",
                    "closing",
                    "recognition",
                ]
            elif index == total - 1:
                fallback_order = [
                    "closing",
                    "secondary_matchup",
                    "policy",
                    "recognition",
                ]
            else:
                fallback_order = [
                    "policy",
                    "secondary_matchup",
                    "closing",
                    "recognition",
                ]
            for fallback in fallback_order:
                if fallback in allowed and fallback not in used:
                    chosen = fallback
                    break

        if chosen:
            used.add(chosen)
        assignments.append(chosen)

    return assignments
