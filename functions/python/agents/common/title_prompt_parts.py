"""?? ???? ??? ?? ??."""

import re
from typing import Any, Dict, List, Optional

from .role_keyword_policy import (
    build_role_keyword_intent_anchor_text,
    order_role_keyword_intent_anchor_candidates,
)
from .title_common import (
    TITLE_LENGTH_HARD_MAX,
    TITLE_LENGTH_OPTIMAL_MAX,
    are_keywords_similar,
    extract_numbers_from_content,
    get_election_compliance_instruction,
    logger,
    _collect_recent_title_values,
    _filter_required_title_keywords,
)
from .title_metadata import (
    _detect_event_label,
    _extract_book_title,
    _extract_date_hint,
)
from .title_repairers import (
    _resolve_competitor_intent_title_keyword,
)

USER_PROVIDED_TITLE_FEW_SHOT: Dict[str, Dict[str, Any]] = {
    'DATA_BASED': {
        'name': '구체적 데이터 기반 (성과 보고)',
        'templates': [
            {'template': '[정책명] [수치][단위] 달성, [성과지표] 개선', 'intent': '수치 기반 성과 전달'},
            {'template': '[사업명] [수량][단위] 지원 완료', 'intent': '완료된 실적 강조'},
            {'template': '[예산항목] [금액] 확보, [사업명] 추진', 'intent': '예산·집행 신뢰 강화'},
        ],
        'bad_to_fix': [
            {'bad': '좋은 성과 거뒀습니다', 'fix_template': '[사업명] [수량][단위] 지원 완료'},
            {'bad': '예산 많이 확보했어요', 'fix_template': '[예산항목] [금액] 확보'},
        ],
    },
    'QUESTION_ANSWER': {
        'name': '질문-해답 구조 (AEO 최적화)',
        'templates': [
            {'template': '[지역명] [정책명] [수치][단위] 추가, 동일 기준 공백 해소', 'intent': '사실조회형 — 구체 수치+지표로 답 자체를 미리 노출'},
            {'template': '[지역명] [이슈명], [대안수]개 노선 중 어디로?', 'intent': '선택지질문형 — 구체 선택지 수를 드러낸 AEO 질의'},
            {'template': '[지역명] [사업명], 상위 수준 도약 [숫자]가지 조건', 'intent': '답변예고리스트형 — N가지 리스트로 답 미리보기'},
            {'template': '[지역명] [정책명], [지원항목] 얼마까지?', 'intent': '검색 질문 직접 대응'},
        ],
        'bad_to_fix': [
            {'bad': '[인물명]의 [숫자]년 숙원 사업 완성할까?', 'fix_template': '[지역명] [사업명], 상위 수준 도약 [숫자]가지 조건'},
            {'bad': '[지역명] [사업명], 최대 현안 해결할까?', 'fix_template': '[지역명] [정책명] [수치][단위] 추가, 동일 기준 공백 해소'},
            {'bad': '정책에 대해 설명드립니다', 'fix_template': '[정책명], 무엇이 달라졌나?'},
        ],
    },
    'COMPARISON': {
        'name': '비교·대조 구조 (성과 증명)',
        'templates': [
            {'template': '[지표명] [이전값]→[현재값], [개선폭] 개선', 'intent': '전후 변화 증명'},
            {'template': '[정책명] [기존안]→[개선안] 확대', 'intent': '정책 업그레이드 강조'},
            {'template': '[비용항목] [이전금액]→[현재금액], 절감 실현', 'intent': '예산 효율 어필'},
        ],
        'bad_to_fix': [
            {'bad': '이전보다 나아졌어요', 'fix_template': '[지표명] [이전값]→[현재값] 개선'},
            {'bad': '시간이 단축되었습니다', 'fix_template': '[업무명] [이전기간]→[현재기간] 단축'},
        ],
    },
    'LOCAL_FOCUSED': {
        'name': '지역 맞춤형 정보 (초지역화)',
        'templates': [
            {'template': '[지역명] [정책명], [수치][단위] 지원', 'intent': '지역+정책+수치 결합'},
            {'template': '[지역명] [사업명], [개관시기] 개시', 'intent': '일정 명확화'},
            {'template': '[지역명] [현안], [기간]간 [개선수치]% 개선', 'intent': '체감 성과 전달'},
        ],
        'bad_to_fix': [
            {'bad': '우리 지역을 위해 노력합니다', 'fix_template': '[지역명] [사업명] [수치][단위] 확보'},
            {'bad': '지역 정책 안내', 'fix_template': '[지역명] [정책명] [혜택수치] 지원'},
        ],
    },
    'EXPERT_KNOWLEDGE': {
        'name': '전문 지식 공유 (법안·조례·정책)',
        'templates': [
            {'template': '[법안명] 발의, [핵심지원] 추진', 'intent': '입법 액션 명시'},
            {'template': '[조례명] 개정, [핵심변경] 반영', 'intent': '제도 변경점 전달'},
            {'template': '[정책명], 핵심 [숫자]가지 정리', 'intent': '전문 정보 요약'},
        ],
        'bad_to_fix': [
            {'bad': '법안을 발의했습니다', 'fix_template': '[법안명] 발의, [핵심혜택] 반영'},
            {'bad': '정책을 추진하겠습니다', 'fix_template': '[정책명] [핵심변화] 추진'},
        ],
    },
    'TIME_BASED': {
        'name': '시간 중심 신뢰성 (정기 보고)',
        'templates': [
            {'template': '[연도/분기] [보고서명], [핵심성과수]대 성과', 'intent': '정기성+성과 요약'},
            {'template': '[월/분기] [업무명] 리포트, [건수]건 처리', 'intent': '월간 실적 신뢰 강화'},
            {'template': '[정기브리핑명]([월호]), [핵심주제] 공개', 'intent': '정례 커뮤니케이션 고정화'},
        ],
        'bad_to_fix': [
            {'bad': '보고서를 올립니다', 'fix_template': '[연도/분기] [보고서명], [성과수]대 성과'},
            {'bad': '최근 활동을 정리했습니다', 'fix_template': '[월/분기] [업무명] 리포트, [건수]건 처리'},
        ],
    },
    'ISSUE_ANALYSIS': {
        'name': '정계 이슈·분석 (국가 정책·거시)',
        'templates': [
            {'template': '[이슈명], 실제로 무엇이 달라지는가', 'intent': '변화 궁금증 유도'},
            {'template': '[정책쟁점], [개선수] 단계 개선 경로', 'intent': '해법 탐색형'},
            {'template': '[문제명], [대안수]대 대안 제시', 'intent': '분석-대안 구조'},
        ],
        'bad_to_fix': [
            {'bad': '정치 현실에 대해 생각해 봅시다', 'fix_template': '[이슈명], 실제로 무엇이 달라지는가'},
            {'bad': '문제가 많습니다', 'fix_template': '[문제명], [대안수]대 대안 제시'},
        ],
    },
    'VIRAL_HOOK': {
        'name': '서사 후킹 전개',
        'templates': [
            {'template': '[주제명], 왜 지금 주목받나', 'intent': '정보 격차 후킹'},
            {'template': '[이슈명] 앞에 선 [인물명], 선택의 이유', 'intent': '인물 중심 서사형'},
            {'template': '[정책명], [숫자]가지 쟁점 정리', 'intent': '핵심 포인트 압축'},
        ],
        'bad_to_fix': [
            {'bad': '중요한 이야기입니다', 'fix_template': '[주제명], 왜 지금 주목받나'},
            {'bad': '[인물명]의 [숫자]년 숙원 사업 완성할까?', 'fix_template': '[정책명], [숫자]가지 쟁점 정리'},
            {'bad': '[지역명] [사업명], 최대 현안 해결 가능할까?', 'fix_template': '[이슈명] 앞에 선 [인물명], 선택의 이유'},
        ],
    },
    'SLOGAN_COMMITMENT': {
        'name': '슬로건·다짐형',
        'templates': [
            {'template': '[인물명], [지역명]을 지켜온 책임감으로 끝까지 뛰겠습니다', 'intent': '책임감 기반 다짐'},
            {'template': '[인물명], [지역명] 시민 곁을 지키는 [정책명]', 'intent': '관계·정체성 강조'},
            {'template': '[인물명], [지역명] 주민에게 더 가까운 [정책명]', 'intent': '정체성+약속 압축'},
        ],
        'bad_to_fix': [
            {'bad': '현안 해결과 미래 비전 제시', 'fix_template': '[인물명], [지역명]을 지켜온 책임감으로'},
            {'bad': '[인물명]의 [숫자]년 숙원 사업, 반드시 완성하겠습니다', 'fix_template': '[인물명], [지역명] 시민 곁을 지키는 [정책명]'},
            {'bad': '[지역명] 최대 현안, 핵심 과제로 풀어가겠습니다', 'fix_template': '[인물명], [지역명] 시민 곁을 지키겠습니다'},
        ],
    },
    'COMMENTARY': {
        'name': '논평·관점형',
        'templates': [
            {'template': '[인물명], [이슈명]에 답하다', 'intent': '화자 관점 명시'},
            {'template': '[이슈명], [인물명]의 판단은', 'intent': '관점형 긴장감'},
            {'template': '[정책쟁점], [대안수]대 대안 제시', 'intent': '논평+해법 구조'},
        ],
        'bad_to_fix': [
            {'bad': '입장을 밝힙니다', 'fix_template': '[인물명], [이슈명]에 답하다'},
            {'bad': '[인물명]의 숙원 사업, 완성 가능할까?', 'fix_template': '[정책쟁점], [대안수]대 대안 제시'},
            {'bad': '[지역명] 최대 현안, [인물명]의 해법은?', 'fix_template': '[이슈명], [인물명]의 판단은'},
        ],
    },
}

# ---------------------------------------------------------------------------
# Title Archetype Ending Constraints
# ---------------------------------------------------------------------------
# 각 family 별 종결형 제약. classify_title_ending() 반환값(class) 기준.
# H2 아키타입 검출(h2_guide.py)이 소제목에서 효과를 본 패턴을 제목에 이식.
#   Prong 1 (prompt): build_archetype_constraint_block() → LLM 에게 제약 고지
#   Prong 2 (scorer): _assess_title_ending_constraint() → 위반 시 감점
TITLE_ENDING_CONSTRAINTS: Dict[str, Dict[str, Any]] = {
    'SLOGAN_COMMITMENT': {
        'label': '슬로건·다짐형',
        'allowed_endings': ['commitment', 'noun_end'],
        'forbidden_endings': ['real_question', 'rhetorical_question'],
        'forbidden_reason': '슬로건·다짐형 제목은 질문형 종결이 아니라 경어체 다짐(-겠습니다/-드립니다) 또는 명사구로 끝나야 합니다.',
        'prompt_instruction': '종결은 반드시 다짐형 경어체(-겠습니다/-드립니다/-지킵니다) 또는 명사구. 의문형(-을까?/-할까?/-인가요?/-는?) 절대 금지.',
        'penalty_points': 15,
    },
    'QUESTION_ANSWER': {
        'label': '질문-해답',
        'allowed_endings': ['real_question'],
        'forbidden_endings': ['commitment'],
        'forbidden_reason': '질문-해답형 제목은 실질 의문문(의문사+?)으로 끝나야 합니다. 다짐형 종결은 이 패밀리에 맞지 않습니다.',
        'prompt_instruction': '종결은 반드시 실질 의문문(왜/어떻게/얼마/무엇 + ?). 수사적 반문(-할까?/-될까?) 금지.',
        'penalty_points': 12,
    },
    'DATA_BASED': {
        'label': '구체적 데이터',
        'allowed_endings': ['noun_end', 'declarative', 'commitment'],
        'forbidden_endings': ['rhetorical_question'],
        'forbidden_reason': '데이터 기반 제목은 수치+성과 명사구 또는 선언형으로 끝나야 합니다. 수사적 반문은 데이터 신뢰를 약화시킵니다.',
        'prompt_instruction': '종결은 수치+성과 명사구, 경어체 선언형, 또는 다짐형. 수사적 반문(-할까?) 금지.',
        'penalty_points': 10,
    },
    'COMPARISON': {
        'label': '비교·대조',
        'allowed_endings': ['noun_end', 'declarative', 'real_question'],
        'forbidden_endings': ['rhetorical_question'],
        'forbidden_reason': '비교·대조 제목은 전후 대비 명사구 또는 실질 질문으로 끝나야 합니다.',
        'prompt_instruction': '종결은 대비 구조 명사구(→), 경어체 선언형, 또는 실질 의문문. 수사적 반문 금지.',
        'penalty_points': 8,
    },
    'LOCAL_FOCUSED': {
        'label': '지역 맞춤형',
        'allowed_endings': ['noun_end', 'declarative', 'commitment', 'real_question'],
        'forbidden_endings': ['rhetorical_question'],
        'forbidden_reason': '지역 맞춤형 제목은 지역+수치 명사구, 경어체, 또는 실질 질문으로 끝나야 합니다.',
        'prompt_instruction': '종결은 지역+수치 명사구, 경어체 선언형, 다짐형, 또는 실질 의문문. 수사적 반문 금지.',
        'penalty_points': 8,
    },
    'EXPERT_KNOWLEDGE': {
        'label': '전문 지식',
        'allowed_endings': ['noun_end', 'declarative', 'real_question'],
        'forbidden_endings': ['rhetorical_question'],
        'forbidden_reason': '전문 지식 제목은 법안/조례 명사구 또는 경어체로 끝나야 합니다.',
        'prompt_instruction': '종결은 전문 용어 명사구 또는 경어체 선언형. 수사적 반문 금지.',
        'penalty_points': 8,
    },
    'TIME_BASED': {
        'label': '시간 중심',
        'allowed_endings': ['noun_end', 'declarative'],
        'forbidden_endings': ['rhetorical_question', 'commitment'],
        'forbidden_reason': '시간 중심 제목은 시점+성과 명사구 또는 선언형으로 끝나야 합니다. 다짐형이나 수사적 반문은 정기 보고 톤에 맞지 않습니다.',
        'prompt_instruction': '종결은 시점+성과 명사구 또는 경어체 선언형. 다짐형/수사적 반문 금지.',
        'penalty_points': 8,
    },
    'ISSUE_ANALYSIS': {
        'label': '이슈·분석',
        'allowed_endings': ['noun_end', 'declarative', 'real_question'],
        'forbidden_endings': ['rhetorical_question'],
        'forbidden_reason': '이슈 분석 제목은 분석 명사구, 선언형, 또는 실질 질문으로 끝나야 합니다.',
        'prompt_instruction': '종결은 분석 명사구, 경어체 선언형, 또는 실질 의문문. 수사적 반문 금지.',
        'penalty_points': 8,
    },
    'VIRAL_HOOK': {
        'label': '서사 후킹',
        'allowed_endings': ['noun_end', 'declarative', 'real_question', 'other'],
        'forbidden_endings': ['rhetorical_question'],
        'forbidden_reason': '서사 후킹 제목은 미완결 서사 또는 실질 질문으로 끝나야 합니다. 수사적 반문은 AEO 에서 금지입니다.',
        'prompt_instruction': '종결은 미완결 명사, 실질 의문문(왜/어떻게), 또는 도발적 평서문. -할까?/-될까? 수사적 반문 절대 금지.',
        'penalty_points': 10,
    },
    'COMMENTARY': {
        'label': '논평·관점',
        'allowed_endings': ['noun_end', 'declarative', 'real_question'],
        'forbidden_endings': ['commitment', 'rhetorical_question'],
        'forbidden_reason': '논평·관점 제목은 도발적 평서문 또는 쟁점 질문으로 끝나야 합니다. 다짐형은 논평 톤에 맞지 않습니다.',
        'prompt_instruction': '종결은 단정적 평서문 또는 쟁점 실질 질문. 다짐형(-겠습니다) 및 수사적 반문 금지.',
        'penalty_points': 10,
    },
}


