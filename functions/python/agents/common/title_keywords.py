"""?? ??/???/?? ??? ?? ??."""

import re
from typing import Any, Dict, List, Optional

from .title_common import logger
from .title_repairers import _assess_competitor_intent_title_tail
from .title_validators import _assess_poll_focus_title_lane

def _expand_topic_keyword_variants(keyword: str) -> List[str]:
    base = re.sub(r"\s+", "", str(keyword or "")).strip()
    if not base:
        return []

    variants = [base]
    if base == "양자대결":
        variants.extend(["맞대결", "대결"])
    elif base == "우세":
        variants.extend(["우위", "리드", "앞선", "앞섰", "앞서나"])
    elif base == "가능성":
        variants.extend(["경쟁력", "승산", "저력"])
    elif base == "선거":
        variants.extend(["경쟁", "승부", "판세"])
    elif base.endswith("시장"):
        variants.extend([f"{base}선거", f"{base}경쟁"])

    deduped: List[str] = []
    for token in variants:
        cleaned = re.sub(r"\s+", "", str(token or "")).strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped

def _topic_keyword_matches_text(keyword: str, text: str) -> bool:
    normalized_text = re.sub(r"\s+", "", str(text or "")).strip().lower()
    if not normalized_text:
        return False
    return any(variant.lower() in normalized_text for variant in _expand_topic_keyword_variants(keyword))


_SURFACE_TOPIC_PARTICLE_SUFFIXES = (
    "에서",
    "보다",
    "으로",
    "로",
    "에게",
    "까지",
    "부터",
    "처럼",
    "의",
    "을",
    "를",
    "은",
    "는",
    "이",
    "가",
    "와",
    "과",
    "도",
    "만",
    "에",
    "서",
)

_SURFACE_TOPIC_STOPWORDS = {
    "그리고",
    "그러나",
    "하지만",
    "또한",
    "가장",
    "정말",
    "바로",
    "앞으로도",
    "앞으로",
    "지금",
    "이번",
    "위해",
    "위한",
    "통해",
    "대해",
    "대한",
    "관련",
    "역할",
    "해내겠습니다",
    "하겠습니다",
    "합니다",
    "입니다",
}

_SURFACE_TOPIC_SIGNAL_SUFFIXES = (
    "지역구",
    "구민",
    "시민",
    "주민",
    "청년",
    "노동자",
    "소상공인",
    "학부모",
    "의원",
    "국회의원",
    "시의원",
    "도의원",
    "광역시의원",
    "위원장",
    "민주당원",
    "책임감",
    "입법활동",
    "의정활동",
    "조례",
    "예산",
    "성과",
    "활성화",
    "민주주의",
    "현안",
    "정책",
    "해법",
    "변화",
    "개혁",
    "비전",
)


def _normalize_surface_topic_token(token: str) -> str:
    cleaned = re.sub(r"<[^>]*>", " ", str(token or ""))
    cleaned = re.sub(r"[#\"'“”‘’`~()\[\]{}<>]", " ", cleaned)
    cleaned = re.sub(r"[,:;!?./\\|]+", " ", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned).strip()
    if not cleaned:
        return ""

    for suffix in _SURFACE_TOPIC_PARTICLE_SUFFIXES:
        if cleaned.endswith(suffix) and len(cleaned) - len(suffix) >= 2:
            cleaned = cleaned[: -len(suffix)]
            break

    if (
        not cleaned
        or len(cleaned) < 2
        or cleaned in _SURFACE_TOPIC_STOPWORDS
        or cleaned.isdigit()
    ):
        return ""

    if re.search(r"(하겠|합니다|입니다|했다|하였다|되는|된다|되다|해내|한다|하며)$", cleaned):
        return ""

    return cleaned


