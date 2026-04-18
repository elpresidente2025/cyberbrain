"""?? ?? ??? ?? ??? ??."""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from .title_common import (
    SLOT_PLACEHOLDER_NAMES,
    TITLE_LENGTH_HARD_MAX,
    TITLE_LENGTH_HARD_MIN,
    TITLE_LENGTH_OPTIMAL_MAX,
    TITLE_LENGTH_OPTIMAL_MIN,
    are_keywords_similar,
    assess_malformed_title_surface,
    assess_title_focus_name_repetition,
    _compare_title_repeat_signature,
    _detect_truncated_title_reason,
    _title_similarity,
    _filter_required_title_keywords,
    _fit_title_length,
    normalize_title_surface,
    repair_title_focus_name_repetition,
    resolve_title_family,
    extract_numbers_from_content,
)
from .title_family_rules import (
    assess_family_fit,
    family_wants_relationship_voice,
    title_has_any_commitment_signal,
)
from .title_metadata import (
    _contains_date_hint,
    _extract_book_title,
    _extract_date_hint,
    _extract_digit_tokens,
    _normalize_digit_token,
    _normalize_generated_title,
    _normalize_generated_title_without_fit,
    _split_hint_tokens,
    resolve_title_purpose,
)
from .title_keywords import (
    _assess_poll_title_numeric_binding,
    _has_awkward_single_score_question_frame,
    validate_theme_and_content,
)
from .title_repairers import (
    _assess_loyalty_self_certification_title,
    _assess_competitor_intent_title_tail,
    _assess_title_first_person_usage,
    _repair_title_for_missing_keywords,
    _validate_role_keyword_title_policy,
    _validate_user_keyword_title_requirements,
)
from .title_validators import validate_event_announcement_title

_ALLOWED_KEYWORD_SPACE_FOLLOWERS = (
    '경선',
    '경선확정',
    '선거',
    '토론',
    '토론회',
    '방송토론',
    '행사',
    '안내',
    '후보',
    '정책',
    '공약',
)

_NON_EVENT_ANNOUNCEMENT_SURFACE_PATTERNS = (
    re.compile(r'(?:행사|일정)\s*안내', re.IGNORECASE),
    re.compile(r'(?:행사|일정)\s*(?:초대|초청)', re.IGNORECASE),
    re.compile(r'참석\s*요청', re.IGNORECASE),
    re.compile(r'개최\s*안내', re.IGNORECASE),
)



_BODY_ANCHOR_BUCKETS = ('policy', 'institution', 'numeric', 'year')

_COMMITMENT_ENDING_RE = re.compile(
    r'(겠습니다|하겠다|드리겠|드립니다|올립니다|약속드립|앞장서겠|뛰겠습니다|'
    r'지키겠습니다|이루겠습니다|만들겠습니다|책임지겠습니다|완성하겠습니다)\s*[.!]*\s*$'
)
_INTERROGATIVE_CUES_TITLE = ('왜', '무엇', '무슨', '어떻게', '어떤', '어디', '언제', '누가', '얼마', '몇')


def _detect_ending_class_regex_fallback(title: str) -> str:
    """kiwi 불가 시 제목 종결형을 regex 로 분류한다."""
    s = str(title or '').strip()
    if not s:
        return 'other'
    if _COMMITMENT_ENDING_RE.search(s):
        return 'commitment'
    if s.rstrip().endswith('?') or re.search(r'[?？]\s*$', s):
        if any(cue in s for cue in _INTERROGATIVE_CUES_TITLE):
            return 'real_question'
        return 'rhetorical_question'
    if re.search(r'(나요|인가요|인가|는가|는지|을지|까요)\s*$', s):
        if any(cue in s for cue in _INTERROGATIVE_CUES_TITLE):
            return 'real_question'
        return 'rhetorical_question'
    if re.search(r'(합니다|됩니다|입니다|습니다)\s*[.!]*\s*$', s):
        return 'declarative'
    last_token = s.split()[-1] if s.split() else ''
    if re.fullmatch(r'[가-힣]{2,}', last_token) and not re.search(r'(다|요|까|나|지)$', last_token):
        return 'noun_end'
    return 'other'