def build_archetype_constraint_block(family_id: str) -> str:
    """family 별 종결형 제약을 프롬프트 XML 블록으로 반환한다."""
    constraint = TITLE_ENDING_CONSTRAINTS.get(str(family_id or '').strip())
    if not constraint:
        return ''
    instruction = constraint.get('prompt_instruction', '')
    if not instruction:
        return ''
    forbidden = constraint.get('forbidden_endings', [])
    allowed = constraint.get('allowed_endings', [])
    forbidden_xml = '\n'.join(
        f'    <forbidden>{e}</forbidden>' for e in forbidden
    )
    allowed_xml = '\n'.join(
        f'    <allowed>{e}</allowed>' for e in allowed
    )
    return f"""<archetype_ending_constraint family="{family_id}" priority="critical">
  <instruction>{instruction}</instruction>
  <ending_rules>
{allowed_xml}
{forbidden_xml}
  </ending_rules>
  <enforcement>이 제약은 content_type 분류에서 결정론적으로 도출됐다. sourceTone 자기판정과 무관하게 반드시 준수할 것. 위반 시 scorer 에서 감점 처리된다.</enforcement>
</archetype_ending_constraint>"""


TITLE_TYPES = {
    'VIRAL_HOOK': {
        'id': 'VIRAL_HOOK',
        'name': '⚡ 서사적 긴장감 (Narrative Hook)',
        'when': '독자의 호기심을 유발하되, 구체적 사실 기반의 서사적 긴장감으로 클릭을 유도할 때 (기본값)',
        'pattern': '정보 격차(Information Gap) 구조: 구체적 팩트 + 미완결 서사 or 의외의 대비',
        'naverTip': '제목이 "답"이 아니라 "질문"을 남길 때 CTR이 가장 높음. 구체적 수치+미완결 문장이 최적.',
        'principle': '【좋은 제목의 판단 기준】\n'
            '- 읽었을 때 "그래서 어떻게 됐지?" 또는 "왜?"라는 생각이 드는가?\n'
            '- 정보 요소가 3개 이하인가? (과밀 = 읽히지 않음)\n'
            '- 기법 하나만 자연스럽게 녹아 있는가? (기법 2개 이상 = 억지)\n'
            '\n'
            '【안티패턴: 이렇게 하면 안 된다】\n'
            '- ❌ 아무 문장 끝에 "~의 선택은?" 붙이기 (형식만 미완결, 내용은 공허)\n'
            '- ❌ 키워드 4개 이상 욱여넣기 (읽는 순간 피로)\n'
            '- ❌ 예시 제목의 어미만 복사하기 (패턴 모방 ≠ 긴장감)\n'
            '- ❌ "이름+의+형용사형/동사형 수식어+명사" 구조 ("후보의 새로운 정책", "후보의 존중하는 비전") — 수식 대상이 불명확하고 의미가 미완결됨',
        'good': [
            {'title': '[지역명] [이슈명], 왜 지금 주목해야 하나', 'chars': 19, 'analysis': '왜 질문형 — 지역+이슈 기반 정보 격차'},
            {'title': '[이슈명] 앞에 선 [역할명], 선택의 이유', 'chars': 20, 'analysis': '서사 아크 — 구체 행위와 이유 연결'},
            {'title': '[정책명], [숫자]가지 쟁점 정리', 'chars': 16, 'analysis': '리스트 예고형 — 답변 구조 미리 노출'},
            {'title': '[지역명] [이슈명], 주민 생활에 어떤 변화가 생기나', 'chars': 24, 'analysis': '영향 질문형 — 주민 관점 AEO 구조'},
            {'title': '현장에서 확인한 [이슈명], 대안은 무엇인가', 'chars': 22, 'analysis': '현장+대안형 — 정치 안전 후킹'},
            {'title': '[이슈명], 주민들이 조용히 겪던 문제입니다', 'chars': 22, 'analysis': '공감형 — 공감 상황극의 정치 변환'},
        ],
        'bad': [
            {'title': '[지역명] [선거명], [직함] [역할명]이 경제를 바꾼다', 'problem': '평서체 종결 — 문장형은 경어체(~바꿉니다) 필수', 'fix': '[지역명] [선거명], [역할명]이 경제를 바꿉니다'},
            {'title': '[역할명] [지역명] [선거명], [정책키워드] [숫자]대 강국?', 'problem': '키워드 나열 — 문장이 아님, 의미 불분명', 'fix': '[지역명] [선거명], [역할명]은 왜 다른가'},
            {'title': '결국 터질 게 터졌습니다... 충격적 현실', 'problem': '낚시 자극 — 구체성 제로, 신뢰 파괴', 'fix': '[지역명] [이슈명], [수치]가 드러낸 현실'},
            {'title': '[지역명] [선거명], [비교대상] [역할명] 원칙 내건 그의 선택은', 'problem': '기계적 모방 — 요소 과밀(5개) + 형식적 미완결 꼬리', 'fix': '[지역명] [선거명], [역할명]은 왜 다른가'},
            {'title': '후보의 존중하는 정책', 'problem': '소유격 + 수식어 나열 — "이름의 [형용사형어구]"는 무엇이 존중하는지 불분명, 의미 불완결', 'fix': '지방선거 경선 확정, 원칙이 가른 판세'},
            {'title': '후보의 새로운 일자리', 'problem': '소유격 + 명사 나열 — 서사 없이 키워드만 접착, 클릭 동기 없음', 'fix': '지방선거, 일자리 공약으로 판 바꾼 새 얼굴'},
            {'title': '지역 산업단지, 4년 숙원 사업 완성할까?', 'problem': '공허 추상 — "숙원 사업/최대 현안/핵심 과제"는 본문의 구체 정책·수치를 가리는 AEO 회피형 수사', 'fix': '지역 산업단지 취득세 25% 추가 감면, 17개 시도 중 유일 공백 해소'},
            {'title': '지역 산업단지 최대 현안, 반드시 해결하겠습니다', 'problem': '추상 의지 — "최대 현안/반드시 해결"은 검색 질의와 매칭되는 앵커 0개, 답변 예고도 없음', 'fix': '지역 산업단지 광역교통망, A역 직결·B역 연결 중 어디로?'},
            {'title': '충격! [이슈]의 숨겨진 진실', 'problem': '상업형 후킹 — 정치 콘텐츠에서 신뢰 파괴 및 선거 리스크. scorer에서 political_high_risk 감점 처리된다.', 'fix': '[이슈], 주민 생활에서 먼저 살펴보겠습니다'},
            {'title': '이 정책 모르면 주민들이 손해봅니다', 'problem': '공포 유발형 — 공공 커뮤니케이션 기준 위반.', 'fix': '[정책명], 주민 생활에 어떤 변화가 생기는지 설명드립니다'},
            {'title': '[이슈]의 진짜 속내, 상대가 말하지 않는 것', 'problem': '음모론·비방형 — 선거법 위험 및 신뢰 파괴. scorer에서 political_high_risk 감점.', 'fix': '[이슈], 사실관계와 쟁점을 차분히 살펴보겠습니다'},
        ]
    },
    'DATA_BASED': {
        'id': 'DATA_BASED',
        'name': '📊 구체적 데이터 기반 (성과 보고)',
        'when': '정책 완료, 예산 확보, 사업 완공 등 구체적 성과가 있을 때',
        'pattern': '숫자 2개 이상 + 핵심 키워드',
        'naverTip': '"억 원", "명", "%" 등 구체적 단위가 있으면 신뢰도 상승',
        'good': [
            {'title': '청년 일자리 274명 창출, 지원금 85억 달성', 'chars': 22, 'analysis': '숫자 2개 + 성과'},
            {'title': '주택 234가구 리모델링 지원 완료', 'chars': 16, 'analysis': '수량 + 완결'},
            {'title': '노후 산업단지 재생, 국비 120억 확보', 'chars': 19, 'analysis': '사업 + 금액'},
            {'title': '교통 신호등 15곳 개선, 사고율 40% 감소', 'chars': 21, 'analysis': '시설 + 효과'},
            {'title': '2025년 상반기 민원 처리 3일 이내 달성', 'chars': 20, 'analysis': '기간 + 기준'}
        ],
        'bad': [
            {'title': '좋은 성과 거뒀습니다', 'problem': '구체적 정보 전무', 'fix': '주택 234가구 지원 완료'},
            {'title': '최선을 다했습니다', 'problem': '성과 미제시', 'fix': '민원 3일 이내 처리율 95%'},
            {'title': '예산 많이 확보했어요', 'problem': '"많이"가 모호', 'fix': '국비 120억 확보'}
        ]
    },
    'QUESTION_ANSWER': {
        'id': 'QUESTION_ANSWER',
        'name': '❓ 질문-해답 구조 (AEO 최적화)',
        'when': '주민이 실제로 검색하는 질문에 답할 때 (정보성)',
        'pattern': '"어떻게", "무엇을", "왜", "얼마" + 질문형',
        'naverTip': '질문형으로 시작하면 검색 사용자의 클릭 유도',
        'good': [
            {'title': '[샘플구] 청년 주거, 월세 지원 얼마까지?', 'chars': 19, 'analysis': '지역 + 혜택 + 질문'},
            {'title': '[샘플시] 교통 체증, 어떻게 풀까?', 'chars': 14, 'analysis': '문제 + 해결책 질문'},
            {'title': '어르신 일자리, 어떤 프로그램이 있나?', 'chars': 19, 'analysis': '대상 + 정보 질문'},
            {'title': '2025년 보육료, 지원 기준 바뀌었어요?', 'chars': 20, 'analysis': '시기 + 변경 확인'},
            {'title': '주민 민원, 실제로 언제 해결돼요?', 'chars': 17, 'analysis': '현실적 질문'}
        ],
        'bad': [
            {'title': '정책에 대해 설명드립니다', 'problem': '지루한 서술형', 'fix': '청년 지원 정책, 무엇이 달라졌나?'},
            {'title': '궁금한 점을 해결해 드립니다', 'problem': '너무 범용적', 'fix': '아이 교육비, 지원 금액 얼마나?'},
            {'title': '후보의 되는 정책', 'problem': '본문 구절 조각을 이름 뒤에 붙여 의미가 끊김', 'fix': '지역 현안, 어떤 정책이 필요한가'}
        ]
    },
    'COMPARISON': {
        'id': 'COMPARISON',
        'name': '🆚 비교·대조 구조 (성과 증명)',
        'when': '정책의 변화, 개선, 해결을 강조할 때',
        'pattern': '전후 대비 수치 + "→", "vs", "대비"',
        'naverTip': '"→", "달라졌다", "개선" 등이 명확한 가치 전달',
        'good': [
            {'title': '민원 처리 14일 → 3일, 5배 빨라졌어요', 'chars': 21, 'analysis': 'Before/After 확실'},
            {'title': '청년 기본소득 월 30만 → 50만원 확대', 'chars': 20, 'analysis': '수치 증대 강조'},
            {'title': '교통 사고율, 전년 대비 40% 감소', 'chars': 17, 'analysis': '감소 효과 데이터'},
            {'title': '쓰레기 비용 99억 → 65억, 절감 실현', 'chars': 20, 'analysis': '예산 절감 증명'},
            {'title': '주차장 부족 지역, 12개월 만에 해결', 'chars': 19, 'analysis': '기간 단축 강조'},
            {'title': '[정책명] 시행 전후, 주민 생활에서 무엇이 달라지나', 'chars': 23, 'analysis': '전/후 비교 — AEO 영향 질문형'},
            {'title': '[기존 방식] vs [새 접근], 핵심 차이는 이것', 'chars': 20, 'analysis': '대조형 — 정보 격차 명시'},
            {'title': '[지역명] [이슈명], [이전값]에서 [현재값]으로 바뀐 것들', 'chars': 25, 'analysis': '수치 변화 + 주민 체감형'},
        ],
        'bad': [
            {'title': '이전보다 나아졌어요', 'problem': '얼마나?', 'fix': '민원 처리 14일→3일 개선'},
            {'title': '많이 개선되었습니다', 'problem': '추상적', 'fix': '교통 사고율 40% 감소'}
        ]
    },
    'LOCAL_FOCUSED': {
        'id': 'LOCAL_FOCUSED',
        'name': '📍 지역 맞춤형 정보 (초지역화)',
        'when': '특정 동·면·읍의 주민을 타겟할 때',
        'pattern': '행정구역명(동 단위) + 정책 + 숫자',
        'naverTip': '동단위 키워드는 경쟁도 낮아 상위노출 유리',
        'good': [
            {'title': '[샘플구] [샘플동] 도시가스, 기금 70억 확보', 'chars': 21, 'analysis': '구/동 + 구체적 예산'},
            {'title': '[샘플구] [샘플동] 학교 신설, 올 9월 개교', 'chars': 21, 'analysis': '지역 + 시설 + 시기'},
            {'title': '[샘플시] [샘플구] 보육료 지원, 월 15만원 추가', 'chars': 22, 'analysis': '지역 + 혜택 구체화'},
            {'title': '[샘플시] [샘플구] 어르신 요양원, 신청 마감 1주', 'chars': 23, 'analysis': '지역 + 긴급성'},
            {'title': '[샘플구] [샘플동] 교통 혼잡도, 6개월간 35% 개선', 'chars': 24, 'analysis': '지역 + 개선 수치'}
        ],
        'bad': [
            {'title': '우리 지역을 위해 노력합니다', 'problem': '어디?', 'fix': '[샘플구] [샘플동] 도시가스 기금 70억'},
            {'title': '지역 현안 해결하겠습니다', 'problem': '무엇을?', 'fix': '[샘플시] [샘플구] 어린이집 5곳 신축'}
        ]
    },
    'EXPERT_KNOWLEDGE': {
        'id': 'EXPERT_KNOWLEDGE',
        'name': '🎓 전문 지식 공유 (법안·조례)',
        'when': '법안 발의, 조례 제정, 정책 분석 글을 쓸 때',
        'pattern': '"법안", "조례", "제도" + 핵심 내용',
        'naverTip': '전문 용어로 E-E-A-T(전문성) 강조',
        'good': [
            {'title': '청년 기본소득법 발의, 월 50만원 지원안', 'chars': 21, 'analysis': '법안명 + 혜택'},
            {'title': '주차장 설치 의무 조례 개정 추진', 'chars': 16, 'analysis': '조례명 + 행위'},
            {'title': '전세 사기 피해자 보호법, 핵심 3가지', 'chars': 19, 'analysis': '법안 + 요약 정보'},
            {'title': '야간 상점 CCTV 의무화 조례안 통과', 'chars': 19, 'analysis': '조례 + 결과'},
            {'title': '자영업자 신용대출, 금리 인하 정책 추진', 'chars': 20, 'analysis': '대상 + 정책 혜택'}
        ],
        'bad': [
            {'title': '법안을 발의했습니다', 'problem': '무슨 법안?', 'fix': '청년 기본소득법 발의, 월 50만원'},
            {'title': '좋은 정책을 준비하고 있습니다', 'problem': '추상적', 'fix': '자영업자 신용대출 금리 인하 추진'}
        ]
    },
    'TIME_BASED': {
        'id': 'TIME_BASED',
        'name': '📅 시간 중심 신뢰성 (정기 보고)',
        'when': '월간 보고서, 분기 리포트, 연간 성과 정리 시',
        'pattern': '"2025년", "상반기", "월간" + 성과 내용',
        'naverTip': '최신성을 강조하여 검색 클릭 유도',
        'good': [
            {'title': '2025년 상반기 의정 보고서, 5대 성과', 'chars': 20, 'analysis': '시점 + 숫자'},
            {'title': '6월 민원 처리 리포트, 1,234건 해결', 'chars': 20, 'analysis': '월 + 구체적 건수'},
            {'title': '2025년 1분기 예산 집행 현황 공개', 'chars': 19, 'analysis': '분기 + 투명성'},
            {'title': '상반기 주민 의견 분석, 88건 반영 추진', 'chars': 21, 'analysis': '기간 + 반영 건수'},
            {'title': '월간 의정 뉴스레터 (7월호) 배포', 'chars': 17, 'analysis': '정기 간행물'}
        ],
        'bad': [
            {'title': '보고서를 올립니다', 'problem': '시간 미명시', 'fix': '2025년 상반기 의정 보고서, 5대 성과'},
            {'title': '최근 활동을 정리했습니다', 'problem': '모호함', 'fix': '6월 민원 처리 리포트, 1,234건 해결'}
        ]
    },
    'ISSUE_ANALYSIS': {
        'id': 'ISSUE_ANALYSIS',
        'name': '⚖️ 정계 이슈·분석 (국가 정책)',
        'when': '정계 이슈, 국가 정책 분석, 제도 개혁 논의 시',
        'pattern': '이슈명 + 질문형 또는 대안 제시',
        'naverTip': '질문형(?)으로 호기심 자극',
        'good': [
            {'title': '지방 분권 개혁, 실제로 무엇이 달라지는가', 'chars': 20, 'analysis': '이슈 + 구체 변화 지시'},
            {'title': '정치 자금 투명성, 3단계 개선 경로', 'chars': 17, 'analysis': '이슈 + 답 예고 리스트'},
            {'title': '양극화 문제, 4대 대안 제시', 'chars': 14, 'analysis': '문제 + 대안 개수'},
            {'title': '교육 격차, 재정 투자로 무엇이 바뀌는가', 'chars': 19, 'analysis': '수단 + 효과 지시'},
            {'title': '선거 제도 개혁, 왜 시급한가', 'chars': 14, 'analysis': '이슈 + 당위성'}
        ],
        'bad': [
            {'title': '정치 현실에 대해 생각해 봅시다', 'problem': '너무 철학적', 'fix': '지방 분권 개혁, 실제로 무엇이 달라지는가'},
            {'title': '문제가 많습니다', 'problem': '불만 토로', 'fix': '양극화 문제, 4대 대안 제시'}
        ]
    },
    'SLOGAN_COMMITMENT': {
        'id': 'SLOGAN_COMMITMENT',
        'name': '🧭 슬로건·다짐형',
        'when': '정체성, 태도, 책임감, 약속을 전면에 세운 입장문/다짐형 글일 때',
        'pattern': '인물명 + 책임감/관계/약속 + 지역 또는 주민 대상',
        'naverTip': '정책 요약보다 정체성·태도·약속을 압축하면 슬로건형 제목의 클릭률과 인물 인지가 올라감',
        'principle': '【좋은 슬로건형 제목의 기준】\n'
            '- 정체성, 관계, 책임감, 약속 중 최소 2개가 드러나는가?\n'
            '- "현안 해결", "정책 방향", "미래 비전" 같은 보고서형 꼬리로 평탄화되지 않았는가?\n'
            '- 주제 문장을 그대로 복사하지 않고, 제목으로 읽히는 압축된 다짐형 문장인가?\n'
            '- [지역명]·[정책명]·[수치] 중 최소 하나의 구체 슬롯이 채워져 있는가?\n'
            '\n'
            '【안티패턴】\n'
            '- ❌ 슬로건형 주제를 보고서형 제목으로 바꾸기 ("현안 해결과 미래 비전 제시")\n'
            '- ❌ 자기인증만 강조하고 관계/약속이 비어 있는 제목 ("가장 충직한 의원")\n'
            '- ❌ 본문 문장을 길게 복붙한 다짐문\n'
            '- ❌ 공허한 추상 쌍만 남은 슬로건: {공동체/미래/희망/사회/나라/시대} + '
            '{책임/가치/길/약속/비전/마음} 조합만 사용하거나, 추상 집단명사를 '
            '목적어로 하는 "공동체를 지킵니다 / 미래를 만들겠습니다" 같은 공식. '
            '반드시 [지역명]이나 [정책명]을 채워 "공동체 책임" 대신 "[지역] [정책] 확대" 형태로 쓸 것.',
        'good': [
            {'title': '[인물명], [지역명] 주민 곁을 지키는 [직책]', 'chars': 24, 'analysis': '정체성 + 관계 + 역할'},
            {'title': '[인물명], [지역명]을 지켜온 책임감으로 끝까지 뛰겠습니다', 'chars': 25, 'analysis': '책임감 + 약속'},
            {'title': '[인물명], [지역명] 주민에게 더 가까운 [직책]', 'chars': 24, 'analysis': '관계형 슬로건'},
            {'title': '[인물명], [지역명]을 지켜온 책임감으로 다시 뜁니다', 'chars': 23, 'analysis': '정체성 + 다짐'},
            {'title': '[인물명], [지역명] 주민 곁에서 끝까지 책임지겠습니다', 'chars': 24, 'analysis': '관계 + 책임 + 약속'}
        ],
        'bad': [
            {'title': '[인물명], [지역명] 현안 해결과 미래 비전 제시', 'problem': '슬로건형 주제가 보고서형 꼬리로 평탄화됨', 'fix': '[인물명], [지역명]을 지켜온 책임감으로 끝까지 뛰겠습니다'},
            {'title': '[인물명], 정책 방향과 실행 과제', 'problem': '다짐형 주제의 정체성/관계가 모두 사라짐', 'fix': '[인물명], [지역명] 주민 곁을 지키는 [직책]'},
            {'title': '[지역명] 주민에게 가장 충직한 [직책] 되겠다', 'problem': '자기인증만 남고 관계/약속이 평면적', 'fix': '[인물명], [지역명] 주민 곁에서 끝까지 책임지겠습니다'},
            {'title': '[인물명], 공동체 책임 다합니다', 'problem': '{공동체/미래/...} + {책임/가치/...} 추상 쌍만 남아 [지역]·[정책] 슬롯이 비어 있음', 'fix': '[인물명], [지역명] 시민 곁을 지키는 [정책명]'},
            {'title': '[인물명], 공동체를 지킵니다', 'problem': '추상 집단명사만 목적어로 두고 구체 정책·대상이 없음', 'fix': '[인물명], [지역명] [정책명] [수치][단위] 확보'},
        ]
    },
    'COMMENTARY': {
         'id': 'COMMENTARY',
         'name': '💬 논평/화자 관점',
         'when': '다른 정치인 논평, 인물 평가, 정치적 입장 표명 시',
         'pattern': '화자 + 관점 표현 + 대상/이슈',
         'naverTip': '화자 이름을 앞에 배치하면 개인 브랜딩 + SEO 효과',
         'good': [
             {'title': '[화자명], [대상명] [직책] [수치][단위] [지표명] 질타', 'chars': 19, 'analysis': '화자 + 대상 + 비판'},
             {'title': '[관계인] 칭찬한 [화자명], [이슈명] 논평', 'chars': 18, 'analysis': '관계 + 화자 + 이슈'},
             {'title': '[화자명] "[지역명] [정책명] 전액 삭감 충격"', 'chars': 19, 'analysis': '화자 + 인용 + 감정'},
             {'title': '[대상명] [직책] 발언에 대한 [화자명] 반박', 'chars': 18, 'analysis': '대상 + 이슈 + 반응'},
             {'title': '[화자명] "[대상명], [지표명] 낙제점"', 'chars': 18, 'analysis': '화자 + 인용'}
         ],
         'bad': [
             {'title': '시장의 발언에 대해', 'problem': '누구? 내용?', 'fix': '[화자명], [대상명] [직책] 발언 반박'},
             {'title': '오늘의 논평입니다', 'problem': '정보 없음', 'fix': '[화자명] "[지역명] [정책명] 삭감 유감"'},
             {'title': '후보, 후보의 되는 정책', 'problem': '이름 반복 뒤에 본문 구절 조각을 접착한 비문', 'fix': '[지역명] 현안, 후보가 말한 해법은'}
         ]
     }
}

