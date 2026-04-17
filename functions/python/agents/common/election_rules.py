# functions/python/agents/common/election_rules.py
# 선거법 준수 표현 규칙 및 유틸리티 (Node.js election-rules.js 완전 이식)

import re
from datetime import date as _date
from datetime import datetime as _datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Optional

# ============================================================================
# 선거법 준수 표현 규칙 (3단계)
# 1단계: 예비후보 등록 이전 (준비, 현역)
# 2단계: 예비후보 등록 이후 (예비)
# 3단계: 본 후보 등록 이후 (후보)
# ============================================================================

ELECTION_EXPRESSION_RULES = {
    # 1단계: 예비후보 등록 이전
    "STAGE_1": {
        "applies_to": ['준비', '현역', 'active'],
        "description": '예비후보 등록 이전 - 일반 정치인, 당직자, 현역 의원/단체장',
        "forbidden": {
            # 기부행위 금지 (제112조) — 매체·시기 불문 항상 위법
            "bribery": [
                r'상품권.*?(지급|제공|드리)',
                r'선물.*?(지급|제공|드리)',
                r'물품.*?(지급|제공|드리)',
                r'금품.*?(지급|제공|드리)',
                r'현금.*?(지급|제공|드리)',
                r'[0-9]+만\s*원\s*(지급|드리|제공)',
                r'지지.*?선물',
                r'투표.*?선물',
                r'무상\s*지급',
                r'경품',
                r'사은품',
                r'혜택\s*제공',
            ]
        },
        "replacements": {},
        # 프롬프트에 주입할 지시문
        # 공직선거법 제59조 3항: 인터넷·SNS·블로그 게시글은 선거운동 시기 제한 면제
        # 공약 표현, 지지 호소, 선거 언급은 온라인 매체에서 상시 합법
        # 형사처벌 대상(기부행위·허위사실·후보자비방)만 금지
        "promptInstruction": """
<election_compliance stage="STAGE_1" label="온라인 콘텐츠 — 형사 위험 방지" priority="critical">
  <summary>온라인(SNS/블로그)은 공직선거법 제59조 3항에 따라 선거운동 시기 제한이 면제됩니다.
  단, 아래 형사처벌 대상은 매체·시기 불문 금지입니다.</summary>

  <criminal_risks priority="critical">
    <risk law="제112조">기부행위 금지: "상품권 지급", "선물 제공", "00만원 드리겠습니다"</risk>
    <risk law="제250조">허위사실공표 금지: 출처 없는 통계/수치 주장, 확인 안 된 사실</risk>
    <risk law="제251조">후보자비방 금지: "~라는 소문", "~라고 들었습니다" 형태의 간접사실 적시</risk>
  </criminal_risks>

  <statistics_rule priority="high">
    <must>수치/통계에는 반드시 출처 명시: [출처: 통계청 2024], [출처: 부산시 자료]</must>
    <must-not>출처 없는 수치 사용 금지</must-not>
  </statistics_rule>

  <note>공약 표현("~하겠습니다", "약속드립니다"), 지지 호소, 선거 언급은
  온라인 매체에서 합법적으로 사용할 수 있습니다.</note>
</election_compliance>
"""
    },

    # 2단계: 예비후보 등록 이후
    "STAGE_2": {
        "applies_to": ['예비'],
        "description": '예비후보 등록 이후 - 선관위 등록 완료',
        "forbidden": {},
        "replacements": {},
        "promptInstruction": """
<election_compliance stage="STAGE_2" label="예비후보 단계">
  <summary>예비후보 단계입니다. 온라인 매체에서 선거운동 표현은 자유롭게 사용 가능합니다.</summary>
  <criminal_risks priority="critical">
    <risk law="제112조">기부행위 금지</risk>
    <risk law="제250조">허위사실공표 금지</risk>
    <risk law="제251조">후보자비방 금지</risk>
  </criminal_risks>
</election_compliance>
"""
    },

    # 3단계: 본 후보 등록 이후 (선거기간)
    "STAGE_3": {
        "applies_to": ['후보'],
        "description": '본 후보 등록 이후 - 선거기간',
        "forbidden": {
            # 불법 표현만 금지
            "illegal": [
                r'금품',
                r'향응',
                r'돈을?\s*드리',
            ]
        },
        "replacements": {},
        "promptInstruction": """
<election_compliance stage="STAGE_3" label="정식 후보 단계">
  <summary>정식 후보 단계에서는 대부분의 선거운동 표현이 가능하다.</summary>
  <forbidden_expressions priority="critical">
    <item>금품/향응 제공 암시</item>
    <item>허위사실 유포</item>
  </forbidden_expressions>
</election_compliance>
"""
    }
}