def _extract_surface_topic_tokens(text: str, *, limit: int = 4) -> List[str]:
    normalized_text = re.sub(r"<[^>]*>", " ", str(text or ""))
    normalized_text = re.sub(r"\s+", " ", normalized_text).strip()
    if not normalized_text:
        return []

    scored_tokens: List[tuple[int, int, str]] = []
    seen: set[str] = set()
    for raw_token in normalized_text.split():
        token = _normalize_surface_topic_token(raw_token)
        if not token or token in seen:
            continue
        seen.add(token)
        priority = 0
        if token.endswith(_SURFACE_TOPIC_SIGNAL_SUFFIXES):
            priority += 5
        if any(marker in token for marker in ("지역구", "구민", "시민", "의원", "책임감", "조례", "성과")):
            priority += 2
        priority += min(len(token), 8)
        scored_tokens.append((priority, len(token), token))

    scored_tokens.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [token for _priority, _length, token in scored_tokens[:limit]]

def extract_topic_keywords(topic: str) -> List[str]:
    topic_text = re.sub(r"\s+", " ", str(topic or "")).strip()
    normalized_topic = re.sub(r"\s+", "", topic_text)
    if not normalized_topic:
        return []

    particle_suffixes = (
        "에서",
        "보다",
        "으로",
        "로",
        "에게",
        "까지",
        "부터",
        "처럼",
        "의",
        "을",
        "를",
        "은",
        "는",
        "이",
        "가",
        "와",
        "과",
        "도",
        "만",
        "에",
        "서",
    )

    def _strip_particle(token: str) -> str:
        cleaned = re.sub(r"\s+", "", str(token or "")).strip()
        for suffix in particle_suffixes:
            if cleaned.endswith(suffix) and len(cleaned) - len(suffix) >= 2:
                return cleaned[: -len(suffix)]
        return cleaned

    def _append_keyword(bucket: List[str], token: str) -> None:
        cleaned = _strip_particle(token)
        if not cleaned:
            return
        if "양자대결" in cleaned:
            cleaned = "양자대결"
        elif any(marker in cleaned for marker in ("우세", "우위", "리드", "앞선", "앞섰")):
            cleaned = "우세"
        elif any(marker in cleaned for marker in ("가능성", "경쟁력", "승산")):
            cleaned = "가능성"
        if len(cleaned) < 2:
            return
        if cleaned not in bucket:
            bucket.append(cleaned)

    keywords: List[str] = []
    role_terms = re.findall(r"[가-힣]{2,10}(?:시장|지사|교육감|구청장|군수|국회의원|의원)", topic_text)
    comparison_names = re.findall(r"([가-힣]{2,4})(?:보다|와|과)", topic_text)
    possessive_names = re.findall(r"([가-힣]{2,4})의", topic_text)
    for token in role_terms[:2]:
        _append_keyword(keywords, token)
    for token in comparison_names[:2]:
        _append_keyword(keywords, token)
    for token in possessive_names[:2]:
        _append_keyword(keywords, token)

    focus_terms = (
        "양자대결",
        "대결",
        "선거",
        "부산시장",
        "시장",
        "지지율",
        "경쟁력",
        "가능성",
        "판세",
        "우세",
        "우위",
        "리드",
    )
    for term in focus_terms:
        if term in normalized_topic:
            _append_keyword(keywords, term)

    if "양자" in normalized_topic and "대결" in normalized_topic:
        _append_keyword(keywords, "양자대결")
    if any(marker in normalized_topic for marker in ("우세", "우위", "리드", "앞선", "앞섰")):
        _append_keyword(keywords, "우세")
    if any(marker in normalized_topic for marker in ("가능성", "경쟁력", "승산")):
        _append_keyword(keywords, "가능성")

    number_matches = re.findall(r"\d+(?:억|만원|%|명|건)?", topic_text)
    for token in number_matches[:2]:
        _append_keyword(keywords, token)

    return keywords[:4]