COMMON_TITLE_ANTI_PATTERNS: List[Dict[str, str]] = [
    {
        'bad': '후보의 되는 정책',
        'problem': '이름 뒤에 본문 구절 조각("되는 정책" 등)을 붙여 의미가 끊긴 비문',
        'fix': '지역 현안, 어떤 정책이 필요한가',
    },
    {
        'bad': '후보, 후보의 되는 정책',
        'problem': '이름을 반복한 뒤 소유격 구조를 붙여 문장이 무너짐',
        'fix': '지역 현안, 후보가 말한 해법은',
    },
    {
        'bad': '후보의 하는 변화',
        'problem': '형용사형 어구만 남아 수식 대상과 서술 관계가 불명확',
        'fix': '지역 변화, 후보가 내놓은 방향은',
    },
]

# ---------------------------------------------------------------------------
# Title skeletons — 각 family의 good examples에서 역추출한 syntactic 골격.
# LLM이 "보고 참고"하는 것이 아니라 "1개를 선택해 슬롯만 치환"하는 강제 구조.
# 각 skeleton은 scoring rubric과 연결된 triggers를 명시해 점수 획득을 보장한다.
# ---------------------------------------------------------------------------
TITLE_SKELETONS: Dict[str, List[Dict[str, Any]]] = {
    'VIRAL_HOOK': [
        {
            'id': 'S1',
            'pattern': '[SEO키워드], 왜 [인물지시구]이 [과거동사]나',
            'example': '[샘플시] 지방선거, 왜 이 사람이 뛰어들었나',
            'triggers': 'keywordPosition+쉼표, impact:원인질문(왜), impact:미완결서사',
            'note': '왜 질문형 — 구체적 인물 + 미완결',
        },
        {
            'id': 'S2',
            'pattern': '[SEO키워드]에 [과거동사형] [인물 배경/정체성 명사]',
            'example': '[샘플시] 지방선거에 뛰어든 부두 노동자의 아들',
            'triggers': 'keywordPosition(조사), titleFamily, 서사 아크',
            'note': '서사 아크 — 출신·배경으로 호기심 유발',
        },
        {
            'id': 'S3',
            'pattern': '[SEO키워드], [인물명]은 왜 [형용사+ㄴ가]',
            'example': '[샘플시] 지방선거, [후보명]은 왜 다른가',
            'triggers': 'keywordPosition+쉼표, authorIncluded, impact:원인질문',
            'note': '간결 도발형 — 짧고 강렬',
        },
        {
            'id': 'S4',
            'pattern': '[SEO키워드], [수치][단위] [주체]이 [과거동사] [지역/대상]의 [사건명사]',
            'example': '[샘플시] 지방선거, 10만 청년이 떠난 도시의 반란',
            'triggers': 'keywordPosition+쉼표, numbers, impact:미완결서사',
            'note': '수치+사건형 — 팩트 충격 + 암시',
        },
        {
            'id': 'S5',
            'pattern': '[SEO키워드], [가치/수단]만으로 이기는 [인물/진영]',
            'example': '[샘플시] 지방선거, 원칙만으로 이기는 후보',
            'triggers': 'keywordPosition+쉼표, 도발적 선언',
            'note': '도발적 선언 — 가치 논쟁 평서체',
        },
    ],
    'DATA_BASED': [
        {
            'id': 'S1',
            'pattern': '[대상] [사업명] [수치][단위] [성과동사], [추가대상] [수치][단위] [성과동사]',
            'example': '청년 일자리 274명 창출, 지원금 85억 달성',
            'triggers': 'numbers(검증됨, 15점), 정보요소 균형',
            'note': '숫자 2개 + 성과 병렬',
        },
        {
            'id': 'S2',
            'pattern': '[대상] [수량][단위] [사업명] [완료동사]',
            'example': '주택 234가구 리모델링 지원 완료',
            'triggers': 'numbers, 짧고 명확',
            'note': '수량 + 완결',
        },
        {
            'id': 'S3',
            'pattern': '[사업명] [액션], [예산항목] [금액][단위] 확보',
            'example': '노후 산업단지 재생, 국비 120억 확보',
            'triggers': 'numbers, 쉼표 구분',
            'note': '사업 + 금액',
        },
        {
            'id': 'S4',
            'pattern': '[시설] [수량][단위] 개선, [지표] [수치]% 감소',
            'example': '교통 신호등 15곳 개선, 사고율 40% 감소',
            'triggers': 'numbers, impact:대비구조',
            'note': '시설 + 효과 수치',
        },
        {
            'id': 'S5',
            'pattern': '[시점] [업무명] [목표수치][단위] [달성동사]',
            'example': '2025년 상반기 민원 처리 3일 이내 달성',
            'triggers': 'numbers, 기간 명시',
            'note': '기간 + 기준',
        },
    ],
    'QUESTION_ANSWER': [
        {
            'id': 'S1',
            'pattern': '[지역] [대상] [영역], [혜택항목] 얼마까지?',
            'example': '[샘플구] 청년 주거, 월세 지원 얼마까지?',
            'triggers': 'impact:질문형(?), keywordPosition',
            'note': '지역+혜택 질문',
        },
        {
            'id': 'S2',
            'pattern': '[지역] [현안], 어떻게 풀까?',
            'example': '[샘플시] 교통 체증, 어떻게 풀까?',
            'triggers': 'impact:질문형(?), impact:원인질문(어떻게)',
            'note': '문제+해결 질문 — 짧고 강력',
        },
        {
            'id': 'S3',
            'pattern': '[대상] [영역], 어떤 [하위항목]이 있나?',
            'example': '어르신 일자리, 어떤 프로그램이 있나?',
            'triggers': 'impact:질문형(?)',
            'note': '대상+정보 질문',
        },
        {
            'id': 'S4',
            'pattern': '[시점] [정책명], [세부기준] 바뀌었어요?',
            'example': '2025년 보육료, 지원 기준 바뀌었어요?',
            'triggers': 'impact:질문형(?)',
            'note': '시기+변경 확인',
        },
        {
            'id': 'S5',
            'pattern': '[대상] [영역], 실제로 언제 [동사]요?',
            'example': '주민 민원, 실제로 언제 해결돼요?',
            'triggers': 'impact:질문형(?)',
            'note': '현실적 질문',
        },
    ],
    'COMPARISON': [
        {
            'id': 'S1',
            'pattern': '[업무] [이전값][단위] → [현재값][단위], [배수] 빨라졌어요',
            'example': '민원 처리 14일 → 3일, 5배 빨라졌어요',
            'triggers': 'numbers, impact:대비구조(→)',
            'note': 'Before/After + 배수',
        },
        {
            'id': 'S2',
            'pattern': '[혜택명] [단위] [이전값] → [현재값][단위] 확대',
            'example': '청년 기본소득 월 30만 → 50만원 확대',
            'triggers': 'numbers, impact:대비구조(→)',
            'note': '수치 증대 강조',
        },
        {
            'id': 'S3',
            'pattern': '[지표], 전년 대비 [수치]% 감소',
            'example': '교통 사고율, 전년 대비 40% 감소',
            'triggers': 'numbers, impact:대비구조(대비)',
            'note': '연도 대비 감소',
        },
        {
            'id': 'S4',
            'pattern': '[비용항목] [이전][단위] → [현재][단위], 절감 실현',
            'example': '쓰레기 비용 99억 → 65억, 절감 실현',
            'triggers': 'numbers, impact:대비구조(→)',
            'note': '예산 절감 증명',
        },
        {
            'id': 'S5',
            'pattern': '[현안], [기간] 만에 해결',
            'example': '주차장 부족 지역, 12개월 만에 해결',
            'triggers': 'numbers, 기간 단축',
            'note': '기간 중심 성과',
        },
    ],
    'LOCAL_FOCUSED': [
        {
            'id': 'S1',
            'pattern': '[구] [동] [사업/정책], [예산항목] [금액][단위] 확보',
            'example': '[샘플구] [샘플동] 도시가스, 기금 70억 확보',
            'triggers': 'numbers, keywordPosition, 초지역 SEO',
            'note': '구/동 + 구체적 예산',
        },
        {
            'id': 'S2',
            'pattern': '[구] [동] [시설] 신설, [시기] 개교',
            'example': '[샘플구] [샘플동] 학교 신설, 올 9월 개교',
            'triggers': 'keywordPosition, 시기 명시',
            'note': '지역 + 시설 + 시기',
        },
        {
            'id': 'S3',
            'pattern': '[시] [구] [정책] 지원, [단위] [수치][단위] 추가',
            'example': '[샘플시] [샘플구] 보육료 지원, 월 15만원 추가',
            'triggers': 'numbers, keywordPosition',
            'note': '지역 + 혜택 구체화',
        },
        {
            'id': 'S4',
            'pattern': '[시] [구] [대상] [시설], 신청 마감 [기간]',
            'example': '[샘플시] [샘플구] 어르신 요양원, 신청 마감 1주',
            'triggers': 'numbers, 긴급성',
            'note': '지역 + 긴급 행동',
        },
        {
            'id': 'S5',
            'pattern': '[구] [동] [지표], [기간]간 [수치]% 개선',
            'example': '[샘플구] [샘플동] 교통 혼잡도, 6개월간 35% 개선',
            'triggers': 'numbers, impact:대비구조',
            'note': '지역 + 개선 수치',
        },
    ],
    'EXPERT_KNOWLEDGE': [
        {
            'id': 'S1',
            'pattern': '[법안명] 발의, [단위] [혜택수치] [지원명사]',
            'example': '청년 기본소득법 발의, 월 50만원 지원안',
            'triggers': 'numbers, 전문성',
            'note': '법안명 + 혜택 수치',
        },
        {
            'id': 'S2',
            'pattern': '[시설/영역] [의무명사] 조례 개정 추진',
            'example': '주차장 설치 의무 조례 개정 추진',
            'triggers': 'titleFamily, 전문성',
            'note': '조례 개정 행동',
        },
        {
            'id': 'S3',
            'pattern': '[법안명], 핵심 [수치]가지',
            'example': '전세 사기 피해자 보호법, 핵심 3가지',
            'triggers': 'numbers, 정보 요약',
            'note': '법안 + 요약 정보',
        },
        {
            'id': 'S4',
            'pattern': '[대상] [시설/정책] 의무화 조례안 통과',
            'example': '야간 상점 CCTV 의무화 조례안 통과',
            'triggers': 'titleFamily, 결과 명시',
            'note': '조례 + 결과',
        },
        {
            'id': 'S5',
            'pattern': '[대상] [영역], [핵심혜택] 정책 추진',
            'example': '자영업자 신용대출, 금리 인하 정책 추진',
            'triggers': 'titleFamily, 대상+혜택',
            'note': '대상 + 정책 추진',
        },
    ],
    'TIME_BASED': [
        {
            'id': 'S1',
            'pattern': '[시점] [보고서명], [수치]대 성과',
            'example': '2025년 상반기 의정 보고서, 5대 성과',
            'triggers': 'numbers, 시점 명시',
            'note': '정기성 + 성과 요약',
        },
        {
            'id': 'S2',
            'pattern': '[월] [업무명] 리포트, [건수]건 해결',
            'example': '6월 민원 처리 리포트, 1,234건 해결',
            'triggers': 'numbers, 월간 실적',
            'note': '월 + 구체적 건수',
        },
        {
            'id': 'S3',
            'pattern': '[시점] [예산/집행] 현황 공개',
            'example': '2025년 1분기 예산 집행 현황 공개',
            'triggers': 'titleFamily, 투명성',
            'note': '분기 + 투명성 공개',
        },
        {
            'id': 'S4',
            'pattern': '[시점] [활동명], [건수]건 반영 추진',
            'example': '상반기 주민 의견 분석, 88건 반영 추진',
            'triggers': 'numbers, 기간 + 반영',
            'note': '기간 + 반영 건수',
        },
        {
            'id': 'S5',
            'pattern': '[정기간행명] ([월호]) 배포',
            'example': '월간 의정 뉴스레터 (7월호) 배포',
            'triggers': 'titleFamily, 정기성',
            'note': '정기 간행물',
        },
    ],
    'ISSUE_ANALYSIS': [
        {
            'id': 'S1',
            'pattern': '[이슈명], 실제로 무엇이 달라지는가',
            'example': '지방 분권 개혁, 실제로 무엇이 달라지는가',
            'triggers': 'impact:의문사(무엇)',
            'note': '이슈 + 구체 변화 지시',
        },
        {
            'id': 'S2',
            'pattern': '[정책쟁점], [개선수] 단계 개선 경로',
            'example': '정치 자금 투명성, 3단계 개선 경로',
            'triggers': 'numbers, 답변 예고 리스트',
            'note': '쟁점 + 답 예고 리스트',
        },
        {
            'id': 'S3',
            'pattern': '[문제명], [대안수]대 대안 제시',
            'example': '양극화 문제, 4대 대안 제시',
            'triggers': 'numbers, 대안 개수',
            'note': '문제 + 대안 제시',
        },
        {
            'id': 'S4',
            'pattern': '[이슈명], [수단명사]로 무엇이 바뀌는가',
            'example': '교육 격차, 재정 투자로 무엇이 바뀌는가',
            'triggers': 'impact:의문사(무엇)',
            'note': '수단 + 효과 지시',
        },
        {
            'id': 'S5',
            'pattern': '[개혁명], 왜 시급한가?',
            'example': '선거 제도 개혁, 왜 시급한가?',
            'triggers': 'impact:질문형, impact:원인질문(왜)',
            'note': '개혁 + 당위성',
        },
    ],
    'SLOGAN_COMMITMENT': [
        {
            'id': 'S1',
            'pattern': '[SEO키워드], [인물명]의 약속 "[한 줄 다짐]"',
            'example_template': '{KEYWORD}, {NAME}의 약속 "끝까지 곁을 지키겠습니다"',
            'triggers': 'authorIncluded, keywordPosition+쉼표, impact:인용문',
            'note': '대상/키워드 선두 → 인물 → 인용 다짐.',
        },
        {
            'id': 'S2',
            'pattern': '[SEO키워드] 지키는 [인물명], 끝까지 뛰겠습니다',
            'example_template': '{KEYWORD} 지키는 {NAME}, 끝까지 뛰겠습니다',
            'triggers': 'authorIncluded, keywordPosition, impact:다짐어미',
            'note': '키워드 수식구 + 인물 + 다짐.',
        },
        {
            'id': 'S3',
            'pattern': '[SEO키워드] 현장, [인물명]이 책임지겠습니다',
            'example_template': '{KEYWORD} 현장, {NAME}이 책임지겠습니다',
            'triggers': 'authorIncluded, keywordPosition+쉼표, impact:다짐어미',
            'note': '키워드 현장 + 인물 + 책임.',
        },
        {
            'id': 'S4',
            'pattern': '[SEO키워드] 개혁, [인물명]의 한 수',
            'example_template': '{KEYWORD} 개혁, {NAME}의 한 수',
            'triggers': 'authorIncluded, keywordPosition+쉼표, impact:한 수',
            'note': '키워드 이슈 + 인물 + 선택.',
        },
        {
            'id': 'S5',
            'pattern': '[SEO키워드] 위한 [인물명]의 선택 "[한 줄 다짐]"',
            'example_template': '{KEYWORD} 위한 {NAME}의 선택 "끝까지 책임지겠습니다"',
            'triggers': 'authorIncluded, keywordPosition, impact:인용문',
            'note': '키워드 목적 + 인물 + 인용 다짐.',
        },
    ],
    'COMMENTARY': [
        {
            'id': 'S1',
            'pattern': '[화자], [대상] [수치][단위] [비판명사]',
            'example': '[후보명], [경쟁후보명] 시장 0.7% 성장률 질타',
            'triggers': 'authorIncluded+앞배치, numbers, keywordPosition+쉼표',
            'note': '화자 + 대상 + 비판',
        },
        {
            'id': 'S2',
            'pattern': '[제3자] 칭찬한 [화자], [이슈] 논평',
            'example': '[제3자명] 칭찬한 [후보명], 尹 사형 논평',
            'triggers': 'authorIncluded, 관계+화자, keywordPosition',
            'note': '관계 + 이슈 논평',
        },
        {
            'id': 'S3',
            'pattern': '[화자] "[이슈에 대한 인용문]"',
            'example': '[후보명] "[샘플시] AI 예산 전액 삭감 충격"',
            'triggers': 'authorIncluded+앞배치, impact:인용문',
            'note': '화자 + 인용 + 감정',
        },
        {
            'id': 'S4',
            'pattern': '[대상] [사건/발언]에 대한 [화자] 반박',
            'example': '[경쟁후보명] 시장 발언에 대한 [후보명] 반박',
            'triggers': 'authorIncluded, 대상+반응',
            'note': '대상 + 이슈 + 반응',
        },
        {
            'id': 'S5',
            'pattern': '[화자] "[대상], [평가]"',
            'example': '[후보명] "[경쟁후보명], 경제 성적 낙제점"',
            'triggers': 'authorIncluded+앞배치, impact:인용문',
            'note': '화자 + 인용 평가',
        },
    ],
}


