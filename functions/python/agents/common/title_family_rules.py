"""
Single source of truth for title-family stylistic rules.

Both the prompt builder (when rendering family-specific instructions) and
the scorer (when gating generated titles) read from this module. Keeping
the definitions in one place prevents the prompt and the gate from drifting
apart — which is what produced the "write commitment style / then reject
commitment style" loop we were seeing before.

Only stylistic / family-fit rules live here. QA-only checks that cannot be
enforced from the prompt side stay in title_scoring.py:
  - number verification against body
  - SEO keyword position
  - duplicate focus-name gate
  - length bounds
  - surface malformation (possessive+modifier, day fragments, etc.)
  - event anchor scoring
"""

import re
from typing import Any, Dict, FrozenSet, List, Pattern


def _compile(sources: List[str]) -> List[Pattern[str]]:
    return [re.compile(src, re.IGNORECASE) for src in sources]


# SLOGAN_COMMITMENT 의 hollow_slogan_patterns 가 잡는 추상 어휘를 단어 단위로
# 노출해, title_keywords.compute_required_topic_keywords 가 동일한 목록을
# required topic keyword 블랙리스트로 사용하도록 한다. 이렇게 두 모듈이 같은
# 상수를 읽으면 "제목에서는 공동체를 쓰지 말라고 강등하면서 동시에 공동체를
# 필수 주제 키워드로 요구" 하는 자기모순을 원천적으로 막는다.
HOLLOW_COLLECTIVE_TOKENS: FrozenSet[str] = frozenset({
    '공동체', '미래', '희망', '사회', '나라', '시대',
})
HOLLOW_VIRTUE_TOKENS: FrozenSet[str] = frozenset({
    '책임', '가치', '길', '약속', '뜻', '꿈', '비전', '마음',
})
# AEO 관점에서 공허한 "정책 추상화" 토큰. 본문에 `취득세 25% 감면`, `60만 개
# 일자리` 같은 구체 정책명·수치가 있는데 제목이 `숙원 사업`, `최대 현안`,
# `핵심 과제` 같은 추상 대체어로 덮어버리면, 답변 엔진이 이 글을 실사용자
# 쿼리에 매칭할 방법이 사라진다. hollow_slogan 과 마찬가지로 구체 앵커가
# 함께 있으면 면책한다.
HOLLOW_POLICY_ABSTRACTION_TOKENS: FrozenSet[str] = frozenset({
    '숙원', '숙원사업', '최대현안', '핵심과제', '주요과제',
    '중점과제', '주요쟁점', '대과제', '대사업',
})
HOLLOW_ABSTRACT_TOKENS: FrozenSet[str] = (
    HOLLOW_COLLECTIVE_TOKENS
    | HOLLOW_VIRTUE_TOKENS
    | HOLLOW_POLICY_ABSTRACTION_TOKENS
)


# UNIVERSAL_AEO_HOLLOW regex 블랙리스트는 삭제됐다. "숙원 사업 완성할까?"
# 같은 추상 제목은 title_scoring._assess_body_anchor_coverage 가 본문에서
# 뽑은 구체 앵커(정책/기관/수치/연도) 인용 여부로 실격시킨다. regex 로 특정
# 어휘를 차단하면 본문이 실제로 어떤 주제를 다루고 있는지와 무관하게 동작해
# 범용성 원칙을 위반한다.