def get_election_stage(status: str) -> Dict[str, Any]:
    """
    상태에 해당하는 선거법 단계 반환

    Args:
        status: 사용자 상태 (준비/현역/예비/후보/active)

    Returns:
        해당 단계의 규칙 딕셔너리
    """
    for stage_name, stage in ELECTION_EXPRESSION_RULES.items():
        if stage.get("applies_to") and status in stage["applies_to"]:
            stage_copy = stage.copy()
            stage_copy['name'] = stage_name
            return stage_copy

    # Default to STAGE_1 if unknown
    default_stage = ELECTION_EXPRESSION_RULES['STAGE_1'].copy()
    default_stage['name'] = 'STAGE_1'
    return default_stage


def get_all_forbidden_patterns(status: str) -> List[str]:
    """
    해당 단계의 모든 금지 패턴을 플랫하게 반환

    Args:
        status: 사용자 상태

    Returns:
        정규식 패턴 문자열 리스트
    """
    stage = get_election_stage(status)
    forbidden = stage.get('forbidden', {})

    patterns = []
    for category, pattern_list in forbidden.items():
        if isinstance(pattern_list, list):
            patterns.extend(pattern_list)

    return patterns


def validate_election_content(content: str, status: str, *, stage_name: str | None = None) -> Dict[str, Any]:
    """
    콘텐츠에서 선거법 위반 표현 검출

    Args:
        content: 검사할 콘텐츠
        status: 사용자 상태
        stage_name: 미리 결정된 스테이지 이름 ('STAGE_1'/'STAGE_2'/'STAGE_3').
                    지정하면 status 대신 이 스테이지의 규칙을 적용한다.

    Returns:
        {
            'passed': bool,
            'violations': [{'pattern': str, 'category': str, 'matches': list, 'severity': str}],
            'total_violations': int
        }
    """
    if stage_name and stage_name in ELECTION_EXPRESSION_RULES:
        stage = ELECTION_EXPRESSION_RULES[stage_name].copy()
        stage['name'] = stage_name
    else:
        stage = get_election_stage(status)
    forbidden = stage.get('forbidden', {})

    violations = []

    # 카테고리별 심각도 매핑
    severity_map = {
        'bribery': 'critical',      # 기부행위 - 형사처벌
        'status': 'high',
        'pledge': 'high',
        'support': 'high',
        'election': 'medium',
        'fullCandidateOnly': 'high',
        'illegal': 'critical',
    }

    for category, patterns in forbidden.items():
        if not isinstance(patterns, list):
            continue

        for pattern in patterns:
            try:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    violations.append({
                        'pattern': pattern,
                        'category': category,
                        'matches': matches if isinstance(matches[0], str) else [m[0] if isinstance(m, tuple) else m for m in matches],
                        'severity': severity_map.get(category, 'medium'),
                        'count': len(matches)
                    })
            except re.error as e:
                print(f"⚠️ 정규식 오류: {pattern} - {e}")
                continue

    return {
        'passed': len(violations) == 0,
        'violations': violations,
        'total_violations': sum(v['count'] for v in violations)
    }