def build_title_skeleton_protocol(
    type_id: str,
    params: Optional[Dict[str, Any]] = None,
    slot_opportunities: Optional[Dict[str, List[str]]] = None,
) -> str:
    """Return a structured construction protocol block for the selected title family.

    The LLM must pick exactly one skeleton and fill slots with current topic/keyword/author
    data, instead of inventing a new structure. Each skeleton is labeled with the scoring
    features it triggers so the model can optimize for the rubric directly.

    slot_opportunities — `extract_slot_opportunities` 가 반환한 typed bucket 맵.
    있으면 <available_slots> 에 본문 앵커를 슬롯명별로 노출해 "이 제목에 어떤
    구체 토큰을 넣을 수 있는지" 를 LLM 에게 직접 보여 준다.
    """
    resolved_id = str(type_id or '').strip() or 'VIRAL_HOOK'
    skeletons = TITLE_SKELETONS.get(resolved_id) or TITLE_SKELETONS.get('VIRAL_HOOK') or []
    if not skeletons:
        return ''

    params = params or {}
    full_name = str(params.get('fullName') or '').strip()
    user_keywords = _filter_required_title_keywords(
        params.get('userKeywords') if isinstance(params.get('userKeywords'), list) else [],
        params.get('roleKeywordPolicy') if isinstance(params.get('roleKeywordPolicy'), dict) else {},
    )
    primary_kw = user_keywords[0] if user_keywords else ''
    topic = str(params.get('topic') or '').strip()

    # 필드값 기반 렌더링: example_template이 있으면 현재 사용자 데이터로 치환한다.
    keyword_fill = primary_kw or '[SEO키워드]'
    name_fill = full_name or '[인물명]'

    def _render_example(sk: Dict[str, Any]) -> str:
        template = str(sk.get('example_template') or '').strip()
        if template:
            return template.replace('{KEYWORD}', keyword_fill).replace('{NAME}', name_fill)
        return str(sk.get('example') or '').strip()

    skeleton_xml_lines: List[str] = []
    for sk in skeletons:
        if not isinstance(sk, dict):
            continue
        sk_id = str(sk.get('id') or '').strip()
        pattern = str(sk.get('pattern') or '').strip()
        example = _render_example(sk)
        triggers = str(sk.get('triggers') or '').strip()
        note = str(sk.get('note') or '').strip()
        if not sk_id or not pattern:
            continue
        skeleton_xml_lines.append(
            f'    <skeleton id="{sk_id}" triggers="{triggers}">\n'
            f'      <pattern>{pattern}</pattern>\n'
            f'      <reference_example>{example}</reference_example>\n'
            f'      <note>{note}</note>\n'
            f'    </skeleton>'
        )
    skeletons_block = '\n'.join(skeleton_xml_lines)

    slot_hint_lines: List[str] = []
    if primary_kw:
        slot_hint_lines.append(f'    <slot name="SEO키워드">{primary_kw}</slot>')
    if full_name:
        slot_hint_lines.append(f'    <slot name="인물명|화자">{full_name}</slot>')
    if topic:
        slot_hint_lines.append(f'    <slot name="topic_원문">{topic[:80]}</slot>')

    # 🔑 Phase 3 — body 앵커 주입.
    # extract_slot_opportunities 가 넘겨준 typed bucket 을 skeleton 의
    # 대괄호 슬롯명 기준으로 렌더한다. 예: region bucket 의 토큰은
    # "[지역명]/[장소명]" 슬롯에 들어갈 수 있음을 pipe 로 분리해 노출.
    # 같은 토큰이 여러 슬롯에 대응해도 LLM 이 골라 쓰도록 한 줄에 모아 준다.
    bucket_label_to_brackets: Dict[str, List[str]] = {}
    for bracket, buckets in _BRACKET_TO_OPPORTUNITY_BUCKETS.items():
        for bucket in buckets:
            bucket_label_to_brackets.setdefault(bucket, []).append(bracket)

    if isinstance(slot_opportunities, dict):
        # body_exclusive 메타 — topic/stanceText 에 없고 본문에서만 나온 토큰
        body_exclusive_raw = slot_opportunities.get('_bodyExclusive')
        body_exclusive_sets: Dict[str, set] = {}
        if isinstance(body_exclusive_raw, dict):
            for bk, vals in body_exclusive_raw.items():
                if isinstance(bk, str) and isinstance(vals, list):
                    body_exclusive_sets[bk] = {v for v in vals if isinstance(v, str)}

        bucket_order = ('region', 'policy', 'institution', 'numeric', 'year')
        for bucket in bucket_order:
            items = slot_opportunities.get(bucket) if slot_opportunities else None
            if not isinstance(items, list) or not items:
                continue
            cleaned = [str(x).strip() for x in items if str(x or '').strip()]
            if not cleaned:
                continue
            bracket_names = bucket_label_to_brackets.get(bucket, [])
            # 같은 bucket 에 대응하는 대괄호 슬롯을 pipe 로 묶는다.
            slot_name = '|'.join(bracket_names[:6]) if bracket_names else bucket
            exclusive_set = body_exclusive_sets.get(bucket, set())
            # body-exclusive 토큰에 ★ 마크를 붙여 LLM 이 우선 인용하도록 유도
            marked = [
                f'{tok}(★본문고유)' if tok in exclusive_set else tok
                for tok in cleaned[:5]
            ]
            joined = ' | '.join(marked)
            exclusive_attr = ' has_body_exclusive="true"' if exclusive_set else ''
            slot_hint_lines.append(
                f'    <slot name="{slot_name}" bucket="{bucket}"{exclusive_attr}>{joined}</slot>'
            )

    slot_hint_xml = '\n'.join(slot_hint_lines) or '    <slot name="(없음)">입력 정보에서 추출</slot>'

    # SEO 키워드와 인물명이 동일한 경우의 충돌 회피 규칙
    name_keyword_collision = bool(
        primary_kw and full_name and primary_kw.replace(' ', '') == full_name.replace(' ', '')
    )
    collision_rule_xml = ''
    if resolved_id == 'SLOGAN_COMMITMENT' and name_keyword_collision:
        collision_rule_xml = (
            f'    <rule priority="critical">SEO키워드와 인물명이 동일("{primary_kw}")하다. '
            f'첫 슬롯은 그대로 유지하고, skeleton의 두 번째 [인물명] 슬롯은 '
            f'input 정보(topic/stance)에서 추출한 [지역/대상/정책 명사]로 치환하라. '
            f'"{primary_kw}"라는 이름이 한 제목에 두 번 반복되지 않게 할 것.</rule>\n'
        )
    elif resolved_id == 'SLOGAN_COMMITMENT':
        collision_rule_xml = (
            '    <rule priority="critical">SLOGAN_COMMITMENT의 첫 슬롯 [SEO키워드]는 '
            '항상 제목 앞(0-10자)에 배치하고, skeleton pattern 순서를 그대로 유지하라. '
            'SEO키워드가 인물명과 다르다고 해서 skeleton 구조를 뒤집지 말 것.</rule>\n'
        )

    return f"""
<title_construction_protocol priority="critical" enforce="strict" source="few_shot_skeletons">
  <description>
    이 블록은 검증된 good example에서 역추출한 syntactic 골격이다.
    절대 새 구조를 발명하지 말고, 아래 3단계를 순서대로 밟아 제목을 생성하라.
    각 skeleton의 triggers는 채점 루브릭에서 점수를 받는 feature를 가리킨다.
  </description>

  <selected_family id="{resolved_id}" />

  <phase_1 name="SKELETON_SELECT">
    <instruction>아래 {len(skeleton_xml_lines)}개 skeleton 중 현재 topic/stance에 가장 적합한 1개를 내부적으로 확정하라. 번호를 섞거나 두 skeleton의 요소를 결합하지 말 것.</instruction>
{skeletons_block}
  </phase_1>

  <phase_2 name="SLOT_FILL">
    <instruction>선택한 skeleton의 [대괄호 슬롯]을 아래 입력값으로 치환하라. 슬롯 이름을 그대로 출력하면 실격.</instruction>
    <available_slots>
{slot_hint_xml}
    </available_slots>
    <rule>슬롯에 들어갈 구체 명사·수치는 본문(content_preview) 또는 입장문(stance_summary)에 실제 등장하는 토큰만 사용하라. 허구 수치 금지.</rule>
    <rule priority="critical">available_slots 에 ★본문고유 또는 body_exclusive="true" 로 표시된 토큰이 있으면, 그 중 최소 1개를 제목에 반드시 포함하라. 이 토큰은 topic/입장문에는 없고 본문에서만 발견된 구체 재료이며, 누락 시 scorer 가 0점 실격 처리한다.</rule>
    <rule>skeleton의 종결 어미(~나, ~까, ~까요?, ~겠습니다, ~었어요, 등)와 구두점(?, →, "...", 쉼표)을 임의로 바꾸지 말 것. 구조의 핵심이다.</rule>
    <rule>SEO 키워드가 skeleton 앞쪽 슬롯에 이미 포함돼 있으면 그대로 두고, 없으면 제목 맨 앞(0-10자)에 배치 후 쉼표/조사로 분리하라.</rule>
{collision_rule_xml}  </phase_2>

  <phase_3 name="SELF_VALIDATE" priority="critical">
    <instruction>출력 직전 아래 checklist를 내부 검증하고, 실패 항목이 있으면 phase_1로 돌아가 다른 skeleton을 선택하라.</instruction>
    <checklist>
      <item id="length">글자 수 {TITLE_LENGTH_OPTIMAL_MAX - 15}-{TITLE_LENGTH_OPTIMAL_MAX}자 범위인가?</item>
      <item id="keyword_front">SEO 키워드가 0-10자 위치에 있고 직후에 쉼표/조사가 붙는가?</item>
      <item id="info_density">실질 정보 요소(2자 이상 단어)가 6개 이하인가? (7개 이상 시 감점)</item>
      <item id="skeleton_fidelity">선택한 skeleton의 pattern 순서와 종결형이 그대로 유지되는가?</item>
      <item id="impact_min">
        아래 중 최소 1개를 만족하는가? (impact 점수 획득 조건)
        - 질문형 종결: ?, ~나, ~까
        - 인용부호: "..." 또는 '...'
        - 대비 표현: →, vs, 대비
        - 관점 표현: X이 본, X가 본
        - 미완결 종결: ~은, ~는, ~선택, ~한 수, ~이유, ~답
        - 의문부사: 왜, 어떻게
        - 수치 + 단위 (억, 만원, %, 명, 건, 가구, 곳)
      </item>
      <item id="no_topic_copy">topic 원문을 그대로/거의 그대로 복사하지 않았는가?</item>
      <item id="slot_leak">"[인물명]", "[지역]" 같은 슬롯 이름이 그대로 출력되지 않았는가?</item>
      <item id="body_anchor">available_slots 에 body_exclusive="true" 토큰이 있다면, 그 중 최소 1개를 제목 문장에 직접 포함했는가? body_exclusive 토큰은 topic/입장문에는 없고 본문에서만 발견된 구체 재료(정책명·기관명·수치·연도)다. 이를 인용하지 않으면 scorer 의 bodyAnchorCoverage 게이트에서 0점 실격 처리된다.</item>
    </checklist>
    <fallback>checklist 중 하나라도 실패하면 phase_1로 돌아가 다른 skeleton을 선택하라. 동일 skeleton을 변형하는 것은 금지.</fallback>
  </phase_3>
</title_construction_protocol>
""".strip()