TITLE_FAMILY_RULES: Dict[str, Dict[str, Any]] = {
    'SLOGAN_COMMITMENT': {
        'label': '슬로건·다짐형',
        'positive_patterns': _compile([
            r'(책임감|책임지|책임\s*을?\s*다|다하겠|'
            r'지키(?:겠|는|고|며)?|지킵니다|지켜(?:온|낼|낸|왔|내겠)|'
            r'곁을\s*지키|곁에서|끝까지|'
            r'약속(?:하|합|드립|할)|다짐|맹세|'
            r'실천(?:할|하|으로|한다|합니다|하겠|하는)|'
            r'답하(?:다|겠|는)|답합니다|'
            r'이어받|계승(?:할|하|하겠)?|'
            r'만들겠|만듭니다|만들어가|'
            r'이끄는|이끌겠|이끕니다|'
            r'뛰겠|뛴다|섬기(?:는|겠)|섬깁니다|'
            r'세우(?:는|겠)|세웁니다|일으키|앞장)',
            r'(구민|시민|주민|당원|청년|공동체)\s*(곁|에게|위해|위한)',
            r'(겠습니다|하겠다|드리겠|드립니다)\s*$',
        ]),
        'anti_patterns': _compile([
            r'(현안\s*해결|미래\s*비전|비전\s*제시|정책\s*방향|실행\s*과제|의정활동\s*성과)',
        ]),
        # 공허한 슬로건: {공동체/미래/희망/사회/나라/시대} + {책임/가치/길/약속/뜻/꿈}
        # 조합은 [지역명]·[정책명] 슬롯이 비어 있을 때 등장하는 전형적인
        # 평탄화 패턴이다. positive 가 이겨도 이 조합이 보이면 fit → neutral 로
        # 강등해 구체 정책·수치 슬롯을 채우도록 유도한다. 숫자나 구체 정책
        # 어휘가 함께 있으면 강등을 면제한다(지역명 단독은 rescue 에 포함하지
        # 않는다 — "계양구 공동체 책임 다합니다" 같은 절반짜리도 템플릿 완성도
        # 기준으로는 부족하므로).
        'hollow_slogan_patterns': _compile([
            # {추상 집단명사} + {추상 가치명사}
            r'(공동체|미래|희망|사회|나라|시대)\s*'
            r'(책임|가치|길|약속|뜻|꿈|비전|마음)',
            # {추상 집단명사}을/를 (위해)? + 운동성 동사 — 구체 대상/사업명
            # 없이 추상 집단만 목적어로 삼는 슬로건
            r'(공동체|미래|희망|사회|나라|시대)(?:을|를)?\s*'
            r'(?:위해|위하여)?\s*'
            r'(지키|지킵|지킨|지켰|만들|만듭|만든|이끌|이끕|이끈|'
            r'뛰겠|뛰겠|뛴다|섬기|섬깁|세우|세웁|일으키|일으킨|앞장)',
        ]),
        'hollow_rescue_patterns': _compile([
            r'\d+(?:,\d{3})*\s*(?:억|만원|원|%|명|건|가구|곳|개|회|배)',
            r'(법안|조례|예산|기금|일자리|주거|교통|돌봄|복지|의료|교육|'
            r'재개발|재건축|환경|안전|청년|어르신|어린이집|복지관|보육|체육관|도서관)',
        ]),
        'hollow_reason': (
            '슬로건이 추상어({matched})에 머물러 [지역]·[정책] 슬롯이 '
            '비어 있습니다. 구체 정책명이나 수치를 제목에 넣어 주세요.'
        ),
        'wants_relationship_voice': False,
        'weak_signal_reason': '슬로건·다짐형 단서가 약합니다.',
        'mismatch_reason_template': (
            '선택된 제목 패밀리는 슬로건·다짐형인데, 제목이 "{matched}" 같은 '
            '보고서형 꼬리로 평탄화됐습니다.'
        ),
    },
    'VIRAL_HOOK': {
        'label': '서사 후킹',
        'positive_patterns': _compile([
            r'[?？]',
            r'\b왜\b',
            r'(무엇이\s*다른|주목받|선택의\s*이유|선택은)',
            r'(답은|카드는|한\s*수|이유)\s*$',
            r'(나|까|ㄹ까|을까|들까|갔나|왔나|였나|었나|했나)\s*[?？]?\s*$',
            r'\bvs\b|→|대비',
        ]),
        'anti_patterns': _compile([
            r'(결국\s*터|충격(?:적|이)|경악|소름|놀라운\s*현실)',
        ]),
        'wants_relationship_voice': False,
        'weak_signal_reason': '서사 긴장감(질문/격차/대비) 단서가 약합니다.',
        'mismatch_reason_template': (
            '서사 후킹 패밀리인데 "{matched}" 같은 자극 낚시 표현이 구체 서사를 대체했습니다.'
        ),
    },
    'DATA_BASED': {
        'label': '구체적 데이터',
        'positive_patterns': _compile([
            r'\d+(?:,\d{3})*\s*(?:억|만원|원|%|명|건|가구|곳|개|회|배)',
            r'\d+\s*(?:일|개월|년|분기)',
        ]),
        'anti_patterns': _compile([
            r'(많이|좋은\s*성과|최선(?:을\s*다|입니다)|열심히\s*하|노력하고?\s*있)',
        ]),
        'wants_relationship_voice': False,
        'weak_signal_reason': '구체적 수치가 제목에 드러나지 않습니다.',
        'mismatch_reason_template': (
            '데이터 기반 패밀리인데 "{matched}" 같은 추상 표현이 수치를 대체했습니다.'
        ),
    },
    'QUESTION_ANSWER': {
        'label': '질문-해답',
        'positive_patterns': _compile([
            r'[?？]',
            r'(어떻게|무엇을|무엇이|왜|얼마(?:까지|나)?|언제|어디서?|어떤)',
        ]),
        'anti_patterns': _compile([
            r'(설명드립니다|알려드립니다|안내드립니다)\s*$',
        ]),
        'wants_relationship_voice': False,
        'weak_signal_reason': '질문형 시그널이 없습니다.',
        'mismatch_reason_template': (
            '질문-해답 패밀리인데 "{matched}" 같은 서술형 종결이 질문 구조를 가립니다.'
        ),
    },
    'COMPARISON': {
        'label': '비교·대조',
        'positive_patterns': _compile([
            r'→',
            r'\bvs\b',
            r'(대비|격차|추월|앞섰|뒤처|개선|감소|증가|확대|축소|절감)',
        ]),
        'anti_patterns': _compile([
            r'(나아졌(?:어요|습니다)|많이\s*개선|개선되었습니다)',
        ]),
        'wants_relationship_voice': False,
        'weak_signal_reason': '전후 대비·변화 구조가 드러나지 않습니다.',
        'mismatch_reason_template': (
            '비교·대조 패밀리인데 "{matched}" 같은 추상 개선 표현이 구체 대비를 가렸습니다.'
        ),
    },
    'LOCAL_FOCUSED': {
        'label': '지역 맞춤형',
        'positive_patterns': _compile([
            r'[가-힣]{2,}(?:동|구|군|시|읍|면|리)(?=[가-힣\s,]|$)',
        ]),
        'anti_patterns': _compile([
            r'(우리\s*지역|지역\s*현안|지역을?\s*위해)',
        ]),
        'wants_relationship_voice': False,
        'weak_signal_reason': '행정구역(동/구/시 등) 단위가 제목에 없습니다.',
        'mismatch_reason_template': (
            '지역 맞춤형 패밀리인데 "{matched}" 같은 모호한 표현이 행정구역을 대체했습니다.'
        ),
    },
    'EXPERT_KNOWLEDGE': {
        'label': '전문 지식',
        'positive_patterns': _compile([
            r'(법안|조례|법률|제도|개정|발의|제정|통과|시행령|입법)',
        ]),
        'anti_patterns': _compile([
            r'(좋은\s*정책|법안을\s*발의했습니다|추진하고?\s*있습니다)\s*$',
        ]),
        'wants_relationship_voice': False,
        'weak_signal_reason': '법안·조례·제도 키워드가 제목에 없습니다.',
        'mismatch_reason_template': (
            '전문 지식 패밀리인데 "{matched}" 같은 추상 서술이 법안/조례 구체성을 대체했습니다.'
        ),
    },
    'TIME_BASED': {
        'label': '시간 중심',
        'positive_patterns': _compile([
            r'(20\d{2}년|상반기|하반기|[1-4]분기|\d+월(?:호)?|월간|연간|분기)',
            r'(보고서|리포트|브리핑|뉴스레터)',
        ]),
        'anti_patterns': _compile([
            r'(최근\s*활동|보고서를\s*올립니다)',
        ]),
        'wants_relationship_voice': False,
        'weak_signal_reason': '시점(연/월/분기)·정기 보고 단서가 없습니다.',
        'mismatch_reason_template': (
            '시간 중심 패밀리인데 "{matched}" 같은 모호한 시점 표현만 남았습니다.'
        ),
    },
    'ISSUE_ANALYSIS': {
        'label': '정계 이슈·분석',
        'positive_patterns': _compile([
            r'(개혁|분권|양극화|격차|투명성|대안|위기|쟁점|문제점|해법)',
            r'(\d+대\s*대안|실제로\s*뭐가|뭐가\s*달라|어떻게\s*개선)',
        ]),
        'anti_patterns': _compile([
            r'(생각해\s*봅시다|문제가\s*많습니다)',
        ]),
        'wants_relationship_voice': False,
        'weak_signal_reason': '이슈/대안 구조가 드러나지 않습니다.',
        'mismatch_reason_template': (
            '이슈·분석 패밀리인데 "{matched}" 같은 모호한 수사가 분석을 대체했습니다.'
        ),
    },
    'COMMENTARY': {
        'label': '논평·관점',
        'positive_patterns': _compile([
            r'(이\s*본|가\s*본|의\s*평가|의\s*시각|의\s*판단|의\s*소신)',
            r'(답하(?:다|는)|답합니다|반박|지적|질타|평가한|칭찬한|논평)',
        ]),
        'anti_patterns': _compile([
            r'(입장을?\s*밝힙니다|생각을?\s*전합니다)',
        ]),
        'wants_relationship_voice': True,
        'weak_signal_reason': '관점·화자 표시 구조가 약합니다. ("X이 본", "X의 판단" 등)',
        'mismatch_reason_template': (
            '논평·관점 패밀리인데 "{matched}" 같은 평범한 선언형으로 평탄화됐습니다.'
        ),
    },
}