def get_prompt_instruction(status: str) -> str:
    """
    해당 단계의 프롬프트 지시문 반환

    Args:
        status: 사용자 상태

    Returns:
        프롬프트에 삽입할 선거법 준수 지시문
    """
    stage = get_election_stage(status)
    return stage.get('promptInstruction', '')


# 편의 함수: 위반 여부만 빠르게 확인
def has_election_violations(content: str, status: str) -> bool:
    """콘텐츠에 선거법 위반이 있는지 빠르게 확인"""
    result = validate_election_content(content, status)
    return not result['passed']


# 편의 함수: 위반 내용을 사람이 읽기 쉬운 형태로 반환
def get_violation_summary(content: str, status: str) -> str:
    """위반 내용 요약 문자열 반환"""
    result = validate_election_content(content, status)

    if result['passed']:
        return "선거법 위반 표현 없음"

    lines = [f"⚠️ 총 {result['total_violations']}건의 선거법 위반 표현 감지:"]

    for v in result['violations']:
        severity_emoji = {'critical': '🔴', 'high': '🟠', 'medium': '🟡'}.get(v['severity'], '⚪')
        lines.append(f"  {severity_emoji} [{v['category']}] \"{', '.join(v['matches'][:3])}\" ({v['count']}회)")

    return '\n'.join(lines)


# ============================================================================
# 원고 생성 자격 가드
# ----------------------------------------------------------------------------
# 아래 가드는 "선거법 표현 단계"와 별개로, 기존 원고 생성 파이프라인을 언제 허용할지
# 판단하는 진입 조건이다. 기존 STAGE_1/2/3 로직은 표현 검증용 규칙이며, 여기의
# 허용/차단 로직과 1:1로 대응하지 않는다.
# ============================================================================

_KST = ZoneInfo("Asia/Seoul")
_ELECTION_WINDOW_DAYS = 90

# ============================================================================
# 선거 레지스트리 — 선거 유형별 기준일/주기/대상 직책
# ============================================================================

ELECTION_REGISTRY: Dict[str, Dict[str, Any]] = {
    'national_assembly': {
        'base_date': _date(2028, 4, 12),  # 제23대 국회의원선거
        'cycle_years': 4,
        'campaign_period_days': 14,
        'positions': ['국회의원'],
    },
    'local_government': {
        'base_date': _date(2026, 6, 3),  # 제9회 전국동시지방선거
        'cycle_years': 4,
        'campaign_period_days': 14,
        'positions': [
            '광역의원', '기초의원', '시장', '구청장', '군수',
            '도지사', '광역단체장', '기초단체장',
        ],
    },
    # 확장 예시:
    # 'presidential': {
    #     'base_date': _date(2027, 3, 3),
    #     'cycle_years': 5,
    #     'campaign_period_days': 23,
    #     'positions': ['대통령'],
    # },
}


def _today_kst() -> _date:
    """서버 환경과 무관하게 KST 기준 오늘 날짜를 반환한다."""
    return _datetime.now(_KST).date()


def _normalize_candidate_status(user_profile: Dict[str, Any] | None) -> str:
    """
    생성 자격 판단용 후보 상태를 정규화한다.

    기존 선거법 표현 단계와 분리된 규칙이므로, 여기서는 현역/예비/후보만
    허용 상태로 취급한다.
    """
    profile = user_profile if isinstance(user_profile, dict) else {}
    current_status = profile.get("currentStatus")

    raw_candidates = [
        profile.get("status"),
        current_status.get("status") if isinstance(current_status, dict) else None,
        current_status if isinstance(current_status, str) else None,
    ]

    status_map = {
        "현역": "현역",
        "예비": "예비",
        "예비후보": "예비",
        "후보": "후보",
        "준비": "준비",
        "active": "active",
    }

    for raw in raw_candidates:
        normalized = str(raw or "").strip()
        if not normalized:
            continue
        if normalized in status_map:
            return status_map[normalized]
        lowered = normalized.lower()
        if lowered in status_map:
            return status_map[lowered]
        return normalized

    return ""