def _build_role_keyword_title_policy_instruction(role_keyword_policy: Dict[str, Any]) -> str:
    policy_dict = role_keyword_policy if isinstance(role_keyword_policy, dict) else {}
    entries = policy_dict.get("entries") if isinstance(policy_dict.get("entries"), dict) else {}
    person_relations = (
        policy_dict.get("personRelations")
        if isinstance(policy_dict.get("personRelations"), dict)
        else {}
    )
    if not entries and not person_relations:
        return ""

    lines: List[str] = []
    for keyword, raw_entry in entries.items():
        entry = raw_entry if isinstance(raw_entry, dict) else {}
        mode = str(entry.get("mode") or "").strip()
        if mode == "intent_only":
            lines.append(
                f'  <rule keyword="{keyword}" mode="intent_only">'
                f'"{keyword}"를 완성된 호칭처럼 쓰지 말고 '
                f'"{build_role_keyword_intent_anchor_text(keyword, variant_index=0)}"처럼 '
                f'출마/거론 의도를 붙여 표현할 것.'
                f"</rule>"
            )
        elif mode == "blocked":
            source_role = str(entry.get("sourceRole") or "").strip() or "입력 근거"
            if bool(entry.get("allowTitleIntentAnchor")):
                lines.append(
                    f'  <rule keyword="{keyword}" mode="blocked_intent_title">'
                    f'"{keyword}"는 현재 직함("{source_role}")과 충돌하므로 사실형 호칭으로는 쓰지 말고, '
                    f'"{build_role_keyword_intent_anchor_text(keyword, variant_index=0)}"처럼 '
                    f'출마/거론 의도를 붙인 검색 앵커로만 제목에 사용할 것.'
                    f"</rule>"
                )
            elif bool(entry.get("allowCompetitorIntent", True)) is False:
                relation = entry.get("speakerRelation") if isinstance(entry.get("speakerRelation"), dict) else {}
                relation_label = str(relation.get("relation") or "프로필상 직접 경쟁 관계 아님").strip()
                lines.append(
                    f'  <rule keyword="{keyword}" mode="profile_not_competitor">'
                    f'"{keyword}"는 사용자 프로필과 대조하면 직접 경쟁자 검색 앵커가 아닙니다'
                    f'({relation_label}). 제목에서 출마론/거론형 경쟁자 앵커로 바꾸지 마세요.'
                    f"</rule>"
                )
            else:
                lines.append(
                    f'  <rule keyword="{keyword}" mode="blocked">'
                    f'"{keyword}"는 입력 근거의 현재 직함("{source_role}")과 충돌하고 '
                    f"target role 근거도 없으므로 제목에서 사용 금지."
                    f"</rule>"
                )

    # personRelations: 사용자 키워드에 들어오지 않았지만 source_texts 에서
    # 등장한 인물 중 화자와 ally(러닝메이트/같은 팀 다른 직책 후보) 관계로
    # 분류된 인물에 대한 긍정 명시 룰. dd923cf 의 부정 차단의 짝꿍.
    for raw_name, raw_relation in person_relations.items():
        relation = raw_relation if isinstance(raw_relation, dict) else {}
        person_name = str(raw_name or "").strip()
        if not person_name:
            continue
        role_text = str(relation.get("role") or "").strip()
        candidate_label = str(relation.get("candidateLabel") or "").strip()
        relation_label = str(relation.get("relation") or "").strip() or "ally"
        role_display = (role_text + candidate_label).strip() or role_text or "다른 직책"
        lines.append(
            f'  <rule person="{person_name}" mode="ally">'
            f'"{person_name}"는 화자와 같은 팀의 다른 직책({role_display})입니다 — '
            f"관계: {relation_label}. 화자가 아니므로 제목에서 화자를 \"{person_name}\"의 "
            f"직책으로 묘사하거나 그 사람의 선거를 화자의 선거로 통합하지 마세요. "
            f'필요하면 "함께/동행/지원" 같은 어휘로 관계를 명시하세요.'
            f"</rule>"
        )

    if not lines:
        return ""
    return "<role_keyword_policy>\n" + "\n".join(lines) + "\n</role_keyword_policy>"

