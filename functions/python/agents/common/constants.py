import re
from typing import Dict, List, Optional

# 사용자 상태별 설정
STATUS_CONFIG = {
    '현역': {
        'guideline': '현역 의원으로서 경험과 성과를 바탕으로 신뢰있는 내용을 포함하세요. 실제 의정활동 경험을 언급하는게 좋습니다.',
        'title': '의원'
    },
    '후보': {
        'guideline': '후보로서 정책과 공약을 중심으로 신뢰있는 내용을 작성하세요. 미래 비전과 구체적 계획을 제시하세요',
        'title': '후보'
    },
    '예비': {
        'guideline': '예비후보로서 정책과 공약을 중심으로 신뢰있는 내용을 작성하세요. 미래 비전과 구체적 계획을 제시하세요',
        'title': '예비후보'
    },
    '준비': {
        'guideline': '준비 상태에서는 어떤 호칭도 사용하지 않고 개인 이름으로만 지칭하세요. 정치 활동 준비 과정이나 지역 현안에 대한 관심, 개인적 견해를 표현하세요. "의원", "후보" 같은 표현을 사용하지 마세요.',
        'title': ''
    }
}

# 카테고리 → 작법(writingMethod) 매핑
CATEGORY_TO_WRITING_METHOD = {
    'daily-communication': 'emotional_writing',
    'activity-report': 'direct_writing',
    'policy-proposal': 'logical_writing',
    'current-affairs': 'critical_writing',
    'local-issues': 'analytical_writing',
    'educational-content': 'logical_writing',
    'bipartisan-cooperation': 'bipartisan_writing',
    'offline-engagement': 'offline_writing',
}

# 하위 카테고리 → 작법(writingMethod) 매핑
SUBCATEGORY_TO_WRITING_METHOD = {
    'current_affairs_diagnosis': 'diagnostic_writing',
    'policy_explanation': 'logical_writing'
}

def resolve_writing_method(category: str, sub_category: Optional[str] = None) -> str:
    if sub_category and sub_category in SUBCATEGORY_TO_WRITING_METHOD:
        return SUBCATEGORY_TO_WRITING_METHOD[sub_category]
    return CATEGORY_TO_WRITING_METHOD.get(category, 'emotional_writing')


# 기념·추념·성찰·헌사 주제 감지 키워드
# 이 패턴이 topic/stance 에 보이면 '비판(critical_writing)' 은 어색하다 — 성찰·기념·헌사 톤으로 빠져야 함.
_COMMEMORATIVE_MARKERS = (
    # 기념일/주년
    "주년", "기념일", "기념식", "기념하", "기리",
    # 추념/추모/헌정
    "추념", "추모", "헌정", "헌사", "분향", "묵념", "영면", "별세",
    # 선열/희생/계승
    "선열", "순국", "산화", "희생자", "유족", "유공자", "계승하", "이어받",
    # 성찰/되새김
    "되새기", "되돌아보", "성찰", "새기며",
    # 축하/축사
    "축하드립니다", "축하의 말씀", "경축",
)

_CRITIQUE_MARKERS = (
    # 비판 대상을 암시하는 명시적 마커
    "규탄", "책임 추궁", "비판", "고발", "반박", "허위", "조작",
    "실정", "무능", "직권남용", "망언", "책임지", "퇴진", "사퇴",
    "의혹", "논란", "프레임", "가짜뉴스", "날조",
)

# 개인의 소회·다짐형 글을 식별하기 위한 장르 마커 목록.
# 여기 담긴 표현은 특정 사용자의 고유 시그니처가 아니라, 정치인 글쓰기 전반에서
# 반복되는 "국면 마감 + 다음 국면 각오" 장르의 관용구다. 따라서 이 파일에 박혀
# 있어도 특정 사용자에 대한 편향이 되지 않는다.
# 감지 임계값은 최소 2개 이상 일치 (함수 아래 참조) 이므로 우연한 단어 하나로는
# 트리거되지 않는다.
_PERSONAL_REFLECTION_PATTERNS = (
    r"경선\s*(?:이\s*)?마무리",
    r"본격적으로\s*(?:제\s*)?선거",
    r"선거를\s*향해",
    r"다시\s*시작",
    r"새롭게\s*시작",
    r"소회",
    r"다짐",
    r"끝까지\s*함께",
    r"함께해\s*주십시오",
    r"좋은\s*결과로\s*보답",
    r"보답하겠습니다",
    r"곁에서\s*듣겠습니다",
    r"더\s*가까이에서\s*듣겠습니다",
)

_SUBSTANTIVE_POLICY_MARKERS = (
    "조례", "예산", "공약", "정책", "제도", "사업", "법안", "발의", "도입", "개정",
    "추진계획", "로드맵", "수익성", "용역", "시설", "지원대상", "지원금",
)


