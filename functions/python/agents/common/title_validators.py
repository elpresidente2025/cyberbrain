"""?? ?? ?? ??."""

import re
from typing import Any, Dict, List

from .role_keyword_policy import (
    build_role_keyword_intent_anchor_text,
    is_role_keyword_intent_surface,
)
from .title_common import (
    EVENT_NAME_MARKERS,
    _filter_required_title_keywords,
    are_keywords_similar,
)
from .title_metadata import (
    _contains_date_hint,
    _extract_book_title,
    _extract_date_hint,
    _split_hint_tokens,
)
from .title_repairers import _assess_competitor_intent_title_tail

def _assess_poll_focus_title_lane(title: str, params: Dict[str, Any]) -> Dict[str, Any]:
    bundle = params.get('pollFocusBundle') if isinstance(params.get('pollFocusBundle'), dict) else {}
    if str(bundle.get('scope') or '').strip().lower() != 'matchup':
        return {'passed': True, 'lane': '', 'reason': ''}

    primary_pair = bundle.get('primaryPair') if isinstance(bundle.get('primaryPair'), dict) else {}
    speaker = str(primary_pair.get('speaker') or '').strip()
    opponent = str(primary_pair.get('opponent') or '').strip()
    speaker_percent = str(primary_pair.get('speakerPercent') or '').strip()
    opponent_percent = str(primary_pair.get('opponentPercent') or '').strip()
    if not speaker or not opponent:
        return {'passed': True, 'lane': '', 'reason': ''}

    normalized_title = re.sub(r'\s+', '', str(title or ''))
    allowed_lanes = bundle.get('allowedTitleLanes') if isinstance(bundle.get('allowedTitleLanes'), list) else []
    allowed_lane_ids = {
        str(item.get('id') or '').strip()
        for item in allowed_lanes
        if isinstance(item, dict) and str(item.get('id') or '').strip()
    }
    if not allowed_lane_ids:
        allowed_lane_ids = {'intent_fact', 'fact_direct', 'contest_observation'}

    has_pair_names = speaker in normalized_title and opponent in normalized_title
    has_pair_score = bool(speaker_percent and opponent_percent and speaker_percent in title and opponent_percent in title)
    has_contest = any(token in title for token in ('가상대결', '양자대결', '대결', '접전', '경쟁력'))
    has_intent = any(token in title for token in ('출마', '출마론', '거론', '구도', '변수'))
    has_soft_direction = any(token in title for token in ('접전', '경쟁력', '약진', '우세', '앞서', '앞선'))
    has_reversal = bool(re.search(r'(역전|뒤집|흔들리|밀리|휘청|내줬|역전당)', title))
    competitor_tail_validation = _assess_competitor_intent_title_tail(title, params)

    lane = 'unknown'
    if has_intent and (has_pair_score or has_contest or has_pair_names):
        lane = 'intent_fact'
    elif has_pair_score or (has_pair_names and has_contest):
        lane = 'fact_direct'
    elif has_pair_names and has_soft_direction:
        lane = 'contest_observation'

    if has_reversal:
        return {
            'passed': False,
            'lane': lane,
            'reason': 'poll focus 기준 제목은 역전·뒤집힘 같은 판세 전환형 표현 대신 접전·경쟁력 수준으로 서술해야 합니다.',
        }
    if not competitor_tail_validation.get('passed', True):
        return {
            'passed': False,
            'lane': lane,
            'reason': str(competitor_tail_validation.get('reason') or '경쟁자 intent 제목의 쉼표 뒤 표현이 상투적입니다.'),
        }
    if lane == 'unknown' or lane not in allowed_lane_ids:
        return {
            'passed': False,
            'lane': lane,
            'reason': 'poll focus 기준 허용된 제목 레인(intent_fact, fact_direct, contest_observation) 안에서 제목을 구성해야 합니다.',
        }
    return {'passed': True, 'lane': lane, 'reason': ''}