def _extract_topic_person_names(topic: str) -> List[str]:
    generic_tokens = {
        "선거",
        "양자대결",
        "대결",
        "가상대결",
        "가능성",
        "경쟁력",
        "승산",
        "우세",
        "우위",
        "리드",
        "판세",
        "지지율",
        "부산시장",
        "서울시장",
        "시장",
        "지사",
        "교육감",
        "구청장",
        "군수",
        "국회의원",
        "의원",
        "대표",
        "위원장",
        "후보",
        "예비후보",
        "부산",
        "서울",
        "인천",
        "대구",
        "대전",
        "광주",
        "울산",
        "세종",
        "제주",
        "경기",
        "강원",
        "충북",
        "충남",
        "전북",
        "전남",
        "경북",
        "경남",
    }
    topic_text = re.sub(r"\s+", " ", str(topic or "")).strip()
    if not topic_text:
        return []

    names: List[str] = []

    def _append_name(token: str) -> None:
        cleaned = re.sub(r"\s+", "", str(token or "")).strip()
        if not cleaned or cleaned in generic_tokens:
            return
        if not re.fullmatch(r"[가-힣]{2,4}", cleaned):
            return
        if cleaned not in names:
            names.append(cleaned)

    for token in extract_topic_keywords(topic):
        _append_name(token)

    extra_patterns = (
        r"([가-힣]{2,4})(?=보다)",
        r"([가-힣]{2,4})(?=[와과])",
        r"([가-힣]{2,4})(?=의)",
        r"([가-힣]{2,4})(?=\s*(?:전\s*)?(?:현\s*)?(?:국회의원|의원|시장|지사|교육감|구청장|군수|대표|위원장|후보|예비후보))",
    )
    for pattern in extra_patterns:
        for match in re.findall(pattern, topic_text):
            _append_name(match)

    return names[:3]

