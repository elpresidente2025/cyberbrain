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
    _build_argument_tail_candidates,
    _extract_argument_title_cues,
    _is_low_signal_competitor_tail,
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
            {'template': '[지역명] [정책명], [지원항목] 얼마까지?', 'intent': '검색 질문 직접 대응'},
            {'template': '[지역명] [현안], 어떻게 풀까?', 'intent': '문제-해결 프레이밍'},
            {'template': '[민원주제], 실제로 언제 해결되나?', 'intent': '실행 시점 궁금증 유도'},
        ],
        'bad_to_fix': [
            {'bad': '정책에 대해 설명드립니다', 'fix_template': '[정책명], 무엇이 달라졌나?'},
            {'bad': '주거 관련 안내', 'fix_template': '[이슈명], 보상은 어떻게 되나?'},
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
            {'template': '[이슈명], 실제로 뭐가 달라질까?', 'intent': '변화 궁금증 유도'},
            {'template': '[정책쟁점], 어떻게 개선할까?', 'intent': '해법 탐색형'},
            {'template': '[문제명], [대안수]대 대안 제시', 'intent': '분석-대안 구조'},
        ],
        'bad_to_fix': [
            {'bad': '정치 현실에 대해 생각해 봅시다', 'fix_template': '[이슈명], 실제로 뭐가 달라질까?'},
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
            {'bad': '핵심을 알려드립니다', 'fix_template': '[이슈명] 앞에 선 [인물명], 선택의 이유'},
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
            {'bad': '정책 방향과 실행 과제', 'fix_template': '[인물명], [지역명] 시민 곁을 지키겠습니다'},
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
            {'bad': '생각을 전합니다', 'fix_template': '[이슈명], [인물명]의 판단은'},
        ],
    },
}

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
            {'title': '부산 지방선거, 왜 이 남자가 뛰어들었나', 'chars': 20, 'analysis': '왜 질문형 — 구체적 인물 + 미완결 질문'},
            {'title': '부산 지방선거에 뛰어든 부두 노동자의 아들', 'chars': 21, 'analysis': '서사 아크 — 출신 배경이 호기심 유발'},
            {'title': '부산 지방선거, 이재성은 왜 다른가', 'chars': 17, 'analysis': '간결 도발형 — 짧고 강렬한 질문'},
            {'title': '부산 지방선거, 10만 청년이 떠난 도시의 반란', 'chars': 22, 'analysis': '수치+사건형 — 팩트 충격 + 사건 암시'},
            {'title': '부산 지방선거, 원칙만으로 이길 수 있을까', 'chars': 20, 'analysis': '도발적 질문 — 가치 논쟁 유발'}
        ],
        'bad': [
            {'title': '부산 지방선거, AI 전문가 이재성이 경제를 바꾼다', 'problem': '선언형 — 답을 다 알려줘서 클릭할 이유 없음', 'fix': '부산 지방선거, 왜 이 남자가 뛰어들었나'},
            {'title': '이재성 부산 지방선거, AI 3대 강국?', 'problem': '키워드 나열 — 문장이 아님, 의미 불분명', 'fix': '부산 지방선거, 이재성은 왜 다른가'},
            {'title': '결국 터질 게 터졌습니다... 충격적 현실', 'problem': '낚시 자극 — 구체성 제로, 신뢰 파괴', 'fix': '부산 지방선거, 10만 청년이 떠난 도시의 반란'},
            {'title': '부산 지방선거, 이재명 2호 이재성 원칙 내건 그의 선택은', 'problem': '기계적 모방 — 요소 과밀(5개) + 형식적 미완결 꼬리', 'fix': '부산 지방선거, 이재성은 왜 다른가'},
            {'title': '후보의 존중하는 정책', 'problem': '소유격 + 수식어 나열 — "이름의 [형용사형어구]"는 무엇이 존중하는지 불분명, 의미 불완결', 'fix': '지방선거 경선 확정, 원칙이 가른 판세'},
            {'title': '후보의 새로운 일자리', 'problem': '소유격 + 명사 나열 — 서사 없이 키워드만 접착, 클릭 동기 없음', 'fix': '지방선거, 일자리 공약으로 판 바꾼 새 얼굴'}
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
            {'title': '분당구 청년 주거, 월세 지원 얼마까지?', 'chars': 19, 'analysis': '지역 + 혜택 + 질문'},
            {'title': '성남 교통 체증, 어떻게 풀까?', 'chars': 14, 'analysis': '문제 + 해결책 질문'},
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
            {'title': '주차장 부족 지역, 12개월 만에 해결', 'chars': 19, 'analysis': '기간 단축 강조'}
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
            {'title': '분당구 정자동 도시가스, 기금 70억 확보', 'chars': 21, 'analysis': '구/동 + 구체적 예산'},
            {'title': '수지구 풍덕천동 학교 신설, 올 9월 개교', 'chars': 21, 'analysis': '지역 + 시설 + 시기'},
            {'title': '성남시 중원구 보육료 지원, 월 15만원 추가', 'chars': 22, 'analysis': '지역 + 혜택 구체화'},
            {'title': '용인시 기흥구 어르신 요양원, 신청 마감 1주', 'chars': 23, 'analysis': '지역 + 긴급성'},
            {'title': '영통구 광교동 교통 혼잡도, 6개월간 35% 개선', 'chars': 24, 'analysis': '지역 + 개선 수치'}
        ],
        'bad': [
            {'title': '우리 지역을 위해 노력합니다', 'problem': '어디?', 'fix': '분당구 정자동 도시가스 기금 70억'},
            {'title': '지역 현안 해결하겠습니다', 'problem': '무엇을?', 'fix': '용인시 기흥구 어린이집 5곳 신축'}
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
            {'title': '지방 분권 개혁, 실제로 뭐가 달라질까?', 'chars': 19, 'analysis': '이슈 + 궁금증'},
            {'title': '정치 자금 투명성, 어떻게 개선할까?', 'chars': 18, 'analysis': '이슈 + 해결책 질문'},
            {'title': '양극화 문제, 4대 대안 제시', 'chars': 14, 'analysis': '문제 + 대안 개수'},
            {'title': '교육 격차, 재정 투자로 뭐가 달라질까?', 'chars': 19, 'analysis': '수단 + 효과 질문'},
            {'title': '선거 제도 개혁, 왜 시급한가?', 'chars': 15, 'analysis': '이슈 + 당위성'}
        ],
        'bad': [
            {'title': '정치 현실에 대해 생각해 봅시다', 'problem': '너무 철학적', 'fix': '지방 분권 개혁, 실제로 뭐가 달라질까?'},
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
            '\n'
            '【안티패턴】\n'
            '- ❌ 슬로건형 주제를 보고서형 제목으로 바꾸기 ("현안 해결과 미래 비전 제시")\n'
            '- ❌ 자기인증만 강조하고 관계/약속이 비어 있는 제목 ("가장 충직한 의원")\n'
            '- ❌ 본문 문장을 길게 복붙한 다짐문',
        'good': [
            {'title': '문세종, 계양구민 곁을 지키는 인천광역시의원', 'chars': 24, 'analysis': '정체성 + 관계 + 역할'},
            {'title': '문세종, 계양을 지켜온 책임감으로 끝까지 뛰겠습니다', 'chars': 25, 'analysis': '책임감 + 약속'},
            {'title': '문세종, 계양구민에게 더 가까운 인천광역시의원', 'chars': 24, 'analysis': '관계형 슬로건'},
            {'title': '문세종, 계양을 지켜온 책임감으로 다시 뜁니다', 'chars': 23, 'analysis': '정체성 + 다짐'},
            {'title': '문세종, 계양구민 곁에서 끝까지 책임지겠습니다', 'chars': 24, 'analysis': '관계 + 책임 + 약속'}
        ],
        'bad': [
            {'title': '문세종, 계양구 현안 해결과 미래 비전 제시', 'problem': '슬로건형 주제가 보고서형 꼬리로 평탄화됨', 'fix': '문세종, 계양을 지켜온 책임감으로 끝까지 뛰겠습니다'},
            {'title': '문세종, 정책 방향과 실행 과제', 'problem': '다짐형 주제의 정체성/관계가 모두 사라짐', 'fix': '문세종, 계양구민 곁을 지키는 인천광역시의원'},
            {'title': '계양구민에게 가장 충직한 인천광역시의원 되겠다', 'problem': '자기인증만 남고 관계/약속이 평면적', 'fix': '문세종, 계양구민 곁에서 끝까지 책임지겠습니다'}
        ]
    },
    'COMMENTARY': {
         'id': 'COMMENTARY',
         'name': '💬 논평/화자 관점',
         'when': '다른 정치인 논평, 인물 평가, 정치적 입장 표명 시',
         'pattern': '화자 + 관점 표현 + 대상/이슈',
         'naverTip': '화자 이름을 앞에 배치하면 개인 브랜딩 + SEO 효과',
         'good': [
             {'title': '이재성, 박형준 시장 0.7% 성장률 질타', 'chars': 19, 'analysis': '화자 + 대상 + 비판'},
             {'title': '조경태 칭찬한 이재성, 尹 사형 논평', 'chars': 18, 'analysis': '관계 + 화자 + 이슈'},
             {'title': '이재성 "부산 AI 예산 전액 삭감 충격"', 'chars': 19, 'analysis': '화자 + 인용 + 감정'},
             {'title': '박형준 시장 발언에 대한 이재성 반박', 'chars': 18, 'analysis': '대상 + 이슈 + 반응'},
             {'title': '이재성 "박형준, 경제 성적 낙제점"', 'chars': 18, 'analysis': '화자 + 인용'}
         ],
         'bad': [
             {'title': '시장의 발언에 대해', 'problem': '누구? 내용?', 'fix': '이재성, 박형준 시장 발언 반박'},
             {'title': '오늘의 논평입니다', 'problem': '정보 없음', 'fix': '이재성 "부산 예산 삭감 유감"'},
             {'title': '후보, 후보의 되는 정책', 'problem': '이름 반복 뒤에 본문 구절 조각을 접착한 비문', 'fix': '지역 현안, 후보가 말한 해법은'}
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
            'example': '부산 지방선거, 왜 이 남자가 뛰어들었나',
            'triggers': 'keywordPosition+쉼표, impact:원인질문(왜), impact:미완결서사',
            'note': '왜 질문형 — 구체적 인물 + 미완결',
        },
        {
            'id': 'S2',
            'pattern': '[SEO키워드]에 [과거동사형] [인물 배경/정체성 명사]',
            'example': '부산 지방선거에 뛰어든 부두 노동자의 아들',
            'triggers': 'keywordPosition(조사), titleFamily, 서사 아크',
            'note': '서사 아크 — 출신·배경으로 호기심 유발',
        },
        {
            'id': 'S3',
            'pattern': '[SEO키워드], [인물명]은 왜 [형용사+ㄴ가]',
            'example': '부산 지방선거, 이재성은 왜 다른가',
            'triggers': 'keywordPosition+쉼표, authorIncluded, impact:원인질문',
            'note': '간결 도발형 — 짧고 강렬',
        },
        {
            'id': 'S4',
            'pattern': '[SEO키워드], [수치][단위] [주체]이 [과거동사] [지역/대상]의 [사건명사]',
            'example': '부산 지방선거, 10만 청년이 떠난 도시의 반란',
            'triggers': 'keywordPosition+쉼표, numbers, impact:미완결서사',
            'note': '수치+사건형 — 팩트 충격 + 암시',
        },
        {
            'id': 'S5',
            'pattern': '[SEO키워드], [가치/수단]만으로 [동사] 수 있을까',
            'example': '부산 지방선거, 원칙만으로 이길 수 있을까',
            'triggers': 'keywordPosition+쉼표, impact:질문형(까)',
            'note': '도발적 질문 — 가치 논쟁',
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
            'example': '분당구 청년 주거, 월세 지원 얼마까지?',
            'triggers': 'impact:질문형(?), keywordPosition',
            'note': '지역+혜택 질문',
        },
        {
            'id': 'S2',
            'pattern': '[지역] [현안], 어떻게 풀까?',
            'example': '성남 교통 체증, 어떻게 풀까?',
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
            'example': '분당구 정자동 도시가스, 기금 70억 확보',
            'triggers': 'numbers, keywordPosition, 초지역 SEO',
            'note': '구/동 + 구체적 예산',
        },
        {
            'id': 'S2',
            'pattern': '[구] [동] [시설] 신설, [시기] 개교',
            'example': '수지구 풍덕천동 학교 신설, 올 9월 개교',
            'triggers': 'keywordPosition, 시기 명시',
            'note': '지역 + 시설 + 시기',
        },
        {
            'id': 'S3',
            'pattern': '[시] [구] [정책] 지원, [단위] [수치][단위] 추가',
            'example': '성남시 중원구 보육료 지원, 월 15만원 추가',
            'triggers': 'numbers, keywordPosition',
            'note': '지역 + 혜택 구체화',
        },
        {
            'id': 'S4',
            'pattern': '[시] [구] [대상] [시설], 신청 마감 [기간]',
            'example': '용인시 기흥구 어르신 요양원, 신청 마감 1주',
            'triggers': 'numbers, 긴급성',
            'note': '지역 + 긴급 행동',
        },
        {
            'id': 'S5',
            'pattern': '[구] [동] [지표], [기간]간 [수치]% 개선',
            'example': '영통구 광교동 교통 혼잡도, 6개월간 35% 개선',
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
            'pattern': '[이슈명], 실제로 뭐가 달라질까?',
            'example': '지방 분권 개혁, 실제로 뭐가 달라질까?',
            'triggers': 'impact:질문형(?)',
            'note': '이슈 + 변화 궁금증',
        },
        {
            'id': 'S2',
            'pattern': '[정책쟁점], 어떻게 개선할까?',
            'example': '정치 자금 투명성, 어떻게 개선할까?',
            'triggers': 'impact:질문형(?), impact:원인질문(어떻게)',
            'note': '쟁점 + 해결 질문',
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
            'pattern': '[이슈명], [수단명사]로 뭐가 달라질까?',
            'example': '교육 격차, 재정 투자로 뭐가 달라질까?',
            'triggers': 'impact:질문형(?)',
            'note': '수단 + 효과 질문',
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
            'pattern': '[인물명], [지역/대상] 곁을 지키는 [역할/직함명]',
            'example': '문세종, 계양구민 곁을 지키는 인천광역시의원',
            'triggers': 'authorIncluded, titleFamily, keywordPosition+쉼표',
            'note': '정체성 + 관계 + 역할',
        },
        {
            'id': 'S2',
            'pattern': '[인물명], [지역]을 지켜온 책임감으로 끝까지 뛰겠습니다',
            'example': '문세종, 계양을 지켜온 책임감으로 끝까지 뛰겠습니다',
            'triggers': 'authorIncluded, keywordPosition+쉼표',
            'note': '책임감 + 약속',
        },
        {
            'id': 'S3',
            'pattern': '[인물명], [지역/대상]에게 더 가까운 [역할/직함명]',
            'example': '문세종, 계양구민에게 더 가까운 인천광역시의원',
            'triggers': 'authorIncluded, keywordPosition+쉼표',
            'note': '관계형 슬로건',
        },
        {
            'id': 'S4',
            'pattern': '[인물명], [지역]을 지켜온 책임감으로 다시 뜁니다',
            'example': '문세종, 계양을 지켜온 책임감으로 다시 뜁니다',
            'triggers': 'authorIncluded, keywordPosition+쉼표',
            'note': '정체성 + 다짐',
        },
        {
            'id': 'S5',
            'pattern': '[인물명], [지역/대상] 곁에서 끝까지 책임지겠습니다',
            'example': '문세종, 계양구민 곁에서 끝까지 책임지겠습니다',
            'triggers': 'authorIncluded, keywordPosition+쉼표',
            'note': '관계 + 책임 + 약속',
        },
    ],
    'COMMENTARY': [
        {
            'id': 'S1',
            'pattern': '[화자], [대상] [수치][단위] [비판명사]',
            'example': '이재성, 박형준 시장 0.7% 성장률 질타',
            'triggers': 'authorIncluded+앞배치, numbers, keywordPosition+쉼표',
            'note': '화자 + 대상 + 비판',
        },
        {
            'id': 'S2',
            'pattern': '[제3자] 칭찬한 [화자], [이슈] 논평',
            'example': '조경태 칭찬한 이재성, 尹 사형 논평',
            'triggers': 'authorIncluded, 관계+화자, keywordPosition',
            'note': '관계 + 이슈 논평',
        },
        {
            'id': 'S3',
            'pattern': '[화자] "[이슈에 대한 인용문]"',
            'example': '이재성 "부산 AI 예산 전액 삭감 충격"',
            'triggers': 'authorIncluded+앞배치, impact:인용문',
            'note': '화자 + 인용 + 감정',
        },
        {
            'id': 'S4',
            'pattern': '[대상] [사건/발언]에 대한 [화자] 반박',
            'example': '박형준 시장 발언에 대한 이재성 반박',
            'triggers': 'authorIncluded, 대상+반응',
            'note': '대상 + 이슈 + 반응',
        },
        {
            'id': 'S5',
            'pattern': '[화자] "[대상], [평가]"',
            'example': '이재성 "박형준, 경제 성적 낙제점"',
            'triggers': 'authorIncluded+앞배치, impact:인용문',
            'note': '화자 + 인용 평가',
        },
    ],
}