def _build_advisory_keywords_xml(advisory_keywords: Optional[List[str]]) -> str:
    """본문에 근거가 없어 필수에서 제외된 사용자 검색어를 참고용으로 안내한다."""
    cleaned = [str(kw or '').strip() for kw in (advisory_keywords or []) if str(kw or '').strip()]
    if not cleaned:
        return ''
    items = '\n'.join(f'  <keyword>{kw}</keyword>' for kw in cleaned[:3])
    return f"""<advisory_user_keywords priority="low">
  <note>아래 검색어는 사용자가 입력했지만 본문(content_preview)에 직접 등장하지 않습니다. 제목에 억지로 넣으면 본문 근거 없는 SEO 제목이 되므로 필수가 아닙니다. 자연스럽게 녹일 수 있을 때만 포함하세요.</note>
{items}
</advisory_user_keywords>"""


def get_keyword_strategy_instruction(
    user_keywords: List[str],
    keywords: List[str],
    role_keyword_policy: Optional[Dict[str, Any]] = None,
    *,
    advisory_keywords: Optional[List[str]] = None,
) -> str:
    try:
        filtered_user_keywords = _filter_required_title_keywords(user_keywords, role_keyword_policy)
        has_user_keywords = bool(filtered_user_keywords)
        primary_kw = filtered_user_keywords[0] if has_user_keywords else (keywords[0] if keywords else '')
        secondary_kw = (
            (filtered_user_keywords[1] if len(filtered_user_keywords) > 1 else (keywords[0] if keywords else ''))
            if has_user_keywords
            else (keywords[1] if len(keywords) > 1 else '')
        )
        if primary_kw and secondary_kw:
            primary_compact = re.sub(r'\s+', '', primary_kw)
            secondary_compact = re.sub(r'\s+', '', secondary_kw)
            if (
                primary_compact
                and secondary_compact
                and primary_compact in secondary_compact
                and len(secondary_compact) > len(primary_compact)
            ):
                primary_kw, secondary_kw = secondary_kw, primary_kw

        # 두 키워드 간 유사/독립 판별
        has_two_keywords = bool(primary_kw and secondary_kw and primary_kw != secondary_kw)
        similar = has_two_keywords and are_keywords_similar(primary_kw, secondary_kw)

        title_keyword_rule = ""
        if has_two_keywords:
            if similar:
                kw2_words = secondary_kw.split()
                kw1_words = primary_kw.split()
                unique_words = [w for w in kw2_words if w not in kw1_words]
                unique_hint = f'"{", ".join(unique_words)}"를 제목에 반드시 포함' if unique_words else '공통 어절로 자동 충족'
                title_keyword_rule = f"""
<keyword_placement type="similar">
  <description>두 검색어("{primary_kw}", "{secondary_kw}")가 공통 어절을 공유</description>
  <rule type="must">제목은 반드시 "{primary_kw}"로 시작</rule>
  <rule type="must">"{secondary_kw}"는 어절 단위로 해체하여 고유 어절({unique_hint})을 제목에 배치. 누락 시 scorer 가 0점 실격 처리한다.</rule>
  <example kw1="[샘플동] 영광도서" kw2="[샘플시] 영광도서">"[샘플동] 영광도서, &lt;보고있나, [샘플시]&gt; 출판기념회에 초대합니다"</example>
  <example kw1="[샘플동] 탄약고" kw2="[샘플역] 탄약고">"[샘플동] [샘플역] 탄약고 이전, 4년 숙원 해결하겠습니다"</example>
  <example kw1="[샘플시] 대형병원" kw2="[샘플시] 암센터">"[샘플시] 대형병원, 암센터 확충으로 고령 환자도 안심"</example>
</keyword_placement>
"""
            else:
                title_keyword_rule = f"""
<keyword_placement type="independent">
  <description>두 검색어("{primary_kw}", "{secondary_kw}")가 독립적</description>
  <rule type="must">제목은 반드시 "{primary_kw}"로 시작</rule>
  <rule type="must">"{secondary_kw}"는 제목 뒤쪽에 자연스럽게 배치. 누락 시 scorer 가 0점 실격 처리한다.</rule>
  <example kw1="[샘플산] 러브버그 방역" kw2="[샘플구]청">"[샘플산] 러브버그 방역, [샘플구]청에 적극 구제 촉구"</example>
  <example kw1="[샘플역] 3번 출구" kw2="코레일 노조">"[샘플역] 3번 출구, 확장 공사 [제3자명] 덕이라는 코레일 노조"</example>
</keyword_placement>
"""

        kw_instructions = []
        if primary_kw:
            kw_instructions.append(f'  <keyword priority="1" value="{primary_kw}">제목 앞 8자 이내 배치 권장 (필수 아님, 자연스러움 우선)</keyword>')
        if secondary_kw:
            placement = '어절 해체하여 자연 배치' if similar else '제목 뒤쪽 배치'
            kw_instructions.append(f'  <keyword priority="2" value="{secondary_kw}">{placement}</keyword>')
        kw_instruction_xml = '\n'.join(kw_instructions)

        role_keyword_policy_xml = _build_role_keyword_title_policy_instruction(role_keyword_policy or {})

        return f"""
<seo_keyword_strategy>

<front_third_rule priority="highest">
  <description>네이버는 제목 앞 8-10자를 가장 중요하게 평가합니다. 핵심 키워드는 제목 시작 부분 배치를 권장하나, 강렬한 카피(Viral Hook)를 위해 문장 중간에 자연스럽게 녹여도 됩니다.</description>
  <examples>
    <bad>"우리 지역 청년들을 위한 청년 기본소득"</bad>
    <good>"청년 기본소득, [샘플구] 월 50만원 지원"</good>
  </examples>
</front_third_rule>

<keyword_separator priority="critical">
  <description>키워드 직후에 쉼표(,) 또는 조사(에, 의, 에서 등)를 넣어 다음 단어와 분리하세요. 네이버는 공백만으로는 키워드 경계를 인식하지 못합니다.</description>
  <examples>
    <good reason="키워드=[샘플시] 지방선거">"[샘플시] 지방선거, 왜 이 사람이"</good>
    <good reason="키워드=[샘플시] 지방선거">"[샘플시] 지방선거에 뛰어든 부두 노동자"</good>
    <bad reason="잘못 인식: [샘플시] 지방선거 [후보명] 원칙">"[샘플시] 지방선거 [후보명] 원칙"</bad>
  </examples>
</keyword_separator>
{title_keyword_rule}
{role_keyword_policy_xml}
<keyword_density>
  <optimal count="2">가장 자연스럽고 효과적</optimal>
  <max count="3"/>
  <warning>4개 이상: 스팸으로 판단, CTR 감소</warning>
</keyword_density>

  <position_strategy>
  <zone range="0-8자" weight="100%" use="지역명, 정책명, 핵심 주제"/>
  <zone range="9-{TITLE_LENGTH_OPTIMAL_MAX}자" weight="80%" use="수치, LSI 키워드"/>
  <zone range="{TITLE_LENGTH_OPTIMAL_MAX + 1}-{TITLE_LENGTH_HARD_MAX}자" weight="60%" use="행동 유도, 긴급성"/>
</position_strategy>

<keyword_priority>
{kw_instruction_xml}
</keyword_priority>

<synonym_guide description="반복 방지">
  <synonym from="지원" to="지원금, 보조금, 혜택"/>
  <synonym from="문제" to="현안, 과제, 어려움"/>
  <synonym from="해결" to="개선, 완화, 해소"/>
</synonym_guide>

{_build_advisory_keywords_xml(advisory_keywords)}
</seo_keyword_strategy>
"""
    except Exception as e:
        logger.error(f'Error in get_keyword_strategy_instruction: {e}')
        return ''