def _assess_title_frame_alignment(
    topic: str,
    title: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    topic_text = re.sub(r"\s+", "", str(topic or "")).strip()
    title_text = re.sub(r"\s+", "", str(title or "")).strip()
    if not topic_text or not title_text:
        return {
            "score": 0,
            "style": "",
            "matchedPeople": [],
            "requiredPeople": 0,
            "hasContestContext": False,
            "hasQuestionFrame": False,
            "hasDirectionalFrame": False,
        }

    topic_people = _extract_topic_person_names(topic)
    matched_people = [name for name in topic_people if name in title_text]
    required_people = 2 if len(topic_people) >= 2 else (1 if topic_people else 0)

    contest_tokens = (
        "양자대결",
        "가상대결",
        "맞대결",
        "대결",
        "경쟁",
        "승부",
        "판세",
        "선거",
        "출마",
        "출마론",
        "후보론",
        "거론",
        "시장",
        "부산시장",
        "서울시장",
        "도지사",
        "지사",
        "교육감",
        "구청장",
        "군수",
    )
    question_tokens = (
        "왜",
        "어떻게",
        "무엇",
        "누가",
        "될까",
        "있을까",
        "흔들리나",
        "밀리나",
        "앞섰나",
        "앞서나",
    )
    directional_tokens = (
        "가능성",
        "경쟁력",
        "승산",
        "우세",
        "우위",
        "리드",
        "약진",
        "접전",
        "앞선",
        "앞서",
        "앞섰",
        "보여준",
        "드러난",
        "확인",
        "입증",
    )

    has_contest_context = any(token in title_text for token in contest_tokens)
    has_question_frame = "?" in str(title or "") or any(token in title_text for token in question_tokens)
    has_directional_frame = any(token in title_text for token in directional_tokens)

    if required_people and len(matched_people) < required_people:
        return {
            "score": 0,
            "style": "",
            "matchedPeople": matched_people,
            "requiredPeople": required_people,
            "hasContestContext": has_contest_context,
            "hasQuestionFrame": has_question_frame,
            "hasDirectionalFrame": has_directional_frame,
        }
    if not has_contest_context or not (has_question_frame or has_directional_frame):
        return {
            "score": 0,
            "style": "",
            "matchedPeople": matched_people,
            "requiredPeople": required_people,
            "hasContestContext": has_contest_context,
            "hasQuestionFrame": has_question_frame,
            "hasDirectionalFrame": has_directional_frame,
        }

    score = 60
    if required_people and len(matched_people) >= required_people:
        score += 10
    if has_question_frame:
        score += 10
    if has_directional_frame:
        score += 10
    competitor_tail_validation = _assess_competitor_intent_title_tail(title, params)
    if (
        competitor_tail_validation.get("passed", True)
        and any(token in title_text for token in ("양자대결", "가상대결", "맞대결", "대결", "접전"))
    ):
        score += 5

    style = "aggressive_question" if has_question_frame else "comparison"
    return {
        "score": min(score, 85),
        "style": style,
        "matchedPeople": matched_people,
        "requiredPeople": required_people,
        "hasContestContext": has_contest_context,
        "hasQuestionFrame": has_question_frame,
        "hasDirectionalFrame": has_directional_frame,
    }

def _assess_poll_title_numeric_binding(topic: str, content: str, title: str) -> Dict[str, Any]:
    title_text = str(title or "").strip()
    if "%" not in title_text:
        return {"passed": True, "reason": "", "allowedPercents": [], "pair": []}

    topic_people = _extract_topic_person_names(topic)
    if len(topic_people) < 2:
        return {"passed": True, "reason": "", "allowedPercents": [], "pair": []}

    compact_title = re.sub(r"\s+", "", title_text)
    matched_people = [name for name in topic_people if name and name in compact_title]
    if len(matched_people) < 2:
        return {"passed": True, "reason": "", "allowedPercents": [], "pair": []}

    contest_cues = ("양자대결", "가상대결", "대결", "접전", "승부", "판세", "앞섰", "밀렸", "내줬", "경쟁력")
    if not any(token in title_text or token in str(topic or "") for token in contest_cues):
        return {"passed": True, "reason": "", "allowedPercents": [], "pair": []}

    try:
        from services.posts.poll_fact_guard import build_poll_matchup_fact_table
    except Exception:
        return {"passed": True, "reason": "", "allowedPercents": [], "pair": []}

    poll_fact_table = build_poll_matchup_fact_table([content], known_names=topic_people)
    pairs = poll_fact_table.get("pairs") if isinstance(poll_fact_table, dict) else {}
    if not isinstance(pairs, dict) or not pairs:
        return {"passed": True, "reason": "", "allowedPercents": [], "pair": []}

    selected_pair: Dict[str, Any] = {}
    best_score = -1
    for row in pairs.values():
        if not isinstance(row, dict):
            continue
        left = str(row.get("left") or "").strip()
        right = str(row.get("right") or "").strip()
        if left not in topic_people or right not in topic_people:
            continue
        score = 0
        if left in compact_title:
            score += 2
        if right in compact_title:
            score += 2
        if score > best_score:
            selected_pair = row
            best_score = score

    if not selected_pair:
        return {"passed": True, "reason": "", "allowedPercents": [], "pair": []}

    try:
        left_score = round(float(str(selected_pair.get("leftScore"))), 1)
        right_score = round(float(str(selected_pair.get("rightScore"))), 1)
    except (TypeError, ValueError):
        return {"passed": True, "reason": "", "allowedPercents": [], "pair": []}

    allowed_values = [left_score, right_score, round(abs(left_score - right_score), 1)]
    title_percents = [
        round(float(match), 1)
        for match in re.findall(r"([0-9]{1,2}(?:\.[0-9])?)\s*%", title_text)
    ]
    if not title_percents:
        return {
            "passed": True,
            "reason": "",
            "allowedPercents": allowed_values,
            "pair": [selected_pair.get("left"), selected_pair.get("right")],
        }

    for detected in title_percents:
        if any(abs(detected - allowed) <= 0.05 for allowed in allowed_values):
            continue
        pair_label = f"{selected_pair.get('left')}-{selected_pair.get('right')}"
        allowed_text = ", ".join(f"{value:.1f}%" for value in allowed_values)
        return {
            "passed": False,
            "reason": f'제목의 {detected:.1f}%는 {pair_label} 대결 수치와 연결되지 않습니다. 허용 수치: {allowed_text}',
            "allowedPercents": allowed_values,
            "pair": [selected_pair.get("left"), selected_pair.get("right")],
        }

    return {
        "passed": True,
        "reason": "",
        "allowedPercents": allowed_values,
        "pair": [selected_pair.get("left"), selected_pair.get("right")],
    }

def _has_awkward_single_score_question_frame(title: str) -> bool:
    title_text = str(title or "").strip()
    if not title_text:
        return False

    title_percents = re.findall(r"([0-9]{1,2}(?:\.[0-9])?)\s*%", title_text)
    if len(title_percents) != 1:
        return False
    if re.search(r"\d+(?:\.\d+)?%\s*(?:대|vs|VS|:)", title_text):
        return False
    if not any(token in title_text for token in ("왜", "어떻게", "앞섰", "앞서", "우세", "리드", "밀렸", "접전")):
        return False

    return bool(
        re.search(
            r"[가-힣]{2,8}\s+[0-9]{1,2}(?:\.[0-9])?%\s*(?:왜|어떻게|앞섰|앞서|우세|리드|밀렸)",
            title_text,
            re.IGNORECASE,
        )
    )

def _has_unsupported_reversal_frame(title: str) -> bool:
    title_text = str(title or "").strip()
    if not title_text:
        return False

    reversal_tokens = (
        "뒤집나",
        "뒤집을까",
        "뒤집을까?",
        "뒤집혔나",
        "뒤집혔을까",
        "역전하나",
        "역전할까",
        "역전했나",
        "역전당했나",
        "반전하나",
    )
    if not any(token in title_text for token in reversal_tokens):
        return False

    support_tokens = (
        "열세",
        "밀리던",
        "추격",
        "추격전",
        "만회",
        "좁히",
        "따라붙",
        "판세",
        "흐름",
        "역전승",
        "반전 카드",
    )
    return not any(token in title_text for token in support_tokens)

def _has_broken_numeric_subject_frame(title: str) -> bool:
    title_text = str(title or "").strip()
    if not title_text:
        return False
    return bool(
        re.search(
            r"\d+(?:\.\d+)?%\s*(?:가|를|을)\s*(?:흔들리|흔들렸|밀리|밀렸|앞서|앞섰|뒤집|역전|반전|내줬|내준)",
            title_text,
            re.IGNORECASE,
        )
    )

def validate_theme_and_content(
    topic: str,
    content: str,
    title: str = '',
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        if not topic or not content:
            return {
                'isValid': False,
                'mismatchReasons': ['주제 또는 본문이 비어 있습니다'],
                'topicKeywords': [],
                'contentKeywords': [],
                'overlapScore': 0,
                'contentOverlapScore': 0,
                'titleOverlapScore': 0,
                'effectiveTitleScore': 0,
            }

        topic_keywords = extract_topic_keywords(topic)
        using_surface_topic_fallback = False
        if not topic_keywords:
            topic_keywords = _extract_surface_topic_tokens(topic, limit=4)
            using_surface_topic_fallback = bool(topic_keywords)
        content_text = str(content or '')
        params_dict = params if isinstance(params, dict) else {}
        matched_keywords = []
        missing_keywords = []

        for kw in topic_keywords:
            if _topic_keyword_matches_text(kw, content_text):
                matched_keywords.append(kw)
            else:
                missing_keywords.append(kw)

        content_overlap_score = round(len(matched_keywords) / len(topic_keywords) * 100) if topic_keywords else 0
        mismatch_reasons = []
        title_matched_keywords: List[str] = []
        title_missing: List[str] = []
        title_overlap_score = 0
        effective_title_score = content_overlap_score
        frame_alignment_meta: Dict[str, Any] = {
            "score": 0,
            "style": "",
            "matchedPeople": [],
            "requiredPeople": 0,
            "hasContestContext": False,
            "hasQuestionFrame": False,
            "hasDirectionalFrame": False,
        }

        if topic_keywords and content_overlap_score < 50:
            mismatch_reasons.append(f"주제 핵심어 중 {len(missing_keywords)}개가 본문에 없음: {', '.join(missing_keywords)}")

        if title:
            title_text = str(title or '')
            for kw in topic_keywords:
                if _topic_keyword_matches_text(kw, title_text):
                    title_matched_keywords.append(kw)
                else:
                    title_missing.append(kw)
            title_overlap_score = round(len(title_matched_keywords) / len(topic_keywords) * 100) if topic_keywords else 0
            effective_title_score = round((title_overlap_score * 0.8) + (content_overlap_score * 0.2))
            frame_alignment_meta = _assess_title_frame_alignment(topic, title_text, params_dict)
            effective_title_score = max(
                effective_title_score,
                int(frame_alignment_meta.get("score") or 0),
            )
            competitor_tail_validation = _assess_competitor_intent_title_tail(title_text, params_dict)
            if not competitor_tail_validation.get("passed", True):
                effective_title_score = min(effective_title_score, 35)
                mismatch_reasons.append(
                    str(
                        competitor_tail_validation.get("reason")
                        or "경쟁자 intent 제목의 쉼표 뒤에는 본문 논지가 와야 합니다."
                    )
                )
            if _has_unsupported_reversal_frame(title_text):
                effective_title_score = min(effective_title_score, 55)
                mismatch_reasons.append("제목에 역전 전제가 부족합니다. 열세·추격 같은 근거 없이 '뒤집나/역전하나' 표현을 쓰지 마세요.")
            poll_focus_lane = _assess_poll_focus_title_lane(title_text, params_dict)
            if not poll_focus_lane.get("passed", True):
                effective_title_score = min(effective_title_score, 35)
                mismatch_reasons.append(str(poll_focus_lane.get("reason") or "poll focus 제목 레인과 맞지 않습니다."))
            if _has_broken_numeric_subject_frame(title_text):
                effective_title_score = min(effective_title_score, 45)
                mismatch_reasons.append("제목에서 수치가 주어처럼 흔들리거나 밀리는 표현은 사용할 수 없습니다.")
            if _has_awkward_single_score_question_frame(title_text):
                effective_title_score = min(effective_title_score, 45)
                mismatch_reasons.append("제목에서 단일 득표율만 떼어 '왜 앞섰나'처럼 쓰지 말고, 격차나 양자 수치를 함께 드러내세요.")
            numeric_binding = _assess_poll_title_numeric_binding(topic, content_text, title_text)
            if not numeric_binding.get("passed", True):
                effective_title_score = min(effective_title_score, 40)
                mismatch_reasons.append(str(numeric_binding.get("reason") or "제목 수치가 대결 문맥과 맞지 않습니다."))
            if (
                topic_keywords
                and len(title_missing) > len(topic_keywords) * 0.5
                and int(frame_alignment_meta.get("score") or 0) < 70
            ):
                mismatch_reasons.append(f"제목에 주제 핵심어 부족: {', '.join(title_missing[:3])}")

        return {
            'isValid': effective_title_score >= 50 and not mismatch_reasons,
            'mismatchReasons': mismatch_reasons,
            'topicKeywords': topic_keywords,
            'matchedKeywords': matched_keywords,
            'missingKeywords': missing_keywords,
            'titleMatchedKeywords': title_matched_keywords,
            'titleMissingKeywords': title_missing,
            'overlapScore': content_overlap_score,
            'contentOverlapScore': content_overlap_score,
            'titleOverlapScore': title_overlap_score,
            'effectiveTitleScore': effective_title_score,
            'frameAlignmentScore': int(frame_alignment_meta.get("score") or 0),
            'frameAlignmentStyle': str(frame_alignment_meta.get("style") or ""),
            'frameMatchedPeople': list(frame_alignment_meta.get("matchedPeople") or []),
            'usedSurfaceTopicFallback': using_surface_topic_fallback,
            'pollFocusTitleLane': str(poll_focus_lane.get("lane") or "") if title else "",
        }
    except Exception as exc:
        logger.exception("[TitleGen] validate_theme_and_content 실패: %s", exc)
        return {
            'isValid': False,
            'topicKeywords': [],
            'matchedKeywords': [],
            'missingKeywords': [],
            'titleMatchedKeywords': [],
            'titleMissingKeywords': [],
            'overlapScore': 0,
            'contentOverlapScore': 0,
            'titleOverlapScore': 0,
            'effectiveTitleScore': 0,
            'frameAlignmentScore': 0,
            'frameAlignmentStyle': 'error',
            'frameMatchedPeople': [],
            'usedSurfaceTopicFallback': False,
            'pollFocusTitleLane': '',
            'mismatchReasons': ['제목-본문 정합성 검증 중 오류가 발생했습니다.'],
        }