def _regex_marker_score(text: str, patterns: tuple[str, ...]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text, re.IGNORECASE))


def detect_personal_reflection_topic(topic: str, stance_text: str = "") -> bool:
    """개인의 소회·다짐형 글인지 판정한다.

    정책 제안이나 의정 보고가 아니라 선거·활동의 한 국면을 마무리하고 독자에게 동행을
    요청하는 글이면 AEO 논증 구조보다 emotional_writing이 자연스럽다.
    """
    blob = f"{topic or ''}\n{stance_text or ''}".strip()
    if not blob:
        return False

    reflection_hits = _regex_marker_score(blob, _PERSONAL_REFLECTION_PATTERNS)
    if reflection_hits < 2:
        return False

    critique_hits = sum(1 for marker in _CRITIQUE_MARKERS if marker in blob)
    if critique_hits >= reflection_hits:
        return False

    policy_hits = sum(1 for marker in _SUBSTANTIVE_POLICY_MARKERS if marker in blob)
    return policy_hits <= 1 or reflection_hits >= policy_hits + 2


def detect_commemorative_topic(topic: str, stance_text: str = "") -> bool:
    """주제·입장문에 기념/추념/성찰 시그널이 있고 비판 대상 시그널이 약한지 판정."""
    blob = f"{topic or ''}\n{stance_text or ''}"
    if not blob.strip():
        return False

    commemorative_hits = sum(1 for marker in _COMMEMORATIVE_MARKERS if marker in blob)
    if commemorative_hits == 0:
        return False

    critique_hits = sum(1 for marker in _CRITIQUE_MARKERS if marker in blob)
    # 기념 신호가 비판 신호를 압도할 때만 commemorative 로 판정.
    return commemorative_hits >= max(1, critique_hits + 1)


def refine_writing_method(
    writing_method: str,
    *,
    topic: str,
    stance_text: str = "",
) -> str:
    """카테고리 기반으로 뽑힌 작법을 주제 문맥으로 한 번 더 정제한다.

    Why: current-affairs 카테고리는 기본적으로 critical_writing 이지만, 실제로는 기념·추념·
    성찰·헌사 같은 비판 대상 없는 주제도 같은 카테고리로 들어온다. 그런 주제에 critical
    템플릿을 강제하면 LLM 이 억지 비판 H2 ("X은 바로잡아야 한다" 등) 를 조립해 낸다.
    주제에 기념 마커가 있고 비판 마커가 약하면 emotional_writing (daily_communication 템플릿) 으로
    우회시켜 성찰·다짐 톤을 유지한다.
    """
    if detect_personal_reflection_topic(topic, stance_text):
        return 'emotional_writing'
    if writing_method != 'critical_writing':
        return writing_method
    if detect_commemorative_topic(topic, stance_text):
        return 'emotional_writing'
    return writing_method

POLICY_NAMES = {
    'economy': '경제정책',
    'education': '교육정책',
    'welfare': '복지정책',
    'environment': '환경정책',
    'security': '안보정책',
    'culture': '문화정책'
}

FAMILY_STATUS_MAP = {
    '미혼': '싱글 생활의 경험을 가진',
    '기혼(자녀 있음)': '자녀 양육 가정의 경험을 가진',
    '기혼(자녀 없음)': '가정을 꾸리며',
    '한부모': '한부모 가정의 경험을 가진'
}

CAREER_RELEVANCE = {
    '교육자': ['교육', '학생', '학교', '교사'],
    '사업가': ['경제', '중소상공인', '영업', '창업'],
    '공무원': ['행정', '정책', '공공서비스'],
    '의료인': ['의료', '건강', '코로나', '보건'],
    '법조인': ['법', '제도', '정의', '권리']
}

POLITICAL_EXPERIENCE_MAP = {
    '초선': '초선 의원으로서 신선한 관점에서',
    '재선': '의정 경험을 바탕으로',
    '3선이상': '다선 의정 경험으로',
    '정치 신인': '새로운 시각에서'
}

COMMITTEE_KEYWORDS = {
    '교육위원회': ['교육', '학생', '학교', '대학'],
    '보건복지위원회': ['복지', '의료', '건강', '연금'],
    '국토교통위원회': ['교통', '주거', '도로', '건설'],
    '환경노동위원회': ['환경', '노동', '일자리'],
    '여성가족위원회': ['여성', '가족', '육아', '출산']
}

LOCAL_CONNECTION_MAP = {
    '토박이': '지역 토박이로서',
    '오래 거주': '오랫동안 이 지역에 거주해',
    '이주민': '이 지역에서 새로운 삶을 시작한 고향으로 일구',
    '귀농': '고향으로 돌아온'
}