# ---------------------------------------------------------------------------
# Phase 3 — skeleton 대괄호 슬롯을 body 앵커 typed bucket 으로 연결
# ---------------------------------------------------------------------------
#
# `extract_slot_opportunities` 는 본문·토픽·프로필에서 region/policy/
# institution/numeric/year 다섯 개 bucket 의 앵커를 뽑아낸다.
# few-shot 템플릿·skeleton 이 쓰는 대괄호 슬롯 이름은 그와 1:N 으로 대응한다.
# 이 매핑을 통해 (1) skeleton protocol 의 <available_slots> 에 "어떤 토큰을
# 어떤 슬롯에 넣을 수 있는지" 를 LLM 에게 직접 보여 주고, (2) few-shot
# rendered_examples 의 placeholder default("한빛시/김민우/청년주거지원") 대신
# 실제 본문 앵커가 채워지도록 한다.
_BRACKET_TO_OPPORTUNITY_BUCKETS: Dict[str, List[str]] = {
    '지역명': ['region'],
    '장소명': ['region', 'institution'],
    '정책명': ['policy'],
    '법안명': ['policy'],
    '조례명': ['policy'],
    '사업명': ['policy'],
    '이슈명': ['policy'],
    '정책쟁점': ['policy'],
    '현안': ['policy'],
    '핵심주제': ['policy'],
    '문제명': ['policy'],
    '민원주제': ['policy'],
    '기관명': ['institution'],
    '위원회': ['institution'],
    '수치': ['numeric'],
    '수량': ['numeric'],
    '금액': ['numeric'],
    '숫자': ['numeric'],
    '대안수': ['numeric'],
    '건수': ['numeric'],
    '성과수': ['numeric'],
    '핵심성과수': ['numeric'],
    '개선수치': ['numeric'],
    '혜택수치': ['numeric'],
    '연도/분기': ['year'],
    '월/분기': ['year'],
    '기간': ['year', 'numeric'],
    '개관시기': ['year'],
    '날짜': ['year'],
}

_NUMERIC_SPLIT_RE = re.compile(r'(\d+(?:\.\d+)?)(.*)$')


def _split_numeric_token(token: str) -> tuple[str, str]:
    """'25%' → ('25', '%'), '120억' → ('120', '억'), '17개' → ('17', '개')."""
    text = str(token or '').strip()
    if not text:
        return '', ''
    m = _NUMERIC_SPLIT_RE.match(text)
    if not m:
        return text, ''
    return m.group(1).strip(), m.group(2).strip()


def _first_opportunity(
    slot_opportunities: Optional[Dict[str, List[str]]],
    buckets: List[str],
) -> str:
    """Return the first non-empty item across the given buckets, in order."""
    if not isinstance(slot_opportunities, dict):
        return ''
    for bucket in buckets:
        items = slot_opportunities.get(bucket)
        if not isinstance(items, list):
            continue
        for item in items:
            text = str(item or '').strip()
            if text:
                return text
    return ''


def _build_few_shot_slot_values(
    params: Dict[str, Any],
    slot_opportunities: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, str]:
    default_slot_values: Dict[str, str] = {
        '지역명': '한빛시',
        '장소명': '시민회관',
        '인물명': '김민우',
        '행사명': '정책간담회',
        '날짜': '2026년 4월',
        '주제명': '청년주거지원',
        '정책명': '청년주거지원',
        '사업명': '생활안전정비사업',
        '수치': '10',
        '수량': '10',
        '금액': '120억',
        '단위': '명',
        '성과지표': '만족도',
        '지원항목': '주거비',
        '현안': '교통 혼잡',
        '민원주제': '주차 민원',
        '이슈명': '지역 순환버스',
        '정책쟁점': '청년주거지원 기준',
        '문제명': '보육 인프라 부족',
        '대안수': '3',
        '지표명': '처리 기간',
        '이전값': '14일',
        '현재값': '3일',
        '개선폭': '78%',
        '기존안': '현행 기준',
        '개선안': '확대 기준',
        '비용항목': '운영비',
        '이전금액': '30억',
        '현재금액': '18억',
        '이전기간': '14일',
        '현재기간': '3일',
        '개관시기': '올해 하반기',
        '기간': '6개월',
        '개선수치': '35',
        '법안명': '생활안전지원법',
        '핵심지원': '지원 확대',
        '조례명': '생활안전지원조례',
        '핵심변경': '신청 기준 완화',
        '숫자': '3',
        '핵심혜택': '월 10만원 지원',
        '핵심변화': '대상 확대',
        '연도/분기': '2026년 상반기',
        '보고서명': '활동 보고서',
        '핵심성과수': '5',
        '월/분기': '6월',
        '업무명': '민원 처리',
        '건수': '1,234',
        '정기브리핑명': '월간 브리핑',
        '월호': '7월호',
        '핵심주제': '생활안전 정책',
        '예산항목': '국비',
        '혜택수치': '월 10만원',
        '성과수': '5',
        '업무': '현장 점검',
    }
    topic = str(params.get('topic') or '')
    content_preview = str(params.get('contentPreview') or '')
    full_name = str(params.get('fullName') or '').strip()
    role_keyword_policy = params.get('roleKeywordPolicy') if isinstance(params.get('roleKeywordPolicy'), dict) else {}
    user_keywords = _filter_required_title_keywords(
        params.get('userKeywords') if isinstance(params.get('userKeywords'), list) else [],
        role_keyword_policy,
    )
    context_analysis = params.get('contextAnalysis') if isinstance(params.get('contextAnalysis'), dict) else {}
    must_preserve = context_analysis.get('mustPreserve') if isinstance(context_analysis.get('mustPreserve'), dict) else {}

    primary_kw = str(user_keywords[0]).strip() if user_keywords else ''
    location_hint = str(must_preserve.get('eventLocation') or '').strip()
    date_hint = _extract_date_hint(str(must_preserve.get('eventDate') or '')) or _extract_date_hint(topic)
    event_label = _detect_event_label(topic)
    topic_label = _extract_book_title(topic, params) or (topic[:14].strip() if topic else '')
    numbers = extract_numbers_from_content(content_preview).get('numbers', [])
    first_number = str(numbers[0]).strip() if numbers else default_slot_values['수치']

    slot_values = dict(default_slot_values)
    slot_values.update(
        {
            '지역명': primary_kw or location_hint or default_slot_values['지역명'],
            '장소명': location_hint or primary_kw or default_slot_values['장소명'],
            '인물명': full_name or default_slot_values['인물명'],
            '행사명': event_label or default_slot_values['행사명'],
            '날짜': date_hint or default_slot_values['날짜'],
            '주제명': topic_label or default_slot_values['주제명'],
            '정책명': topic_label or default_slot_values['정책명'],
            '사업명': topic_label or default_slot_values['사업명'],
            '수치': first_number,
            '수량': first_number,
            '금액': first_number,
            '현안': topic_label or default_slot_values['현안'],
            '민원주제': topic_label or default_slot_values['민원주제'],
            '이슈명': topic_label or default_slot_values['이슈명'],
            '정책쟁점': topic_label or default_slot_values['정책쟁점'],
            '문제명': topic_label or default_slot_values['문제명'],
            '법안명': topic_label or default_slot_values['법안명'],
            '조례명': topic_label or default_slot_values['조례명'],
            '핵심주제': topic_label or default_slot_values['핵심주제'],
        }
    )

    # 🔑 Phase 3 — body 앵커 override.
    # slot_opportunities 가 전달되면 placeholder default / topic_label 대신
    # 실제 본문·토픽·프로필에서 추출한 토큰으로 슬롯을 덮어쓴다. 이렇게
    # 해야 rendered_examples 가 허구 앵커("한빛시", "청년주거지원") 대신
    # 현재 글의 실제 정책·지역·수치로 렌더되고, LLM 이 그걸 그대로 복사해
    # 제목을 만든다. 빈 bucket 은 덮어쓰지 않아 기존 topic_label fallback 을
    # 유지한다.
    if isinstance(slot_opportunities, dict) and slot_opportunities:
        for bracket, buckets in _BRACKET_TO_OPPORTUNITY_BUCKETS.items():
            value = _first_opportunity(slot_opportunities, buckets)
            if not value:
                continue
            if bracket in ('수치', '수량', '숫자', '대안수', '건수',
                           '성과수', '핵심성과수', '개선수치'):
                numeric_part, _unit_part = _split_numeric_token(value)
                slot_values[bracket] = numeric_part or value
            elif bracket == '혜택수치':
                slot_values[bracket] = value
            else:
                slot_values[bracket] = value
        # numeric bucket 의 첫 토큰에서 단위를 뽑아 [단위] 슬롯도 동기화
        first_numeric = _first_opportunity(slot_opportunities, ['numeric'])
        if first_numeric:
            _num_part, unit_part = _split_numeric_token(first_numeric)
            if unit_part:
                slot_values['단위'] = unit_part

    return slot_values

def _render_slot_template(template: str, slot_values: Dict[str, str]) -> str:
    rendered = str(template or '')
    for slot_name, slot_value in slot_values.items():
        rendered = rendered.replace(f'[{slot_name}]', str(slot_value))
    return re.sub(r'\s+', ' ', rendered).strip()


def build_common_title_anti_pattern_instruction() -> str:
    examples_xml = '\n'.join(
        f'  <example index="{idx}">'
        f'<bad>{item.get("bad", "")}</bad>'
        f'<problem>{item.get("problem", "")}</problem>'
        f'<fix>{item.get("fix", "")}</fix>'
        f'</example>'
        for idx, item in enumerate(COMMON_TITLE_ANTI_PATTERNS, start=1)
        if isinstance(item, dict)
    )
    return f"""
<common_title_anti_patterns priority="critical">
  <rule>"[인물명]의 되는/하는/있는 [명사]" 구조 금지. 본문 구절 조각을 이름 뒤에 붙이지 마세요.</rule>
  <rule>"[인물명], [인물명]의 ..."처럼 이름을 반복한 뒤 소유격 구조를 붙이는 제목 금지.</rule>
  <rule>content_preview의 구문 일부를 떼어 이름 뒤에 직접 접착하지 말고, 팩트와 논지를 새 문장으로 다시 구성하세요.</rule>
  <examples>
{examples_xml}
  </examples>
</common_title_anti_patterns>
""".strip()


def build_user_provided_few_shot_instruction(
    type_id: str,
    params: Optional[Dict[str, Any]] = None,
    slot_opportunities: Optional[Dict[str, List[str]]] = None,
) -> str:
    requested_type_id = str(type_id or '').strip()
    resolved_type_id = requested_type_id
    few_shot = USER_PROVIDED_TITLE_FEW_SHOT.get(resolved_type_id)
    if not few_shot:
        logger.info("[TitleGen] 사용자 few-shot 미정의 타입: %s", resolved_type_id)
        return ''

    slot_values = _build_few_shot_slot_values(params or {}, slot_opportunities)
    slot_guide = '\n'.join([
        f'    <slot name="{k}" value="{v}" />'
        for k, v in list(slot_values.items())[:12]
    ])

    template_examples = '\n'.join([
        f'    <template pattern="{item.get("template", "")}" intent="{item.get("intent", "")}" />'
        for item in few_shot.get('templates', [])
        if isinstance(item, dict)
    ])
    rendered_examples = '\n'.join([
        f'    <example>{_render_slot_template(item.get("template", ""), slot_values)}</example>'
        for item in few_shot.get('templates', [])
        if isinstance(item, dict)
    ])
    bad_examples = '\n'.join([
        f'    <example bad="{item.get("bad", "")}" fix_template="{item.get("fix_template", "")}" />'
        for item in few_shot.get('bad_to_fix', [])
        if isinstance(item, dict)
    ])

    return f"""
<user_provided_few_shot priority="high" source="사용자_정치인_7유형_전략">
  <description>아래 예시는 고정 카피가 아니라 슬롯 기반 템플릿이다. 현재 주제/지역/인물에 맞게 슬롯만 치환해 사용하라.</description>
  <type requested="{requested_type_id}" resolved="{resolved_type_id}" name="{few_shot.get('name', '')}" />
  <slot_guide>
{slot_guide}
  </slot_guide>
  <template_examples>
{template_examples}
  </template_examples>
  <rendered_examples>
{rendered_examples}
  </rendered_examples>
  <bad_to_fix_examples>
{bad_examples}
  </bad_to_fix_examples>
</user_provided_few_shot>
""".strip()