def get_family_rule(family: str) -> Dict[str, Any]:
    return TITLE_FAMILY_RULES.get(str(family or '').strip().upper(), {})


def assess_family_fit(title: str, family: str) -> Dict[str, Any]:
    """Evaluate a title against its selected family's stylistic rules.

    Returns a breakdown dict: { passed, score, max, status, reason, family }.
    - passed=False when an anti-pattern matches without a positive pattern.
    - 'fit' (full score) when a positive pattern matches, regardless of anti.
    - 'neutral' (partial score) when neither matches.
    """
    normalized_family = str(family or '').strip().upper() or 'VIRAL_HOOK'
    rule = get_family_rule(normalized_family)
    if not rule:
        return {
            'passed': True,
            'score': 8,
            'max': 10,
            'status': 'fit',
            'reason': '',
            'family': normalized_family,
        }

    title_text = str(title or '').strip()
    if not title_text:
        return {
            'passed': True,
            'score': 0,
            'max': 10,
            'status': 'unknown',
            'reason': '',
            'family': normalized_family,
        }

    positive = any(p.search(title_text) for p in rule.get('positive_patterns', []))
    anti_match = None
    for pattern in rule.get('anti_patterns', []):
        m = pattern.search(title_text)
        if m:
            anti_match = m
            break

    # family 와 무관한 AEO hollow 검사는 더 이상 여기서 돌리지 않는다.
    # title_scoring._assess_body_anchor_coverage 가 본문 기반으로 실격시킨다.

    if positive:
        hollow_patterns = rule.get('hollow_slogan_patterns') or []
        if hollow_patterns:
            rescue_patterns = rule.get('hollow_rescue_patterns') or []
            has_rescue = any(p.search(title_text) for p in rescue_patterns)
            if not has_rescue:
                hollow_match = None
                for pattern in hollow_patterns:
                    m = pattern.search(title_text)
                    if m:
                        hollow_match = m
                        break
                if hollow_match:
                    matched = str(hollow_match.group(0) or '').strip()
                    reason_tpl = rule.get('hollow_reason') or (
                        '슬로건이 추상어에 머물러 구체 슬롯이 비어 있습니다.'
                    )
                    return {
                        'passed': True,
                        'score': 5,
                        'max': 10,
                        'status': 'neutral',
                        'reason': reason_tpl.format(matched=matched),
                        'family': normalized_family,
                        'matched': matched,
                        'hollow': True,
                    }
        return {
            'passed': True,
            'score': 10,
            'max': 10,
            'status': 'fit',
            'reason': '',
            'family': normalized_family,
        }

    if anti_match:
        matched = str(anti_match.group(0) or '').strip()
        template = rule.get('mismatch_reason_template') or '선택된 제목 패밀리와 표면이 맞지 않습니다.'
        return {
            'passed': False,
            'score': 0,
            'max': 10,
            'status': 'mismatch',
            'reason': template.format(matched=matched),
            'family': normalized_family,
            'matched': matched,
        }

    return {
        'passed': True,
        'score': 6,
        'max': 10,
        'status': 'neutral',
        'reason': rule.get('weak_signal_reason') or '',
        'family': normalized_family,
    }


def family_wants_relationship_voice(family: str) -> bool:
    rule = get_family_rule(family)
    return bool(rule.get('wants_relationship_voice', False))


def title_has_family_positive_signal(title: str, family: str) -> bool:
    rule = get_family_rule(family)
    title_text = str(title or '').strip()
    if not title_text:
        return False
    return any(p.search(title_text) for p in rule.get('positive_patterns', []))


def title_has_any_commitment_signal(title: str) -> bool:
    """Commitment/slogan endings make sense across many families; exposed as
    a shortcut so the scorer can skip relationship-voice nagging when the
    author clearly wrote a commitment-style title."""
    return title_has_family_positive_signal(title, 'SLOGAN_COMMITMENT')