def _assess_title_ending_constraint(title: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """제목 종결형이 family 아키타입 제약에 부합하는지 평가한다."""
    from .title_prompt_parts import TITLE_ENDING_CONSTRAINTS
    from . import korean_morph

    selected_family = resolve_title_family(params)
    constraint = TITLE_ENDING_CONSTRAINTS.get(selected_family)
    if not constraint:
        return {'passed': True, 'penalty': 0, 'ending_class': '', 'family': selected_family, 'reason': ''}

    normalized = normalize_title_surface(title) or str(title or '').strip()
    ending_info = korean_morph.classify_title_ending(normalized)

    if ending_info is None:
        ending_class = _detect_ending_class_regex_fallback(normalized)
    else:
        ending_class = ending_info.get('class', 'other')

    forbidden = constraint.get('forbidden_endings', [])
    if ending_class in forbidden:
        return {
            'passed': False,
            'penalty': int(constraint.get('penalty_points', 10)),
            'ending_class': ending_class,
            'family': selected_family,
            'reason': constraint.get('forbidden_reason', ''),
        }
    return {'passed': True, 'penalty': 0, 'ending_class': ending_class, 'family': selected_family, 'reason': ''}


def _assess_body_anchor_coverage(title: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """제목이 본문에서 뽑힌 구체 앵커(정책·기관·수치·연도) 중 최소 1개를 인용했는지 검증.

    region 만 포함된 제목은 통과시키지 않는다 — region 은 모든 제목이 기본으로 달고
    있는 틀이라 umbrella 해소의 지표가 되지 못한다. policy/institution/numeric/year
    버킷 중 어느 하나라도 후보가 있을 때만 게이트를 적용하고, 본문이 비어 있어
    후보가 전혀 없으면 skip 한다(프로필 전용 케이스 보호).
    """
    normalized_title = str(title or '').strip()
    if not normalized_title:
        return {'passed': True, 'skipped': True}

    try:
        from .title_hook_quality import (
            extract_slot_opportunities,
            _slot_token_used_in_title,
            _is_body_exclusive,
        )
    except Exception:
        return {'passed': True, 'skipped': True}

    topic = str(params.get('topic') or '')
    stance_text = str(params.get('stanceText') or '')
    content_preview = str(params.get('contentPreview') or '')
    try:
        slots = extract_slot_opportunities(topic, content_preview, params) or {}
    except Exception:
        return {'passed': True, 'skipped': True}

    has_any_candidate = any(
        isinstance(slots.get(bucket), list) and slots.get(bucket)
        for bucket in _BODY_ANCHOR_BUCKETS
    )
    if not has_any_candidate:
        return {'passed': True, 'skipped': True}

    # 🔑 body-exclusive 후보가 글 전체에 하나라도 존재하는지 먼저 파악.
    # 존재 여부는 scorer 의 suggestion 메시지 발동 조건으로 쓰인다
    # (후보는 있는데 제목이 안 썼으면 안내).
    has_body_exclusive_available = False
    for bucket in _BODY_ANCHOR_BUCKETS:
        for tok in (slots.get(bucket) or []):
            if _is_body_exclusive(str(tok or ''), topic, stance_text):
                has_body_exclusive_available = True
                break
        if has_body_exclusive_available:
            break

    # body-exclusive 후보가 전혀 없으면 gate 건너뜀 — 모든 앵커 후보가
    # 사용자 입력(topic/stanceText) 에도 이미 있는 상황이라 "본문 고유 재료"
    # 가 아니다. 이때 score=0 실격은 부당하며, 앵커 포함 여부는
    # bodyAnchorStrength soft scoring 에서 점수에 반영된다.
    if not has_body_exclusive_available:
        return {
            'passed': True,
            'skipped': True,
            'reason': 'body-exclusive 앵커 후보가 없어 게이트 건너뜀',
        }

    hit_buckets: List[str] = []
    hit_tokens: List[str] = []
    for bucket in _BODY_ANCHOR_BUCKETS:
        items = slots.get(bucket) or []
        for token in items:
            token_str = str(token or '').strip()
            if not token_str:
                continue
            if _slot_token_used_in_title(normalized_title, token_str):
                hit_buckets.append(bucket)
                hit_tokens.append(token_str)
                break

    if hit_buckets:
        body_exclusive_hits = [
            tok for tok in hit_tokens
            if _is_body_exclusive(tok, topic, stance_text)
        ]
        return {
            'passed': True,
            'hitBuckets': hit_buckets,
            'hitTokens': hit_tokens,
            'bodyExclusiveHits': body_exclusive_hits,
            'hasBodyExclusiveAvailable': has_body_exclusive_available,
        }

    available = {
        bucket: list((slots.get(bucket) or [])[:3])
        for bucket in _BODY_ANCHOR_BUCKETS
        if slots.get(bucket)
    }
    reason = (
        '제목에 본문 구체 앵커(정책명·법안명·기관명·수치·연도) 가 '
        '하나도 인용되지 않았습니다. 본문에서 뽑힌 후보 중 1개 이상을 '
        '제목 문장에 직접 포함하세요.'
    )
    return {
        'passed': False,
        'reason': reason,
        'available': available,
        'hasBodyExclusiveAvailable': has_body_exclusive_available,
    }


def _repair_third_person_possessive_title_surface(title: str) -> str:
    repaired = normalize_title_surface(str(title or "").strip())
    if not repaired:
        return ""
    repaired = re.sub(r"(?:그의|그녀의)\s*", "", repaired)
    repaired = re.sub(r"선택은\??$", "선택의 이유", repaired)
    repaired = re.sub(r"\s{2,}", " ", repaired)
    repaired = re.sub(r"\s+([,·:;!?])", r"\1", repaired)
    repaired = repaired.strip(" ,·:;!?")
    return repaired


def _detect_non_event_announcement_surface(title: str) -> str:
    normalized = normalize_title_surface(title) or str(title or '').strip()
    if not normalized:
        return ''
    for pattern in _NON_EVENT_ANNOUNCEMENT_SURFACE_PATTERNS:
        match = pattern.search(normalized)
        if match:
            return str(match.group(0) or '').strip()
    return ''


def _assess_title_family_fit(title: str, params: Dict[str, Any]) -> Dict[str, Any]:
    selected_family = resolve_title_family(params)
    normalized = normalize_title_surface(title) or str(title or '').strip()
    return assess_family_fit(normalized, selected_family)

def _assess_initial_title_length_discipline(title: str) -> Dict[str, Any]:
    normalized = normalize_title_surface(title)
    title_length = len(normalized)
    if not normalized:
        return {
            'length': 0,
            'penalty': 0,
            'status': 'empty',
            'requiresRetry': True,
            'inOptimalRange': False,
        }

    if TITLE_LENGTH_OPTIMAL_MIN <= title_length <= TITLE_LENGTH_OPTIMAL_MAX:
        return {
            'length': title_length,
            'penalty': 0,
            'status': 'optimal',
            'requiresRetry': False,
            'inOptimalRange': True,
        }

    if TITLE_LENGTH_HARD_MIN <= title_length < TITLE_LENGTH_OPTIMAL_MIN:
        return {
            'length': title_length,
            'penalty': 8,
            'status': 'short_borderline',
            'requiresRetry': True,
            'inOptimalRange': False,
        }

    long_mid = (TITLE_LENGTH_OPTIMAL_MAX + TITLE_LENGTH_HARD_MAX) // 2
    if TITLE_LENGTH_OPTIMAL_MAX < title_length <= long_mid:
        return {
            'length': title_length,
            'penalty': 6,
            'status': 'long_borderline',
            'requiresRetry': False,
            'inOptimalRange': False,
        }

    if long_mid < title_length <= TITLE_LENGTH_HARD_MAX:
        return {
            'length': title_length,
            'penalty': 10,
            'status': 'long_borderline',
            'requiresRetry': True,
            'inOptimalRange': False,
        }

    return {
        'length': title_length,
        'penalty': 28,
        'status': 'hard_violation',
        'requiresRetry': True,
        'inOptimalRange': False,
    }

def _compute_similarity_penalty(
    title: str,
    previous_titles: List[str],
    threshold: float,
    max_penalty: int,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not title or not previous_titles or max_penalty <= 0:
        return {
            'penalty': 0,
            'maxSimilarity': 0.0,
            'against': '',
            'framePenalty': 0,
            'frameScore': 0,
            'frameAgainst': '',
            'frameReasons': [],
        }

    best_similarity = 0.0
    against = ''
    best_frame_score = 0
    frame_against = ''
    frame_reasons: List[str] = []
    for prev in previous_titles:
        if not prev:
            continue
        similarity = _title_similarity(title, prev)
        if similarity > best_similarity:
            best_similarity = similarity
            against = prev
        frame_meta = _compare_title_repeat_signature(title, prev)
        frame_score = int(frame_meta.get('score') or 0)
        if frame_score > best_frame_score:
            best_frame_score = frame_score
            frame_against = prev
            frame_reasons = list(frame_meta.get('reasons') or [])

    penalty = 0
    if best_similarity >= threshold:
        span = max(0.01, 1.0 - threshold)
        ratio = (best_similarity - threshold) / span
        penalty = max(1, min(max_penalty, int(round(ratio * max_penalty))))

    frame_penalty = 0
    if best_frame_score >= 5:
        frame_penalty = min(max_penalty, 4 + max(0, best_frame_score - 5) * 2)

    # 스타일 수렴 완화: 현재 제목과 "가장 비슷했던 과거 제목"이 모두 같은
    # stylistic family(슬로건/다짐, 관점 등) 이면 고정 어휘 풀 때문에 자연
    # 수렴하는 것이므로 penalty를 절반으로 줄인다. 다른 주제에서 surface만
    # 재활용하는 케이스는 family가 달라 감점이 그대로 유지된다.
    if penalty and against and isinstance(params, dict):
        current_family = resolve_title_family(params)
        current_fit = assess_family_fit(title, current_family)
        past_fit = assess_family_fit(against, current_family)
        if (
            current_fit.get('status') == 'fit'
            and past_fit.get('status') == 'fit'
        ):
            penalty = max(1, penalty // 2)

    total_penalty = min(max_penalty, penalty + frame_penalty)
    return {
        'penalty': total_penalty,
        'maxSimilarity': round(best_similarity, 3),
        'against': against,
        'framePenalty': frame_penalty,
        'frameScore': best_frame_score,
        'frameAgainst': frame_against,
        'frameReasons': frame_reasons,
    }

def calculate_title_quality_score(
    title: str,
    params: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # No try/except blocking logic here. Let it propagate.
    score_options = options if isinstance(options, dict) else {}
    auto_fit_length = bool(score_options.get('autoFitLength', True))
    topic = params.get('topic', '')
    content = params.get('contentPreview', '')
    role_keyword_policy = params.get('roleKeywordPolicy') if isinstance(params.get('roleKeywordPolicy'), dict) else {}
    user_keywords = _filter_required_title_keywords(
        params.get('userKeywords') if isinstance(params.get('userKeywords'), list) else [],
        role_keyword_policy,
    )
    author_name = params.get('fullName', '')
    repaired_title: Optional[str] = None
    keyword_gate_soft_reason = ''
    event_topic_copy_soft_reason = ''
    
    if not title:
        return {'score': 0, 'breakdown': {}, 'passed': False, 'suggestions': ['제목이 없습니다']}
        
    # 0. Critical Failure Checks
    has_html_tag = bool(re.search(r'<\s*/?\s*[a-zA-Z][^>]*>', title))
    has_slot_placeholder = any(f'[{name}]' in title for name in SLOT_PLACEHOLDER_NAMES)
    # 경어체 종결(~입니다/~습니다/~니다)은 문장형 제목의 정상 종결이므로 더 이상 차단하지 않는다.
    # 평서체 종결(~다/~ㄴ다)에 대한 규제는 프롬프트 레벨(sentence_form_honorific rule)에서 수행한다.
    looks_like_content = (
        '여러분' in title or
        has_html_tag or
        has_slot_placeholder or
        len(title) > 50
    )

    if looks_like_content:
        reason = (
            '호칭("여러분") 포함' if '여러분' in title else
            ('HTML 태그 포함' if has_html_tag else
             ('슬롯 플레이스홀더 포함' if has_slot_placeholder else '50자 초과'))
        )
        return {
            'score': 0,
            'breakdown': {'contentPattern': {'score': 0, 'max': 100, 'status': '실패', 'reason': reason}},
            'passed': False,
            'suggestions': [f'제목이 본문처럼 보입니다 ({reason}). 검색어 중심의 간결한 제목으로 다시 작성하세요.']
        }
        
    if '...' in title or '…' in title or title.endswith('..'):
        return {
            'score': 0,
            'breakdown': {'ellipsis': {'score': 0, 'max': 100, 'status': '실패', 'reason': '말줄임표 포함'}},
            'passed': False,
            'suggestions': ['말줄임표("...", "…") 사용 금지. 내용을 자르지 말고 완결된 제목을 작성하세요.']
        }

    truncated_reason = _detect_truncated_title_reason(title)
    if truncated_reason:
        return {
            'score': 0,
            'breakdown': {
                'truncatedTitle': {
                    'score': 0,
                    'max': 100,
                    'status': '실패',
                    'reason': truncated_reason,
                }
            },
            'passed': False,
            'suggestions': [f'제목이 중간에 잘린 것처럼 보입니다 ({truncated_reason}). 완결된 제목으로 다시 작성하세요.'],
        }

    normalized_author = re.sub(r"\s+", "", str(author_name or "")).strip()
    normalized_title = re.sub(r"\s+", "", str(title or "")).strip()
    if normalized_author and ("그의" in title or "그녀의" in title):
        repaired_title = _repair_third_person_possessive_title_surface(title)
        return {
            'score': 0,
            'breakdown': {
                'speakerFocus': {
                    'score': 0,
                    'max': 100,
                    'status': '실패',
                    'reason': '3인칭 소유 표현으로 화자 중심성이 약화됨',
                }
            },
            'passed': False,
            'suggestions': ['제목에서 "그의/그녀의" 같은 3인칭 소유 표현을 제거하고 화자 중심으로 작성하세요.'],
            **({'repairedTitle': repaired_title} if repaired_title and repaired_title != title else {}),
        }

    title_purpose = resolve_title_purpose(topic, params)
    if title_purpose != 'event_announcement':
        event_surface = _detect_non_event_announcement_surface(title)
        if event_surface:
            return {
                'score': 0,
                'breakdown': {
                    'eventSurfaceLeak': {
                        'score': 0,
                        'max': 100,
                        'status': '실패',
                        'reason': f'실제 행사 안내문이 아닌데 행사 안내 표현("{event_surface}")이 포함됨',
                    }
                },
                'passed': False,
                'suggestions': [
                    '행사 공지 글이 아니라면 "행사 안내/일정 안내/참석 요청" 같은 표현을 제목에서 제거하세요.'
                ],
            }
    if title_purpose != 'event_announcement':
        first_person_title = _assess_title_first_person_usage(title, params)
        if not first_person_title.get('passed', True):
            repaired_candidate = str(first_person_title.get("repairedTitle") or "").strip()
            return {
                'score': 0,
                'breakdown': {
                    'firstPersonTitle': {
                        'score': 0,
                        'max': 100,
                        'status': '실패',
                        'reason': str(first_person_title.get('reason') or '메인 제목에 1인칭 표현이 포함됐습니다.'),
                        'matched': str(first_person_title.get('matched') or ''),
                    }
                },
                'passed': False,
                'suggestions': [str(first_person_title.get('reason') or '메인 제목의 1인칭 표현을 제거하세요.')],
                **({'repairedTitle': repaired_candidate} if repaired_candidate else {}),
            }
        loyalty_self_cert_title = _assess_loyalty_self_certification_title(title, params)
        if not loyalty_self_cert_title.get('passed', True):
            repaired_candidate = str(loyalty_self_cert_title.get("repairedTitle") or "").strip()
            return {
                'score': 0,
                'breakdown': {
                    'loyaltySelfCertification': {
                        'score': 0,
                        'max': 100,
                        'status': '실패',
                        'reason': str(
                            loyalty_self_cert_title.get('reason')
                            or '메인 제목에 자기인증 표현이 포함됐습니다.'
                        ),
                        'matched': str(loyalty_self_cert_title.get('matched') or ''),
                    }
                },
                'passed': False,
                'suggestions': [
                    str(
                        loyalty_self_cert_title.get('reason')
                        or '메인 제목의 자기인증 표현을 제거하세요.'
                    )
                ],
                **({'repairedTitle': repaired_candidate} if repaired_candidate else {}),
            }

    family_fit = _assess_title_family_fit(title, params)
    if not family_fit.get('passed', True):
        return {
            'score': 0,
            'breakdown': {
                'titleFamily': {
                    'score': 0,
                    'max': 100,
                    'status': '실패',
                    'reason': str(family_fit.get('reason') or '선택된 제목 패밀리와 표면이 맞지 않습니다.'),
                    'family': str(family_fit.get('family') or ''),
                }
            },
            'passed': False,
            'suggestions': [str(family_fit.get('reason') or '선택된 제목 패밀리에 맞게 다시 작성하세요.')],
        }

    focus_name_validation = assess_title_focus_name_repetition(title, params)
    if not focus_name_validation.get('passed', True):
        repaired_candidate = repair_title_focus_name_repetition(title, params)
        return {
            'score': 0,
            'breakdown': {
                'focusNameRepeat': {
                    'score': 0,
                    'max': 100,
                    'status': '실패',
                    'reason': str(
                        focus_name_validation.get('reason')
                        or '제목에 동일 인물명이 중복되어 의미가 무너집니다.'
                    ),
                    'duplicateNames': list(focus_name_validation.get('duplicateNames') or []),
                }
            },
            'passed': False,
            'suggestions': [
                str(
                    focus_name_validation.get('reason')
                    or '동일 인물명 반복을 제거하고 제목 문장을 다시 완성하세요.'
                )
            ],
            **({'repairedTitle': repaired_candidate} if repaired_candidate else {}),
        }

    malformed_surface = assess_malformed_title_surface(title, params)
    if not malformed_surface.get('passed', True):
        repaired_candidate = str(malformed_surface.get("repairedTitle") or "").strip()
        return {
            'score': 0,
            'breakdown': {
                'malformedSurface': {
                    'score': 0,
                    'max': 100,
                    'status': '실패',
                    'reason': str(
                        malformed_surface.get('reason')
                        or '제목 문장이 비문이거나 토큰이 잘못 결합됐습니다.'
                    ),
                    'issue': str(malformed_surface.get('issue') or ''),
                }
            },
            'passed': False,
            'suggestions': [
                str(
                    malformed_surface.get('reason')
                    or '제목 문장을 자연스러운 의미 단위로 다시 완성하세요.'
                )
            ],
            **({'repairedTitle': repaired_candidate} if repaired_candidate else {}),
        }

    # 0-b. Topic 직복 감지: 주제 텍스트와 지나치게 유사한 제목은 hard fail
    if topic and len(topic) >= 12:
        topic_sim_threshold = 0.85 if title_purpose == 'event_announcement' else 0.75
        topic_sim = _title_similarity(title, topic)
        if topic_sim >= topic_sim_threshold:
            if title_purpose == 'event_announcement':
                distinguishing_tokens = []
                if author_name and author_name in title and author_name not in topic:
                    distinguishing_tokens.append(str(author_name))
                for keyword in user_keywords[:2]:
                    normalized_keyword = str(keyword or '').strip()
                    if (
                        normalized_keyword
                        and normalized_keyword in title
                        and normalized_keyword not in topic
                    ):
                        distinguishing_tokens.append(normalized_keyword)
                if distinguishing_tokens:
                    unique_tokens = list(dict.fromkeys(distinguishing_tokens))
                    event_topic_copy_soft_reason = (
                        '행사형 제목이 주제와 유사하지만 '
                        f'추가 앵커({", ".join(unique_tokens)})를 포함해 허용했습니다.'
                    )
                else:
                    return {
                        'score': 0,
                        'breakdown': {
                            'topicCopy': {
                                'score': 0, 'max': 100, 'status': '실패',
                                'reason': f'주제와 유사도 {topic_sim:.0%} (임계 {topic_sim_threshold:.0%})',
                            },
                        },
                        'passed': False,
                        'suggestions': [
                            '주제(topic) 텍스트를 그대로 제목으로 사용하지 마세요. '
                            '표현과 어순을 새롭게 구성하세요.',
                        ],
                    }
            else:
                return {
                    'score': 0,
                    'breakdown': {
                        'topicCopy': {
                            'score': 0, 'max': 100, 'status': '실패',
                            'reason': f'주제와 유사도 {topic_sim:.0%} (임계 {topic_sim_threshold:.0%})',
                        },
                    },
                    'passed': False,
                    'suggestions': [
                        '주제(topic) 텍스트를 그대로 제목으로 사용하지 마세요. '
                        '표현과 어순을 새롭게 구성하세요.',
                    ],
                }

    if title_purpose == 'event_announcement':
        event_validation = validate_event_announcement_title(title, params)
        if not event_validation.get('passed'):
            return {
                'score': 0,
                'breakdown': {
                    'eventPurpose': {
                        'score': 0,
                        'max': 100,
                        'status': '실패',
                        'reason': str(event_validation.get('reason') or '행사 안내 목적 불일치')
                    }
                },
                'passed': False,
                'suggestions': [str(event_validation.get('reason') or '행사 안내 목적에 맞게 제목을 다시 작성하세요.')]
            }

    competitor_tail_validation = _assess_competitor_intent_title_tail(title, params)
    if not competitor_tail_validation.get('passed', True):
        return {
            'score': 0,
            'breakdown': {
                'competitorIntentTail': {
                    'score': 0,
                    'max': 100,
                    'status': '실패',
                    'reason': str(
                        competitor_tail_validation.get('reason')
                        or '경쟁자 intent 제목의 쉼표 뒤 표현이 상투적입니다.'
                    ),
                    'tail': str(competitor_tail_validation.get('tail') or ''),
                    'forbiddenTokens': list(competitor_tail_validation.get('forbiddenTokens') or []),
                }
            },
            'passed': False,
            'suggestions': [str(competitor_tail_validation.get('reason') or '경쟁자 intent 제목의 쉼표 뒤를 본문 논지로 다시 작성하세요.')],
        }

    keyword_gate = _validate_user_keyword_title_requirements(title, user_keywords)
    if not keyword_gate.get('passed'):
        repaired_candidate = _repair_title_for_missing_keywords(title, keyword_gate, params)
        if repaired_candidate:
            re_gate = _validate_user_keyword_title_requirements(repaired_candidate, user_keywords)
            if re_gate.get('passed'):
                keyword_gate = re_gate
                repaired_title = repaired_candidate
                title = repaired_candidate
            else:
                keyword_reason = str(re_gate.get('reason') or keyword_gate.get('reason') or '사용자 검색어 반영 실패')
                severity = str(re_gate.get('severity') or keyword_gate.get('severity') or '').strip().lower()
                if severity == 'soft':
                    keyword_gate_soft_reason = keyword_reason
                else:
                    return {
                        'score': 0,
                        'breakdown': {
                            'keywordRequirement': {
                                'score': 0,
                                'max': 100,
                                'status': '실패',
                                'reason': keyword_reason,
                            }
                        },
                        'passed': False,
                        'suggestions': [keyword_reason],
                    }
        else:
            keyword_reason = str(keyword_gate.get('reason') or '사용자 검색어 반영 실패')
            severity = str(keyword_gate.get('severity') or '').strip().lower()
            if severity == 'soft':
                keyword_gate_soft_reason = keyword_reason
            else:
                return {
                    'score': 0,
                    'breakdown': {
                        'keywordRequirement': {
                            'score': 0,
                            'max': 100,
                            'status': '실패',
                            'reason': keyword_reason,
                        }
                    },
                        'passed': False,
                        'suggestions': [keyword_reason],
                    }

    role_keyword_gate = _validate_role_keyword_title_policy(title, role_keyword_policy)
    if not role_keyword_gate.get('passed'):
        role_reason = str(role_keyword_gate.get('reason') or '역할형 검색어 제목 정책 위반')
        return {
            'score': 0,
            'breakdown': {
                'roleKeywordPolicy': {
                    'score': 0,
                    'max': 100,
                    'status': '실패',
                    'reason': role_reason,
                }
            },
            'passed': False,
            'suggestions': [role_reason],
        }

    # Body anchor coverage gate — 같은 extract_slot_opportunities 파이프라인으로
    # 본문에서 뽑힌 구체 앵커(정책·기관·수치·연도 버킷) 중 최소 1개가 제목에
    # 실제로 인용됐는지 검증한다. generator 프롬프트의 <available_slots> 와
    # scorer 가 동일한 버킷을 공유하므로, "프롬프트엔 후보가 있는데 제목엔
    # 아무 앵커도 없는" hollow 제목이 자동으로 실격된다.
    #
    # region 은 모든 제목이 달고 있는 기본 틀이라 umbrella 해소 지표가 못 되고,
    # 본문이 비어 있어 후보가 0개면 게이트를 건너뛴다(프로필 전용 케이스).
    # 행사 안내 제목은 일정·장소 전달이 목적이라 적용하지 않는다.
    anchor_coverage: Dict[str, Any] = {'passed': True, 'skipped': True}
    if title_purpose != 'event_announcement':
        anchor_coverage = _assess_body_anchor_coverage(title, params)
        if not anchor_coverage.get('passed', True) and not anchor_coverage.get('skipped'):
            anchor_reason = str(
                anchor_coverage.get('reason')
                or '제목에 본문 구체 앵커가 인용되지 않았습니다.'
            )
            return {
                'score': 0,
                'breakdown': {
                    'bodyAnchorCoverage': {
                        'score': 0,
                        'max': 100,
                        'status': '실격(본문앵커없음)',
                        'reason': anchor_reason,
                        'available': dict(anchor_coverage.get('available') or {}),
                    }
                },
                'passed': False,
                'suggestions': [
                    anchor_reason
                    + ' <available_slots> 의 policy/institution/numeric/year '
                    '버킷에서 본문 고유 토큰 1개 이상을 골라 제목에 직접 넣으세요.'
                ],
            }

    event_anchor_context: Dict[str, Any] = {
        'dateHint': '',
        'bookTitle': '',
        'authorName': '',
    }
    if title_purpose == 'event_announcement':
        context_analysis = params.get('contextAnalysis') if isinstance(params.get('contextAnalysis'), dict) else {}
        must_preserve = context_analysis.get('mustPreserve') if isinstance(context_analysis.get('mustPreserve'), dict) else {}
        event_date = str(must_preserve.get('eventDate') or '').strip()
        event_anchor_context = {
            'dateHint': _extract_date_hint(event_date) or _extract_date_hint(topic),
            'bookTitle': _extract_book_title(topic, params),
            'authorName': str(author_name or '').strip(),
        }
        
    breakdown = {}
    suggestions = []
    title_length = len(title)
    if event_topic_copy_soft_reason:
        suggestions.append(event_topic_copy_soft_reason)

    # 일반 검증 경로에서는 길이 초과를 한 번 축약해볼 수 있지만,
    # 제목 생성 경로에서는 auto_fit_length=False로 두고 초기 생성본을 그대로 평가한다.
    if auto_fit_length and title_length > TITLE_LENGTH_HARD_MAX:
        fitted_title = _fit_title_length(title)
        if fitted_title and fitted_title != title:
            fitted_gate = _validate_user_keyword_title_requirements(fitted_title, user_keywords)
            fitted_severity = str(fitted_gate.get('severity') or '').strip().lower()
            fitted_gate_passed = bool(fitted_gate.get('passed')) or fitted_severity == 'soft'
            if not fitted_gate.get('passed'):
                recovered_title = _repair_title_for_missing_keywords(fitted_title, fitted_gate, params)
                if recovered_title:
                    recovered_gate = _validate_user_keyword_title_requirements(recovered_title, user_keywords)
                    recovered_severity = str(recovered_gate.get('severity') or '').strip().lower()
                    recovered_gate_passed = bool(recovered_gate.get('passed')) or recovered_severity == 'soft'
                    if recovered_gate_passed:
                        fitted_title = recovered_title
                        fitted_gate = recovered_gate
                        fitted_gate_passed = True

            if fitted_gate_passed:
                title = fitted_title
                repaired_title = fitted_title
                title_length = len(title)

    # Hard fail length check
    if title_length < TITLE_LENGTH_HARD_MIN or title_length > TITLE_LENGTH_HARD_MAX:
             return {
            'score': 0,
            'breakdown': {'length': {'score': 0, 'max': 100, 'status': '실패', 'reason': f'{title_length}자 ({TITLE_LENGTH_HARD_MIN}-{TITLE_LENGTH_HARD_MAX}자 필요)'}},
            'passed': False,
            'suggestions': [f'제목이 {title_length}자입니다. {TITLE_LENGTH_HARD_MIN}-{TITLE_LENGTH_HARD_MAX}자 범위로 작성하세요.']
        }

    if keyword_gate_soft_reason:
        breakdown['keywordRequirement'] = {
            'score': 6,
            'max': 10,
            'status': '보완 필요',
            'reason': keyword_gate_soft_reason,
        }
        suggestions.append(keyword_gate_soft_reason)
    else:
        breakdown['keywordRequirement'] = {'score': 10, 'max': 10, 'status': '충족'}

    breakdown['titleFamily'] = {
        'score': int(family_fit.get('score', 8) or 0),
        'max': int(family_fit.get('max', 10) or 10),
        'status': str(family_fit.get('status') or 'fit'),
        'family': str(family_fit.get('family') or ''),
    }
    family_fit_reason = str(family_fit.get('reason') or '').strip()
    if family_fit_reason:
        suggestions.append(family_fit_reason)

    # Archetype ending constraint (soft penalty Phase 1)
    ending_constraint = _assess_title_ending_constraint(title, params)
    if not ending_constraint.get('passed', True):
        _ec_penalty = int(ending_constraint.get('penalty', 10))
        _ec_reason = str(ending_constraint.get('reason') or '')
        breakdown['endingConstraint'] = {
            'score': max(0, 10 - _ec_penalty),
            'max': 10,
            'status': '위반',
            'ending_class': ending_constraint.get('ending_class', ''),
            'family': ending_constraint.get('family', ''),
        }
        if _ec_reason:
            suggestions.append(_ec_reason)
        logger.warning(
            "[TitleScorer] ending_constraint_violation family=%s ending=%s title=%r",
            ending_constraint.get('family', ''),
            ending_constraint.get('ending_class', ''),
            title,
        )
    else:
        breakdown['endingConstraint'] = {
            'score': 10,
            'max': 10,
            'status': '준수',
            'ending_class': ending_constraint.get('ending_class', ''),
        }

    # 1. Length Score (Max 20)
    if TITLE_LENGTH_OPTIMAL_MIN <= title_length <= TITLE_LENGTH_OPTIMAL_MAX:
        breakdown['length'] = {'score': 20, 'max': 20, 'status': '최적'}
    elif TITLE_LENGTH_HARD_MIN <= title_length < TITLE_LENGTH_OPTIMAL_MIN:
        breakdown['length'] = {'score': 12, 'max': 20, 'status': '짧음'}
        suggestions.append(f'제목이 {title_length}자입니다. {TITLE_LENGTH_OPTIMAL_MIN}자 이상 권장.')
    elif TITLE_LENGTH_OPTIMAL_MAX < title_length <= TITLE_LENGTH_HARD_MAX:
        breakdown['length'] = {'score': 12, 'max': 20, 'status': '경계'}
        suggestions.append(f'제목이 {title_length}자입니다. {TITLE_LENGTH_OPTIMAL_MAX}자 이하가 클릭률 최고.')
    else:
        breakdown['length'] = {'score': 0, 'max': 20, 'status': '부적정'}
        suggestions.append(f'제목이 {title_length}자입니다. {TITLE_LENGTH_OPTIMAL_MIN}-{TITLE_LENGTH_OPTIMAL_MAX}자 범위로 작성하세요.')
        
    # 2. Keyword Position (Max 20)
    if user_keywords:
        # Check positions
        keyword_infos = []
        for kw in user_keywords:
            idx = title.find(kw)
            keyword_infos.append({
                'keyword': kw,
                'index': idx,
                'inFront10': 0 <= idx <= 10
            })
            
        any_in_front10 = any(k['inFront10'] for k in keyword_infos)
        any_in_title = any(k['index'] >= 0 for k in keyword_infos)
        front_keyword = next((k['keyword'] for k in keyword_infos if k['inFront10']), '')
        any_keyword = next((k['keyword'] for k in keyword_infos if k['index'] >= 0), '')
        required_pair = [str(kw or '').strip() for kw in user_keywords[:2] if str(kw or '').strip()]
        if (
            len(required_pair) >= 2
            and not are_keywords_similar(required_pair[0], required_pair[1])
        ):
            missing_keywords = [kw for kw in required_pair if title.find(kw) < 0]
            if missing_keywords:
                return {
                    'score': 0,
                    'breakdown': {
                        'keywordCoverage': {
                            'score': 0,
                            'max': 100,
                            'status': '실패',
                            'reason': f'독립 검색어 2개 중 누락: {", ".join(missing_keywords)}',
                            'required': required_pair,
                            'missing': missing_keywords,
                        }
                    },
                    'passed': False,
                    'suggestions': [f'제목에 두 검색어를 모두 포함하세요: {", ".join(required_pair)}'],
                }
        
        # 키워드 뒤 구분자 검증: 쉼표, 물음표, 조사 등으로 분리되어야 함
        # 단, 유사 키워드가 중첩되는 경우(예: "부산 디즈니랜드 유치" / "부산 디즈니랜드")
        # 짧은 키워드의 중간 매칭은 구분자 검증에서 제외한다.
        matched_spans = []
        for info in keyword_infos:
            idx = int(info.get('index', -1))
            keyword = str(info.get('keyword') or '')
            if idx < 0 or not keyword:
                continue
            matched_spans.append({
                'keyword': keyword,
                'start': idx,
                'end': idx + len(keyword),
            })

        kw_delimiter_ok = True
        delimiters = (',', '?', '!', '.', '·', '/', '|', '에', '의', '을', '를', '은', '는', '이', '가', ':', ' ')
        for span in matched_spans:
            is_shadowed = any(
                other['start'] == span['start'] and other['end'] > span['end']
                for other in matched_spans
            )
            if is_shadowed:
                continue

            end_pos = span['end']
            if end_pos >= len(title):
                continue

            next_char = title[end_pos]
            if next_char not in delimiters:
                kw_delimiter_ok = False
                continue

            if next_char == ' ':
                # 공백 뒤에 바로 한글(이름 등)이 오면 구분자 부족
                trailing_text = title[end_pos + 1 : end_pos + 12].strip()
                if any(trailing_text.startswith(token) for token in _ALLOWED_KEYWORD_SPACE_FOLLOWERS):
                    continue
                if end_pos + 1 < len(title) and '\uac00' <= title[end_pos + 1] <= '\ud7a3':
                    kw_delimiter_ok = False

        # 듀얼 키워드 보너스: 1순위 키워드가 제목 시작에 있으면 가산점
        dual_kw_bonus = 0
        if len(user_keywords) >= 2:
            kw1 = user_keywords[0]
            kw1_idx = title.find(kw1)
            kw1_starts_title = 0 <= kw1_idx <= 2  # 제목 맨 앞(0~2자 내)
            if kw1_starts_title:
                dual_kw_bonus = 3

        if any_in_front10:
            score = min(20, max(0, (20 if kw_delimiter_ok else 15) + dual_kw_bonus))
            status = '최적' if kw_delimiter_ok else '최적(구분자 부족)'
            breakdown['keywordPosition'] = {'score': score, 'max': 20, 'status': status, 'keyword': front_keyword}
            if not kw_delimiter_ok:
                suggestions.append(f'키워드 "{front_keyword}" 뒤에 쉼표나 조사를 넣어 다음 단어와 분리하세요. (예: "부산 지방선거, ~")')
        elif any_in_title:
            score = 12
            breakdown['keywordPosition'] = {'score': score, 'max': 20, 'status': '포함됨', 'keyword': any_keyword}
            suggestions.append(f'키워드 "{any_keyword}"를 제목 앞쪽(10자 내)으로 이동하면 SEO 효과 증가.')
        else:
            breakdown['keywordPosition'] = {'score': 0, 'max': 20, 'status': '없음'}
            suggestions.append(f'키워드 중 하나라도 제목에 포함하세요: {", ".join(user_keywords[:2])}')
    else:
        # 사용자가 별도 검색어를 지정하지 않았다면 이 항목은 측정 자체가
        # 불가능하다. max 를 0 으로 돌려 총점 분모에서 제외해, 10점을
        # "그냥 잃는" 구조가 되지 않게 한다. (score 도 0 이므로 합은 유지)
        breakdown['keywordPosition'] = {'score': 0, 'max': 0, 'status': '키워드없음(N/A)'}
             
    # 3. Numbers Score (Max 15)
    has_numbers = bool(re.search(r'\d+(?:억|만원|%|명|건|가구|곳)?', title))
    if has_numbers:
        content_numbers_res = extract_numbers_from_content(content)
        safe_content_numbers = content_numbers_res.get('numbers', [])
        content_number_tokens = [_normalize_digit_token(c_num) for c_num in safe_content_numbers]
        numeric_binding = _assess_poll_title_numeric_binding(topic, content, title)

        allowed_event_tokens: set[str] = set()
        if title_purpose == 'event_announcement':
            allowed_event_tokens.update(_extract_digit_tokens(topic))
            allowed_event_tokens.update(_extract_digit_tokens(event_anchor_context.get('dateHint', '')))

        title_numbers = re.findall(r'\d+(?:억|만원|%|명|건|가구|곳)?', title)
        awkward_single_score = _has_awkward_single_score_question_frame(title)

        # Check if all title numbers exist in content (fuzzy match)
        all_valid = True
        for t_num in title_numbers:
            t_val = _normalize_digit_token(t_num)
            if not t_val:
                continue

            # Check if t_val exists inside any content number OR any content number exists inside t_val
            in_content = any(
                t_val in c_token or c_token in t_val
                for c_token in content_number_tokens
                if c_token
            )
            in_event_hint = t_val in allowed_event_tokens
            if not in_content and not in_event_hint:
                all_valid = False
                break

        if all_valid and numeric_binding.get('passed', True) and not awkward_single_score:
                breakdown['numbers'] = {'score': 15, 'max': 15, 'status': '검증됨'}
        else:
                breakdown['numbers'] = {'score': 5, 'max': 15, 'status': '미검증'}
                if awkward_single_score:
                    suggestions.append('단일 득표율만 떼어 쓰지 말고, 격차 또는 양자대결 수치를 함께 드러내세요.')
                else:
                    suggestions.append(str(numeric_binding.get('reason') or '제목의 숫자가 본문에서 확인되지 않았습니다.'))
    else:
        breakdown['numbers'] = {'score': 8, 'max': 15, 'status': '없음'}
        
    # 4. Topic Match (Max 25)
    if topic:
        theme_val = validate_theme_and_content(topic, content, title, params=params)
        title_topic_score = int(theme_val.get('effectiveTitleScore') or theme_val.get('titleOverlapScore') or theme_val.get('overlapScore') or 0)
        content_topic_score = int(theme_val.get('contentOverlapScore') or theme_val.get('overlapScore') or 0)
        if title_topic_score >= 75:
            breakdown['topicMatch'] = {
                'score': 25,
                'max': 25,
                'status': '높음',
                'overlap': title_topic_score,
                'contentOverlap': content_topic_score,
            }
        elif title_topic_score >= 65:
            breakdown['topicMatch'] = {
                'score': 15,
                'max': 25,
                'status': '보통',
                'overlap': title_topic_score,
                'contentOverlap': content_topic_score,
            }
            if theme_val['mismatchReasons']:
                suggestions.append(theme_val['mismatchReasons'][0])
        else:
            breakdown['topicMatch'] = {
                'score': 5,
                'max': 25,
                'status': '낮음',
                'overlap': title_topic_score,
                'contentOverlap': content_topic_score,
            }
            suggestions.append('제목이 주제와 많이 다릅니다. 주제 핵심어를 반영하세요.')
    else:
        breakdown['topicMatch'] = {'score': 15, 'max': 25, 'status': '주제없음'}
        
    # 5. Author Inclusion (Max 10)
    if author_name:
        selected_family = str(family_fit.get('family') or '').strip().upper()
        prefers_relationship_style = (
            family_wants_relationship_voice(selected_family)
            and not title_has_any_commitment_signal(title)
        )

        if author_name in title:
            escaped_author_name = re.escape(author_name)
            speaker_patterns = [
                f"{escaped_author_name}이 본", f"{escaped_author_name}가 본",
                f"{escaped_author_name}의 평가", f"{escaped_author_name}의 시각",
                f"칭찬한 {escaped_author_name}", f"질타한 {escaped_author_name}",
                f"{escaped_author_name} [\"'`]"
            ]
            has_pattern = any(re.search(p, title) for p in speaker_patterns)

            if prefers_relationship_style:
                if has_pattern:
                    breakdown['authorIncluded'] = {'score': 10, 'max': 10, 'status': '패턴 적용'}
                else:
                    breakdown['authorIncluded'] = {'score': 6, 'max': 10, 'status': '단순 포함'}
                    suggestions.append(f'"{author_name}이 본", "칭찬한 {author_name}" 등 관계형 표현 권장.')
            else:
                breakdown['authorIncluded'] = {'score': 10, 'max': 10, 'status': '포함'}
        else:
            # 행사 안내형 제목은 인물명 누락을 치명 감점으로 보지 않는다.
            if title_purpose == 'event_announcement':
                breakdown['authorIncluded'] = {'score': 6, 'max': 10, 'status': '행사형 예외'}
            elif prefers_relationship_style:
                breakdown['authorIncluded'] = {'score': 0, 'max': 10, 'status': '미포함'}
                suggestions.append(f'화자 "{author_name}"를 제목에 포함하면 브랜딩에 도움됩니다.')
            else:
                breakdown['authorIncluded'] = {'score': 5, 'max': 10, 'status': '선택'}
    else:
        breakdown['authorIncluded'] = {'score': 5, 'max': 10, 'status': '해당없음'}

    # 행사형 제목은 고유 앵커(날짜/인물명/도서명)를 가산해
    # 사용자 few-shot 기반의 구체 제목이 점수에서 불리하지 않도록 보정한다.
    if title_purpose == 'event_announcement':
        anchor_score = 0
        matched_anchors: List[str] = []
        date_hint = str(event_anchor_context.get('dateHint') or '')
        if date_hint and _contains_date_hint(title, date_hint):
            anchor_score += 4
            matched_anchors.append('date')
        book_title = str(event_anchor_context.get('bookTitle') or '').strip()
        if book_title:
            book_tokens = _split_hint_tokens(book_title)
            if book_tokens and any(token in title for token in book_tokens):
                anchor_score += 3
                matched_anchors.append('book')
        author_hint = str(event_anchor_context.get('authorName') or '').strip()
        if author_hint and author_hint in title:
            anchor_score += 3
            matched_anchors.append('author')

        breakdown['eventAnchors'] = {
            'score': min(anchor_score, 10),
            'max': 10,
            'status': '충분' if anchor_score >= 6 else ('보통' if anchor_score >= 3 else '부족'),
            'matched': matched_anchors,
        }
        if anchor_score == 0:
            suggestions.append('행사 고유 정보(날짜/인물명/도서명)를 1개 이상 넣으면 품질 점수가 상승합니다.')

    # 6. Impact (Max 10) - 서사적 긴장감 패턴 포함
    impact_score = 0
    impact_features = []

    if '?' in title or title.endswith('나') or title.endswith('까'):
        impact_score += 3
        impact_features.append('질문/미완결')
    if re.search(r"'.*'|\".*\"", title):
        impact_score += 3
        impact_features.append('인용문')
    if re.search(r"vs|\bvs\b|→|대비", title):
        impact_score += 2
        impact_features.append('대비구조')
    if re.search(r"이 본|가 본", title):
        impact_score += 2
        impact_features.append('관점표현')
    # 서사적 긴장감 패턴
    if re.search(r'(은|는|카드는|답은|선택|한 수|이유)$', title):
        impact_score += 2
        impact_features.append('미완결서사')
    if re.search(r'에서.*까지', title):
        impact_score += 2
        impact_features.append('서사아크')
    if re.search(r'왜\s|어떻게\s', title):
        impact_score += 2
        impact_features.append('원인질문')
    # 정보 과밀 패널티: 실질 요소(2글자 이상 단어)가 7개 이상이면 감점
    substantive_elements = [e for e in re.findall(r'[가-힣A-Za-z0-9]{2,}', title)]
    if len(substantive_elements) >= 7:
        impact_score -= 2
        impact_features.append('정보과밀(-2)')
    if title_purpose == 'event_announcement':
        if any(token in title for token in ('현장', '직접', '일정', '안내', '초대', '만남', '참석')):
            impact_score += 3
            impact_features.append('행사형후킹')

    breakdown['impact'] = {
        'score': min(impact_score, 10),
        'max': 10,
        'status': '있음' if impact_score > 0 else '없음',
        'features': impact_features
    }

    # Body anchor strength — 같은 본문 앵커 게이트를 통과한 후보들 중에서
    # "정말로 구체적인" 앵커(정책명·기관명·연도) 를 인용한 제목이 tiebreaker
    # 에서 이기도록 20점 차원을 추가한다. 구체 앵커가 들어간 제목은 자연히
    # 표면 요소가 많아 impact 의 정보과밀 -2 와 numbers "없음" 감점을 떠안기
    # 때문에, numeric-only 대비 최소 10점 이상 앞서야 tiebreaker 로 기능한다.
    # 본문이 비어 게이트가 skip 된 경우(프로필 전용) 는 max=0 으로 N/A 처리해
    # 점수 상한이 내려가지 않도록 한다.
    if anchor_coverage.get('skipped'):
        breakdown['bodyAnchorStrength'] = {
            'score': 0,
            'max': 0,
            'status': 'N/A',
        }
    else:
        hit_buckets = list(anchor_coverage.get('hitBuckets') or [])
        body_exclusive_hits = list(anchor_coverage.get('bodyExclusiveHits') or [])
        anchor_strength_score = 0
        if 'policy' in hit_buckets:
            anchor_strength_score += 8
        if 'institution' in hit_buckets:
            anchor_strength_score += 6
        if 'year' in hit_buckets:
            anchor_strength_score += 5
        if 'numeric' in hit_buckets:
            anchor_strength_score += 2
        # 🔑 body-exclusive 가산 — topic/stance 에는 없고 본문에서만 발견된
        # 토큰을 실제로 제목에 넣었으면 +6. cap 20 fold-in 이라 max_possible
        # 분모는 불변, tiebreaker 로 기능한다. "테크노밸리"(topic 공유) 만
        # 넣은 제목(policy 8점) vs "도시첨단산업단지"(body-exclusive) 까지
        # 넣은 제목(policy 8 + exclusive 6 = 14점) 이 명확히 갈린다.
        has_body_exclusive_hit = bool(body_exclusive_hits)
        if has_body_exclusive_hit:
            anchor_strength_score += 6
        anchor_strength_score = min(anchor_strength_score, 20)
        if anchor_strength_score >= 12:
            anchor_status = '강함'
        elif anchor_strength_score >= 6:
            anchor_status = '보통'
        else:
            anchor_status = '약함'
        breakdown['bodyAnchorStrength'] = {
            'score': anchor_strength_score,
            'max': 20,
            'status': anchor_status,
            'hitBuckets': hit_buckets,
            'bodyExclusiveHits': body_exclusive_hits,
        }
        if anchor_strength_score <= 2:
            suggestions.append(
                '본문에 정책명·기관명·연도 같은 구체 고유 앵커가 있는데 제목이 '
                '이를 사용하지 않았습니다. 그쪽을 인용하면 점수가 크게 오릅니다.'
            )
        if not has_body_exclusive_hit and anchor_coverage.get('hasBodyExclusiveAvailable'):
            suggestions.append(
                '본문에만 등장하는 고유 정책명·기관명이 있는데 제목은 topic 에 있던 '
                '단어만 재사용했습니다. body_exclusive 토큰 1개를 넣으면 +6점.'
            )

    # Total Score
    total_score = sum(item.get('score', 0) for item in breakdown.values())
    max_possible = sum(item.get('max', 0) for item in breakdown.values())

    # Normalize to 100
    normalized_score = round(total_score / max_possible * 100) if max_possible > 0 else 0

    result = {
        'score': normalized_score,
        'rawScore': total_score,
        'maxScore': max_possible,
        'breakdown': breakdown,
        'passed': normalized_score >= 70,
        'suggestions': suggestions[:3]
    }
    if repaired_title:
        result['repairedTitle'] = repaired_title
    return result