def build_poll_focus_title_instruction(params: Dict[str, Any]) -> str:
    bundle = params.get('pollFocusBundle') if isinstance(params.get('pollFocusBundle'), dict) else {}
    if str(bundle.get('scope') or '').strip().lower() != 'matchup':
        return ''

    primary_pair = bundle.get('primaryPair') if isinstance(bundle.get('primaryPair'), dict) else {}
    speaker = str(primary_pair.get('speaker') or '').strip()
    opponent = str(primary_pair.get('opponent') or '').strip()
    speaker_percent = str(primary_pair.get('speakerPercent') or primary_pair.get('speakerScore') or '').strip()
    opponent_percent = str(primary_pair.get('opponentPercent') or primary_pair.get('opponentScore') or '').strip()
    if not speaker or not opponent or not speaker_percent or not opponent_percent:
        return ''

    allowed_title_lanes = bundle.get('allowedTitleLanes') if isinstance(bundle.get('allowedTitleLanes'), list) else []
    forbidden_metrics = bundle.get('forbiddenMetrics') if isinstance(bundle.get('forbiddenMetrics'), list) else []
    title_name_priority = bundle.get('titleNamePriority') if isinstance(bundle.get('titleNamePriority'), list) else []
    title_name_repeat_limit = max(1, int(bundle.get('titleNameRepeatLimit') or 1))
    forbidden_xml = "\n".join(
        f"  <metric>{str(item).strip()}</metric>"
        for item in forbidden_metrics[:5]
        if str(item).strip()
    ) or "  <metric>정당 지지율</metric>"
    name_priority_xml = "\n".join(
        f'  <name index="{idx}">{str(item).strip()}</name>'
        for idx, item in enumerate(title_name_priority[:4], start=1)
        if str(item).strip()
    ) or f'  <name index="1">{speaker}</name>'

    secondary_pairs = bundle.get('secondaryPairs') if isinstance(bundle.get('secondaryPairs'), list) else []
    secondary_xml_lines: List[str] = []
    for idx, raw_pair in enumerate(secondary_pairs[:2], start=1):
        pair = raw_pair if isinstance(raw_pair, dict) else {}
        pair_speaker = str(pair.get('speaker') or '').strip()
        pair_opponent = str(pair.get('opponent') or '').strip()
        pair_speaker_score = str(pair.get('speakerPercent') or pair.get('speakerScore') or '').strip()
        pair_opponent_score = str(pair.get('opponentPercent') or pair.get('opponentScore') or '').strip()
        if not pair_speaker or not pair_opponent or not pair_speaker_score or not pair_opponent_score:
            continue
        secondary_xml_lines.append(
            f'  <pair index="{idx}">{pair_speaker} vs {pair_opponent} ({pair_speaker_score} 대 {pair_opponent_score})</pair>'
        )
    secondary_xml = "\n".join(secondary_xml_lines) if secondary_xml_lines else '  <pair index="0">없음</pair>'

    lane_xml_lines: List[str] = []
    for raw_lane in allowed_title_lanes[:3]:
        lane = raw_lane if isinstance(raw_lane, dict) else {}
        lane_id = str(lane.get('id') or '').strip()
        lane_label = str(lane.get('label') or lane_id).strip()
        lane_template = str(lane.get('template') or '').strip()
        if not lane_id or not lane_template:
            continue
        lane_xml_lines.append(
            f'  <lane id="{lane_id}" label="{lane_label}">{lane_template}</lane>'
        )
    lane_xml = "\n".join(lane_xml_lines) if lane_xml_lines else '  <lane id="fact_direct" label="fact_direct">없음</lane>'

    return f"""
<poll_focus_title priority="critical">
  <primary_pair>{speaker} vs {opponent} ({speaker_percent} 대 {opponent_percent})</primary_pair>
  <secondary_pairs>
{secondary_xml}
  </secondary_pairs>
  <allowed_lanes>
{lane_xml}
  </allowed_lanes>
  <title_name_priority>
{name_priority_xml}
  </title_name_priority>
  <forbidden_metrics>
{forbidden_xml}
  </forbidden_metrics>
  <rules>
    <rule>제목은 allowed_lanes 중 하나의 문법을 따르고, 정당 지지율이나 당내 경선 수치로 중심을 바꾸지 않습니다.</rule>
    <rule>질문형을 쓰더라도 판세 전환형 표현('역전', '뒤집힘', '흔들림')은 사용하지 않습니다. 접전이나 경쟁력 수준에서만 해석합니다.</rule>
    <rule>단일 수치를 넣을 때는 primary_pair 또는 secondary_pairs의 실제 수치만 사용합니다.</rule>
    <rule>인물명은 title_name_priority 순서를 우선 참고하고, speaker를 먼저 배치합니다.</rule>
    <rule>동일 인물명은 제목에서 최대 {title_name_repeat_limit}회만 사용합니다. "[후보A] [후보B], [후보B]"처럼 같은 이름을 반복하지 않습니다.</rule>
  </rules>
</poll_focus_title>
""".strip()

def build_competitor_intent_title_instruction(params: Dict[str, Any]) -> str:
    recent_titles = _collect_recent_title_values(params)
    intent_keyword = _resolve_competitor_intent_title_keyword(params)
    if not intent_keyword:
        return ""

    anchor_examples = order_role_keyword_intent_anchor_candidates(intent_keyword, recent_titles)[:3]
    anchor_xml = "\n".join(
        f"  <anchor>{anchor}</anchor>"
        for anchor in anchor_examples
        if str(anchor).strip()
    ) or f"  <anchor>{build_role_keyword_intent_anchor_text(intent_keyword, variant_index=0)}</anchor>"
    argument_xml = "  <argument>본문에서 뽑은 수치·정책·현장 논지 하나</argument>"
    cue_xml = "  <cue>정책·역량·지역 현안</cue>"

    return f"""
<competitor_intent_title priority="critical">
  <keyword>{intent_keyword}</keyword>
  <structure>[경쟁자 출마/거론 표현], [본문 핵심 논지]</structure>
  <tail_selection_order>
    <step priority="1">수치가 있으면 수치+해석을 우선합니다. 예: 31.7% 앞선 이유</step>
    <step priority="2">수치가 없으면 정책·역량 키워드를 고릅니다. 예: AI [샘플시] 해법, 현장 40년</step>
    <step priority="3">위 둘이 약하면 지역 현안을 고릅니다. 예: 제조업 위기 해법, 청년 이탈 대안</step>
  </tail_selection_order>
  <rules>
    <rule>intent_only 경쟁자가 등장하면 제목 앞절은 경쟁자 출마/거론 검색 앵커로 고정하고, 쉼표 뒤만 본문 논지로 확장합니다.</rule>
    <rule>"{intent_keyword}"를 제거하거나 "[경쟁후보명], [후보명]"처럼 인명을 쉼표로 나열하는 구조는 금지합니다.</rule>
    <rule>메인 제목에는 "저는/제가/저의/제 정책" 같은 1인칭 표현을 넣지 않습니다.</rule>
    <rule>쉼표 뒤에는 비전, 가능성, 가상대결, 접전, 경쟁력, 득표율 같은 금지어를 쓰지 말고 본문에서 가장 강한 주장 하나만 반영합니다.</rule>
    <rule>여론조사 본문이면 쉼표 뒤에 실제 수치나 앞서는 이유를 넣어 "[후보명] 31.7% 앞선 배경"처럼 구체화합니다.</rule>
    <rule>최근 제목에서 이미 사용한 경쟁자 앵커 variant는 우선 피합니다.</rule>
  </rules>
  <anchor_examples>
{anchor_xml}
  </anchor_examples>
  <argument_examples>
{argument_xml}
  </argument_examples>
  <argument_cues>
{cue_xml}
  </argument_cues>
</competitor_intent_title>
""".strip()

def build_event_title_policy_instruction(params: Dict[str, Any]) -> str:
    topic = str(params.get('topic') or '')
    context_analysis = params.get('contextAnalysis') if isinstance(params.get('contextAnalysis'), dict) else {}
    role_keyword_policy = params.get('roleKeywordPolicy') if isinstance(params.get('roleKeywordPolicy'), dict) else {}
    user_keywords = _filter_required_title_keywords(
        params.get('userKeywords') if isinstance(params.get('userKeywords'), list) else [],
        role_keyword_policy,
    )

    must_preserve = context_analysis.get('mustPreserve') if isinstance(context_analysis.get('mustPreserve'), dict) else {}
    event_date = str(must_preserve.get('eventDate') or '').strip()
    event_location = str(must_preserve.get('eventLocation') or '').strip()
    date_hint = _extract_date_hint(event_date) or _extract_date_hint(topic)
    location_hint = event_location or (user_keywords[0] if user_keywords else '')
    keyword_line = ', '.join([str(k).strip() for k in user_keywords[:2] if str(k).strip()]) or '핵심 장소 키워드'
    event_name_hint = _detect_event_label(topic)

    return f"""
<title_goal purpose="event_announcement" priority="critical">
  <rule>제목은 행사 안내/초대 목적이 즉시 드러나야 합니다.</rule>
  <rule>추측형/논쟁형/공격형 문구(예: 진짜 속내, 왜 왔냐, 답할까?)와 물음표(?)는 금지합니다.</rule>
  <rule>제목에는 안내형 표현(안내, 초대, 개최, 열립니다, 행사) 또는 행사명("{event_name_hint}")을 포함하십시오.</rule>
  <rule>제목에는 안전한 후킹 단어를 1개 이상 포함하십시오: 현장, 직접, 일정, 안내, 초대, 만남, 참석</rule>
  <rule>추상 카피(예: "핵심 대화 공개", "핵심 메시지 공개")만 단독으로 쓰지 말고 날짜/인물/책제목 같은 고유 정보를 포함하십시오.</rule>
  <rule>가능하면 날짜와 장소를 포함하십시오. 날짜 힌트: {date_hint or '(없음)'} / 장소 힌트: {location_hint or '(없음)'}</rule>
  <rule>SEO 검색어는 제목 앞부분에서 자연스럽게 사용하십시오: {keyword_line}</rule>
</title_goal>
""".strip()


def build_stance_title_policy_instruction(params: Dict[str, Any]) -> str:
    """선언·입장문 intent 용 제목 정책.

    Why: stance_announcement intent 는 body-anchor coverage 게이트에서 면제되지만,
    default 프롬프트에는 여전히 정책 글 전제의 rule (prefer_concrete_policy_over_abstract_honorific,
    aeo_answerable_query_form, require_body_exclusive_anchor_when_present) 들이
    강하게 걸려 있어, LLM 이 그 룰을 만족시키려고 본문에 없는 추상 umbrella 어휘
    (예: "경제 해법 제시", "종합 대책", "구조적 해법") 를 제목에서 **발명**하는
    경향이 있다. 이 instruction 은 그 압력을 상쇄한다. stance intent 에서는
    본문이 담고 있는 입장·관계·계기가 제목의 중심이어야 하고, 본문에 없는
    정책 디테일을 제목에서 새로 만들어 붙이는 것은 금지한다.
    """
    del params  # 현재 구현은 파라미터 없이 고정 규칙만 내보낸다.
    return """
<title_goal purpose="stance_announcement" priority="critical">
  <context>이 글은 선언·입장문(경선 결과·출마/사퇴·입장 표명·인사 등). 정책 해설 글이 아니다.</context>
  <rule>제목은 stance/선언 중심으로 작성하라. 책임·각오·관계·계기·일정이 중심어다. 정책 앵커 인용은 선택이지 필수가 아니다.</rule>
  <rule priority="critical">본문에 명시적으로 등장하지 않는 추상 umbrella 어휘를 제목에서 **새로 만들어 넣지 말라**. 구체 예시: "경제 해법 제시", "정책 비전", "실질적 변화", "종합 대책", "구조적 해법", "경쟁력 강화", "미래 청사진". 본문이 입장·관계·일정 위주라면 제목도 거기에 충실할 것. 본문이 담고 있지 않은 정책 디테일을 제목이 주장하면 허위 사실 리스크.</rule>
  <rule>default 규칙 중 &lt;prefer_concrete_policy_over_abstract_honorific&gt;, &lt;aeo_answerable_query_form&gt;, &lt;require_body_exclusive_anchor_when_present&gt; 가 요구하는 [정책명][수치] 쿼리 형식은 이 intent 에서 **권장이지 강제가 아니다**. 본문에 구체 앵커가 없다면 선언형 평서문이 자연스러운 답이다. 예: "[맥락], 책임지겠습니다", "[맥락], 함께 나아가겠습니다", "[맥락], 주민 여러분께 드리는 인사".</rule>
  <rule>반대로 본문에 실제 정책·수치·조례·사업명이 등장한다면 그 중 1개를 제목에 인용하는 것은 여전히 품질을 높인다. 다만 없는 것을 지어내는 것보다 없이 선언형으로 쓰는 것이 우선이다.</rule>
</title_goal>
""".strip()


def _render_narrative_principle_xml(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if not text:
        return ""

    items: List[str] = []
    for line in text.splitlines():
        normalized = re.sub(r'^\s*[-•]\s*', '', str(line or '').strip())
        normalized = normalized.replace('❌ ', '').replace('✅ ', '').strip()
        if not normalized:
            continue
        items.append(f"  <item>{normalized}</item>")

    if not items:
        return ""

    return "<narrative_principle>\n" + "\n".join(items) + "\n</narrative_principle>"