def _match_election_type(position: str) -> Optional[Dict[str, Any]]:
    """직책 문자열로 ELECTION_REGISTRY에서 매칭되는 선거 유형을 찾는다."""
    if not position:
        return None
    for entry in ELECTION_REGISTRY.values():
        for pos in entry['positions']:
            if pos in position or position in pos:
                return entry
    return None


def _get_next_election_date(user_profile: Dict[str, Any] | None) -> _date:
    """프론트 ElectionDDay와 같은 기준일/주기로 다음 선거일을 계산한다.

    ELECTION_REGISTRY에서 position 매칭하여 선거 유형을 결정한다.
    매칭 실패 시 가장 가까운 선거일을 반환한다 (보수적 폴백).
    """
    profile = user_profile if isinstance(user_profile, dict) else {}
    target = profile.get("targetElection") if isinstance(profile.get("targetElection"), dict) else {}
    position = str(target.get("position") or profile.get("position") or "").strip()

    matched = _match_election_type(position)
    today = _today_kst()

    if matched:
        return _advance_to_next(matched['base_date'], matched['cycle_years'], today)

    # 매칭 실패 — 모든 레지스트리에서 가장 가까운 미래 선거일 반환
    nearest = None
    for entry in ELECTION_REGISTRY.values():
        candidate = _advance_to_next(entry['base_date'], entry['cycle_years'], today)
        if nearest is None or candidate < nearest:
            nearest = candidate
    return nearest or _advance_to_next(ELECTION_REGISTRY['local_government']['base_date'], 4, today)


def _advance_to_next(base: _date, cycle_years: int, today: _date) -> _date:
    """base_date를 cycle_years 간격으로 today 이후까지 전진시킨다."""
    d = base
    while d < today:
        d = _date(d.year + cycle_years, d.month, d.day)
    return d