def validate_event_announcement_title(title: str, params: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = (title or '').strip()
    if not cleaned:
        return {'passed': False, 'reason': '제목이 비어 있습니다.'}

    topic = str(params.get('topic') or '')
    context_analysis = params.get('contextAnalysis') if isinstance(params.get('contextAnalysis'), dict) else {}
    role_keyword_policy = params.get('roleKeywordPolicy') if isinstance(params.get('roleKeywordPolicy'), dict) else {}
    user_keywords = _filter_required_title_keywords(
        params.get('userKeywords') if isinstance(params.get('userKeywords'), list) else [],
        role_keyword_policy,
    )

    banned_phrases = (
        '진짜 속내',
        '왜 왔냐',
        '답할까',
        '속내는',
        '의혹',
        '논란',
    )
    # Kiwi-first: 수사적 반문 어미(물음표 없는 "완성할까"/"이뤄낼까" 변형 포함) 는
    # 이벤트 안내와 맞지 않는 톤이므로 차단한다. Kiwi 실패 시 기존 regex 경로만.
    kiwi_rhetorical = False
    try:
        from agents.common import korean_morph  # local import
        _verdict = korean_morph.classify_title_ending(cleaned)
        if isinstance(_verdict, dict) and _verdict.get('class') == 'rhetorical_question':
            kiwi_rhetorical = True
    except Exception:
        kiwi_rhetorical = False

    if any(phrase in cleaned for phrase in banned_phrases) or '?' in cleaned or kiwi_rhetorical:
        return {
            'passed': False,
            'reason': (
                "행사 안내 목적과 맞지 않는 제목 톤입니다. 추측형/논쟁형 표현과 물음표를 제거하고 "
                "'안내/초대/개최/행사명' 같은 안내형 표현을 사용하세요."
            ),
        }

    vague_phrases = (
        '핵심 대화 공개',
        '핵심 메시지 공개',
        '핵심 메시지 현장 공개',
    )
    if any(phrase in cleaned for phrase in vague_phrases):
        return {
            'passed': False,
            'reason': "추상 문구 중심 제목입니다. 날짜/인물/책제목 등 행사 고유 정보를 포함하세요.",
        }

    event_tokens = ('안내', '초대', '개최', '열립니다', '행사') + EVENT_NAME_MARKERS
    if not any(token in cleaned for token in event_tokens):
        return {
            'passed': False,
            'reason': "행사 안내 목적이 제목에 드러나지 않습니다. 안내/초대/개최/행사명을 포함하세요.",
        }

    hook_tokens = ('현장', '직접', '일정', '안내', '초대', '만남', '참석')
    if not any(token in cleaned for token in hook_tokens):
        return {
            'passed': False,
            'reason': (
                "후킹 요소가 부족합니다. '현장/직접/일정/안내/초대/만남/참석' 중 "
                "하나 이상을 제목에 포함하세요."
            ),
        }

    normalized_keywords = [str(k).strip() for k in user_keywords if str(k).strip()]
    primary_keyword = normalized_keywords[0] if normalized_keywords else ''
    if primary_keyword and primary_keyword not in cleaned:
        return {
            'passed': False,
            'reason': f'1순위 검색어 "{primary_keyword}"가 제목에 없습니다.',
        }

    must_preserve = context_analysis.get('mustPreserve') if isinstance(context_analysis.get('mustPreserve'), dict) else {}
    event_date = str(must_preserve.get('eventDate') or '').strip()
    date_hint = _extract_date_hint(event_date) or _extract_date_hint(topic)
    if date_hint and not _contains_date_hint(cleaned, date_hint):
        return {
            'passed': False,
            'reason': f'행사 날짜 정보가 제목에 없습니다. 예: {date_hint}',
        }

    try:
        from services.posts.validation import validate_date_weekday_pairs

        date_weekday_result = validate_date_weekday_pairs(
            cleaned,
            year_hint=f"{event_date} {topic}".strip(),
        )
    except Exception:
        date_weekday_result = {'passed': True, 'issues': []}
    if isinstance(date_weekday_result, dict) and not date_weekday_result.get('passed', True):
        issues = date_weekday_result.get('issues') if isinstance(date_weekday_result.get('issues'), list) else []
        mismatch = next(
            (
                item for item in issues
                if isinstance(item, dict) and str(item.get('type') or '') == 'date_weekday_mismatch'
            ),
            None,
        )
        if mismatch:
            date_text = str(mismatch.get('dateText') or '').strip()
            expected = str(mismatch.get('expectedWeekday') or '').strip()
            found = str(mismatch.get('foundWeekday') or '').strip()
            if date_text and expected:
                return {
                    'passed': False,
                    'reason': f'날짜-요일이 불일치합니다. {date_text}은 {expected}입니다(입력: {found}).',
                }

    book_title = _extract_book_title(topic, params)
    full_name = str(params.get('fullName') or '').strip()

    anchor_tokens: List[str] = []
    anchor_tokens.extend(_split_hint_tokens(date_hint))
    anchor_tokens.extend(_split_hint_tokens(book_title))
    if full_name:
        anchor_tokens.append(full_name)
    deduped_anchor_tokens: List[str] = []
    seen_anchor_tokens = set()
    for token in anchor_tokens:
        normalized = str(token).strip()
        if not normalized:
            continue
        if normalized in seen_anchor_tokens:
            continue
        seen_anchor_tokens.add(normalized)
        deduped_anchor_tokens.append(normalized)
    if deduped_anchor_tokens and not any(token in cleaned for token in deduped_anchor_tokens):
        return {
            'passed': False,
            'reason': (
                "행사 고유 정보가 부족합니다. 날짜/인물명/도서명 중 최소 1개를 제목에 포함하세요."
            ),
        }

    is_book_event = any(marker in topic for marker in ('출판기념회', '북토크', '토크콘서트'))
    if is_book_event and book_title:
        book_tokens = _split_hint_tokens(book_title)
        if book_tokens and not any(token in cleaned for token in book_tokens):
            return {
                'passed': False,
                'reason': f'출판 행사 제목은 도서명 단서가 필요합니다. 예: {book_title}',
            }

    if full_name and full_name not in cleaned:
        return {
            'passed': False,
            'reason': f'행사 안내 제목에는 인물명("{full_name}")을 포함하세요.',
        }

    event_location = str(must_preserve.get('eventLocation') or '').strip()
    location_tokens = _split_hint_tokens(event_location)
    if location_tokens and not any(token in cleaned for token in location_tokens):
        return {'passed': False, 'reason': f'행사 장소 정보가 제목에 없습니다. 예: {event_location}'}

    return {'passed': True}