def build_title_skeleton_protocol(type_id: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Return a structured construction protocol block for the selected title family.

    The LLM must pick exactly one skeleton and fill slots with current topic/keyword/author
    data, instead of inventing a new structure. Each skeleton is labeled with the scoring
    features it triggers so the model can optimize for the rubric directly.
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

    skeleton_xml_lines: List[str] = []
    for sk in skeletons:
        if not isinstance(sk, dict):
            continue
        sk_id = str(sk.get('id') or '').strip()
        pattern = str(sk.get('pattern') or '').strip()
        example = str(sk.get('example') or '').strip()
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
    slot_hint_xml = '\n'.join(slot_hint_lines) or '    <slot name="(없음)">입력 정보에서 추출</slot>'

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
    <rule>skeleton의 종결 어미(~나, ~까, ~까요?, ~겠습니다, ~었어요, 등)와 구두점(?, →, "...", 쉼표)을 임의로 바꾸지 말 것. 구조의 핵심이다.</rule>
    <rule>SEO 키워드가 skeleton 앞쪽 슬롯에 이미 포함돼 있으면 그대로 두고, 없으면 제목 맨 앞(0-10자)에 배치 후 쉼표/조사로 분리하라.</rule>
  </phase_2>

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
    </checklist>
    <fallback>checklist 중 하나라도 실패하면 phase_1로 돌아가 다른 skeleton을 선택하라. 동일 skeleton을 변형하는 것은 금지.</fallback>
  </phase_3>
</title_construction_protocol>
""".strip()

def _build_role_keyword_title_policy_instruction(role_keyword_policy: Dict[str, Any]) -> str:
    entries = role_keyword_policy.get("entries") if isinstance(role_keyword_policy, dict) else {}
    if not isinstance(entries, dict) or not entries:
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
            else:
                lines.append(
                    f'  <rule keyword="{keyword}" mode="blocked">'
                    f'"{keyword}"는 입력 근거의 현재 직함("{source_role}")과 충돌하고 '
                    f"target role 근거도 없으므로 제목에서 사용 금지."
                    f"</rule>"
                )
    if not lines:
        return ""
    return "<role_keyword_policy>\n" + "\n".join(lines) + "\n</role_keyword_policy>"

def get_keyword_strategy_instruction(user_keywords: List[str], keywords: List[str], role_keyword_policy: Optional[Dict[str, Any]] = None) -> str:
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
                unique_hint = f'"{", ".join(unique_words)}"를 제목 뒤쪽에 녹여넣기' if unique_words else '공통 어절로 자동 충족'
                title_keyword_rule = f"""
<keyword_placement type="similar">
  <description>두 검색어("{primary_kw}", "{secondary_kw}")가 공통 어절을 공유</description>
  <rule type="must">제목은 반드시 "{primary_kw}"로 시작</rule>
  <rule type="must">"{secondary_kw}"는 어절 단위로 해체하여 자연스럽게 배치 ({unique_hint})</rule>
  <example>"서면 영광도서, &lt;보고있나, 부산&gt; 출판기념회에 초대합니다"</example>
  <example>"부산 대형병원, 암센터 확충으로 고령 환자도 안심"</example>
</keyword_placement>
"""
            else:
                title_keyword_rule = f"""
<keyword_placement type="independent">
  <description>두 검색어("{primary_kw}", "{secondary_kw}")가 독립적</description>
  <rule type="must">제목은 반드시 "{primary_kw}"로 시작</rule>
  <rule type="must">"{secondary_kw}"는 제목 뒤쪽에 자연스럽게 배치</rule>
  <example>"계양산 러브버그 방역, 계양구청에 적극 구제 촉구"</example>
  <example>"성수역 3번 출구, 확장 공사 전현희 덕이라는 코레일 노조"</example>
  <example>"부산 디즈니랜드 유치, 서부산 발전의 열쇠?"</example>
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
    <good>"청년 기본소득, 분당구 월 50만원 지원"</good>
  </examples>
</front_third_rule>

<keyword_separator priority="critical">
  <description>키워드 직후에 쉼표(,) 또는 조사(에, 의, 에서 등)를 넣어 다음 단어와 분리하세요. 네이버는 공백만으로는 키워드 경계를 인식하지 못합니다.</description>
  <examples>
    <good reason="키워드=부산 지방선거">"부산 지방선거, 왜 이 남자가"</good>
    <good reason="키워드=부산 지방선거">"부산 지방선거에 뛰어든 부두 노동자"</good>
    <bad reason="잘못 인식: 부산 지방선거 이재성 원칙">"부산 지방선거 이재성 원칙"</bad>
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

</seo_keyword_strategy>
"""
    except Exception as e:
        logger.error(f'Error in get_keyword_strategy_instruction: {e}')
        return ''

def _build_few_shot_slot_values(params: Dict[str, Any]) -> Dict[str, str]:
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


def build_user_provided_few_shot_instruction(type_id: str, params: Optional[Dict[str, Any]] = None) -> str:
    requested_type_id = str(type_id or '').strip()
    resolved_type_id = requested_type_id
    few_shot = USER_PROVIDED_TITLE_FEW_SHOT.get(resolved_type_id)
    if not few_shot:
        logger.info("[TitleGen] 사용자 few-shot 미정의 타입: %s", resolved_type_id)
        return ''

    slot_values = _build_few_shot_slot_values(params or {})
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
    <rule>동일 인물명은 제목에서 최대 {title_name_repeat_limit}회만 사용합니다. "전재수 이재성, 이재성"처럼 같은 이름을 반복하지 않습니다.</rule>
  </rules>
</poll_focus_title>
""".strip()

def build_competitor_intent_title_instruction(params: Dict[str, Any]) -> str:
    recent_titles = _collect_recent_title_values(params)
    intent_keyword = _resolve_competitor_intent_title_keyword(params)
    if not intent_keyword:
        return ""

    anchor_examples = order_role_keyword_intent_anchor_candidates(intent_keyword, recent_titles)[:3]
    argument_examples = [
        candidate
        for candidate in _build_argument_tail_candidates("", params)
        if str(candidate).strip() and not _is_low_signal_competitor_tail(candidate)
    ][:4]
    cue_examples = _extract_argument_title_cues(params)[:4]
    anchor_xml = "\n".join(
        f"  <anchor>{anchor}</anchor>"
        for anchor in anchor_examples
        if str(anchor).strip()
    ) or f"  <anchor>{build_role_keyword_intent_anchor_text(intent_keyword, variant_index=0)}</anchor>"
    argument_xml = "\n".join(
        f"  <argument>{argument}</argument>"
        for argument in argument_examples
        if str(argument).strip()
    ) or "  <argument>이재성 31.7% 앞선 배경</argument>"
    cue_xml = "\n".join(
        f"  <cue>{cue}</cue>"
        for cue in cue_examples
        if str(cue).strip()
    ) or "  <cue>정책·역량·지역 현안</cue>"

    return f"""
<competitor_intent_title priority="critical">
  <keyword>{intent_keyword}</keyword>
  <structure>[경쟁자 출마/거론 표현], [본문 핵심 논지]</structure>
  <tail_selection_order>
    <step priority="1">수치가 있으면 수치+해석을 우선합니다. 예: 31.7% 앞선 이유</step>
    <step priority="2">수치가 없으면 정책·역량 키워드를 고릅니다. 예: AI 부산 해법, 현장 40년</step>
    <step priority="3">위 둘이 약하면 지역 현안을 고릅니다. 예: 제조업 위기 해법, 청년 이탈 대안</step>
  </tail_selection_order>
  <rules>
    <rule>intent_only 경쟁자가 등장하면 제목 앞절은 경쟁자 출마/거론 검색 앵커로 고정하고, 쉼표 뒤만 본문 논지로 확장합니다.</rule>
    <rule>"{intent_keyword}"를 제거하거나 "주진우, 이재성"처럼 인명을 쉼표로 나열하는 구조는 금지합니다.</rule>
    <rule>메인 제목에는 "저는/제가/저의/제 정책" 같은 1인칭 표현을 넣지 않습니다.</rule>
    <rule>쉼표 뒤에는 비전, 가능성, 가상대결, 접전, 경쟁력, 득표율 같은 금지어를 쓰지 말고 본문에서 가장 강한 주장 하나만 반영합니다.</rule>
    <rule>여론조사 본문이면 쉼표 뒤에 실제 수치나 앞서는 이유를 넣어 "이재성 31.7% 앞선 배경"처럼 구체화합니다.</rule>
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