def check_election_eligibility(user_profile: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    기존 원고 생성 파이프라인 실행 자격을 검사한다.

    허용 조건:
    - 현역: 즉시 허용
    - 예비/후보: 선거일까지 90일 이하일 때만 허용
    """
    profile = user_profile if isinstance(user_profile, dict) else {}
    status = _normalize_candidate_status(profile)

    if status == "현역":
        return {
            "allowed": True,
            "reason": "현역",
            "message": "",
            "days_until_election": None,
        }

    if status not in ("예비", "후보"):
        label = status or "미설정"
        return {
            "allowed": False,
            "reason": "예비_후보_아님",
            "message": f"예비후보 또는 후보 등록 후 이용 가능합니다. (현재 상태: {label})",
            "days_until_election": None,
        }

    election_date = _get_next_election_date(profile)
    days_until_election = (election_date - _today_kst()).days
    if days_until_election > _ELECTION_WINDOW_DAYS:
        return {
            "allowed": False,
            "reason": "선거일_초과",
            "message": (
                f"선거일 {_ELECTION_WINDOW_DAYS}일 이내에 이용 가능합니다. "
                f"(현재 D-{days_until_election}, 선거일: {election_date.strftime('%Y-%m-%d')})"
            ),
            "days_until_election": days_until_election,
        }

    return {
        "allowed": True,
        "reason": "허용",
        "message": "",
        "days_until_election": days_until_election,
    }


# ============================================================================
# 통합 선거 컨텍스트 — status + D-day + position 을 종합하여 동적 단계 결정
# ============================================================================

def _get_phase(days: int, campaign_period_days: int = 14) -> str:
    """D-day로부터 선거 단계(Phase)를 결정한다."""
    if days < 0:
        return 'POST_ELECTION'
    if days == 0:
        return 'ELECTION_DAY'
    if days <= campaign_period_days:
        return 'CAMPAIGN_PERIOD'
    if days <= 30:
        return 'PRE_CAMPAIGN_WARNING'
    return 'NORMAL_PERIOD'


# Phase별 추천 콘텐츠 유형 (election-compliance.js getRecommendedContentTypes 이식)
_RECOMMENDED_CONTENT_TYPES: Dict[str, List[Dict[str, str]]] = {
    'NORMAL_PERIOD': [
        {'type': 'policy', 'title': '정책 연구 발표', 'description': '지역 현안에 대한 정책 제안'},
        {'type': 'achievement', 'title': '의정활동 보고', 'description': '지난 활동 성과 공유'},
        {'type': 'introduction', 'title': '개인 소개', 'description': '정치 철학과 가치관 공유'},
    ],
    'PRE_CAMPAIGN_WARNING': [
        {'type': 'policy', 'title': '정책 토론 참여', 'description': '정책 중심의 건전한 토론'},
        {'type': 'local_issue', 'title': '지역 현안 의견', 'description': '지역 문제에 대한 의견 표명'},
        {'type': 'achievement', 'title': '의정활동 설명', 'description': '객관적 활동 내용 설명'},
    ],
    'CAMPAIGN_PERIOD': [
        {'type': 'campaign', 'title': '공식 선거운동', 'description': '모든 형태의 선거운동 가능'},
        {'type': 'debate', 'title': '공개 토론 참여', 'description': '후보자 간 정책 토론'},
        {'type': 'meet_voters', 'title': '유권자 만남', 'description': '지역 주민과의 소통'},
    ],
    'ELECTION_DAY': [
        {'type': 'thanks', 'title': '감사 인사', 'description': '일반적인 감사 표현만 가능'},
    ],
}

# Phase별 경고 메시지
_PHASE_WARNINGS: Dict[str, Dict[str, str]] = {
    'PRE_CAMPAIGN_WARNING': {
        'title': '사전 선거운동 주의',
        'message': '현재 사전 선거운동 금지 기간입니다. 생성되는 내용이 선거법에 위반되지 않도록 주의해주세요.',
    },
    'CAMPAIGN_PERIOD': {
        'title': '선거운동 기간',
        'message': '공식 선거운동 기간입니다. 선거법에 따른 제한 사항을 준수해주세요.',
    },
    'ELECTION_DAY': {
        'title': '선거일 - 선거운동 금지',
        'message': '투표일에는 모든 형태의 선거운동이 금지됩니다.',
    },
}


def resolve_election_context(
    status: str,
    user_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """status + D-day + position을 종합하여 동적으로 선거법 단계를 결정한다.

    Returns:
        {
            'stage_name': str,          # 'STAGE_1' | 'STAGE_2' | 'STAGE_3'
            'stage': dict,              # ELECTION_EXPRESSION_RULES[stage_name]
            'prompt_instruction': str,  # 프롬프트 주입용 XML
            'days_until_election': int | None,
            'election_date': str | None,      # 'YYYY-MM-DD'
            'phase': str,               # 'NORMAL_PERIOD' | 'PRE_CAMPAIGN_WARNING' | ...
            'phase_warning': dict | None,
            'campaign_unlocked': bool,  # True면 공약 표현 일부/전부 해금
            'blocked': bool,            # True면 생성 자체를 차단해야 함
            'block_reason': str,        # blocked=True일 때 사유
            'recommended_content_types': list,
        }
    """
    profile = user_profile if isinstance(user_profile, dict) else {}
    normalized_status = _normalize_candidate_status(profile) or status or ''

    # 준비 / 현역(active) → 항상 STAGE_1, D-day 무관
    if normalized_status in ('준비', '현역', 'active', ''):
        stage_name = 'STAGE_1'
        stage = ELECTION_EXPRESSION_RULES[stage_name]

        # D-day 계산은 정보 제공용
        election_date = _get_next_election_date(profile)
        today = _today_kst()
        days = (election_date - today).days if election_date else None
        matched = _match_election_type(
            str((profile.get("targetElection") or {}).get("position") or profile.get("position") or "")
        )
        campaign_days = matched['campaign_period_days'] if matched else 14
        phase = _get_phase(days, campaign_days) if days is not None else 'NORMAL_PERIOD'

        return {
            'stage_name': stage_name,
            'stage': stage,
            'prompt_instruction': stage.get('promptInstruction', ''),
            'days_until_election': days,
            'election_date': election_date.strftime('%Y-%m-%d') if election_date else None,
            'phase': phase,
            'phase_warning': _PHASE_WARNINGS.get(phase),
            'campaign_unlocked': False,
            'blocked': False,
            'block_reason': '',
            'recommended_content_types': _RECOMMENDED_CONTENT_TYPES.get(phase, []),
        }

    # 예비 / 후보 → D-day 기반 동적 판단
    if normalized_status in ('예비', '후보'):
        election_date = _get_next_election_date(profile)
        today = _today_kst()
        days = (election_date - today).days

        # 선거 종료 후
        if days < 0:
            return _blocked_context(
                normalized_status, days, election_date,
                'POST_ELECTION', '선거가 종료되었습니다.',
            )

        # 선거일 당일 — 모든 선거운동 금지
        if days == 0:
            return _blocked_context(
                normalized_status, days, election_date,
                'ELECTION_DAY', '선거일 당일에는 콘텐츠 생성이 금지됩니다.',
            )

        # D > 90 — eligibility guard (기존 동작 유지)
        if days > _ELECTION_WINDOW_DAYS:
            return _blocked_context(
                normalized_status, days, election_date,
                _get_phase(days),
                f'선거일 {_ELECTION_WINDOW_DAYS}일 이내에 이용 가능합니다. '
                f'(현재 D-{days}, 선거일: {election_date.strftime("%Y-%m-%d")})',
            )

        # D-90 ~ D-1 → 단계 해금
        matched = _match_election_type(
            str((profile.get("targetElection") or {}).get("position") or profile.get("position") or "")
        )
        campaign_days = matched['campaign_period_days'] if matched else 14
        phase = _get_phase(days, campaign_days)

        if normalized_status == '예비':
            stage_name = 'STAGE_2'
        else:  # 후보
            stage_name = 'STAGE_3'

        stage = ELECTION_EXPRESSION_RULES[stage_name]
        return {
            'stage_name': stage_name,
            'stage': stage,
            'prompt_instruction': stage.get('promptInstruction', ''),
            'days_until_election': days,
            'election_date': election_date.strftime('%Y-%m-%d'),
            'phase': phase,
            'phase_warning': _PHASE_WARNINGS.get(phase),
            'campaign_unlocked': True,
            'blocked': False,
            'block_reason': '',
            'recommended_content_types': _RECOMMENDED_CONTENT_TYPES.get(phase, []),
        }

    # 알 수 없는 상태 → 보수적으로 STAGE_1
    stage_name = 'STAGE_1'
    stage = ELECTION_EXPRESSION_RULES[stage_name]
    return {
        'stage_name': stage_name,
        'stage': stage,
        'prompt_instruction': stage.get('promptInstruction', ''),
        'days_until_election': None,
        'election_date': None,
        'phase': 'NORMAL_PERIOD',
        'phase_warning': None,
        'campaign_unlocked': False,
        'blocked': False,
        'block_reason': '',
        'recommended_content_types': _RECOMMENDED_CONTENT_TYPES.get('NORMAL_PERIOD', []),
    }


def _blocked_context(
    status: str, days: int, election_date: _date,
    phase: str, reason: str,
) -> Dict[str, Any]:
    """생성 차단 컨텍스트를 반환하는 헬퍼."""
    return {
        'stage_name': 'STAGE_1',
        'stage': ELECTION_EXPRESSION_RULES['STAGE_1'],
        'prompt_instruction': '',
        'days_until_election': days,
        'election_date': election_date.strftime('%Y-%m-%d') if election_date else None,
        'phase': phase,
        'phase_warning': _PHASE_WARNINGS.get(phase),
        'campaign_unlocked': False,
        'blocked': True,
        'block_reason': reason,
        'recommended_content_types': _RECOMMENDED_CONTENT_TYPES.get(phase, []),
    }
