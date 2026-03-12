
import asyncio
import re
import logging
from difflib import SequenceMatcher
from typing import Dict, Any, List, Optional
from .election_rules import get_election_stage
from .editorial import TITLE_SPEC
from .role_keyword_policy import (
    build_role_keyword_intent_text,
    is_role_keyword_intent_surface,
    should_block_role_keyword,
)

logger = logging.getLogger(__name__)

TITLE_LENGTH_HARD_MIN = TITLE_SPEC['hardMin']
TITLE_LENGTH_HARD_MAX = TITLE_SPEC['hardMax']
TITLE_LENGTH_OPTIMAL_MIN = TITLE_SPEC['optimalMin']
TITLE_LENGTH_OPTIMAL_MAX = TITLE_SPEC['optimalMax']

EVENT_NAME_MARKERS = (
    '출판기념회',
    '간담회',
    '설명회',
    '토론회',
    '기자회견',
    '세미나',
    '강연',
    '북토크',
    '토크콘서트',
    '팬미팅',
)

SLOT_PLACEHOLDER_NAMES = (
    '지역명', '장소명', '인물명', '행사명', '날짜', '주제명', '정책명', '사업명',
    '수치', '수량', '금액', '단위', '성과지표', '지원항목', '현안', '민원주제',
    '이슈명', '정책쟁점', '문제명', '대안수', '이전값', '현재값', '개선폭',
    '기존안', '개선안', '비용항목', '이전금액', '현재금액', '개관시기', '기간',
    '개선수치', '법안명', '핵심지원', '조례명', '핵심변경', '숫자', '핵심혜택',
    '핵심변화', '연도/분기', '보고서명', '핵심성과수', '월/분기', '업무명',
    '건수', '정기브리핑명', '월호', '핵심주제', '예산항목', '혜택수치', '성과수',
)

# 사용자 제공 "네이버 블로그 제목 전략 (정치인 특화)"를
# 고정 문구가 아닌 슬롯 기반 템플릿 few-shot으로 주입한다.
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
            '- ❌ 예시 제목의 어미만 복사하기 (패턴 모방 ≠ 긴장감)',
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
            {'title': '부산 지방선거, 이재명 2호 이재성 원칙 내건 그의 선택은', 'problem': '기계적 모방 — 요소 과밀(5개) + 형식적 미완결 꼬리', 'fix': '부산 지방선거, 이재성은 왜 다른가'}
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
            {'title': '궁금한 점을 해결해 드립니다', 'problem': '너무 범용적', 'fix': '아이 교육비, 지원 금액 얼마나?'}
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
             {'title': '오늘의 논평입니다', 'problem': '정보 없음', 'fix': '이재성 "부산 예산 삭감 유감"'}
         ]
     }
}

def detect_content_type(content_preview: str, category: str) -> str:
    try:
        text = content_preview.lower()
        
        has_numbers = re.search(r'\d+억|\d+만원|\d+%|\d+명|\d+건|\d+가구|\d+곳', content_preview)
        has_comparison = re.search(r'→|에서|으로|전년|대비|개선|감소|증가|변화', text)
        has_question = re.search(r'\?|어떻게|무엇|왜|얼마|언제', text)
        has_legal_terms = re.search(r'법안|조례|법률|제도|개정|발의|통과', text)
        has_time_terms = re.search(r'2025년|상반기|하반기|분기|월간|연간|보고서|리포트', text)
        has_local_terms = re.search(r'[가-힣]+(동|구|군|시|읍|면|리)(?:[가-힣]|\s|,|$)', content_preview)
        has_issue_terms = re.search(r'개혁|분권|양극화|격차|투명성|문제점|대안', text)
        has_commentary_terms = re.search(r'칭찬|질타|비판|논평|평가|소신|침묵|역부족|낙제|심판', text)
        has_politician_names = re.search(r'박형준|조경태|윤석열|이재명|한동훈', content_preview)
        
        # Priority for user content signals
        if has_time_terms and ('보고' in text or '리포트' in text or '현황' in text):
            return 'TIME_BASED'
        if has_legal_terms:
            return 'EXPERT_KNOWLEDGE'
        if has_commentary_terms and has_politician_names:
            return 'COMMENTARY'
        if has_comparison and has_numbers:
            return 'COMPARISON'
        if has_question:
            return 'QUESTION_ANSWER'
        if has_numbers and not has_issue_terms:
            return 'DATA_BASED'
        if has_issue_terms and not has_local_terms:
            return 'ISSUE_ANALYSIS'
        if has_local_terms:
            return 'LOCAL_FOCUSED'
        
        category_mapping = {
            'activity-report': 'DATA_BASED',
            'policy-proposal': 'EXPERT_KNOWLEDGE',
            'local-issues': 'LOCAL_FOCUSED',
            'current-affairs': 'ISSUE_ANALYSIS',
            'daily-communication': 'VIRAL_HOOK', # Changed to VIRAL_HOOK for daily coms
            'bipartisan-cooperation': 'COMMENTARY'
        }
        
        return category_mapping.get(category, 'VIRAL_HOOK') # Default to VIRAL_HOOK
    except Exception as e:
        logger.error(f'Error in detect_content_type: {e}')
        return 'VIRAL_HOOK'

def extract_numbers_from_content(content: str) -> Dict[str, Any]:
    if not content:
        return {'numbers': [], 'instruction': ''}
        
    try:
        patterns = [
            r'\d+(?:,\d{3})*억원?',
            r'\d+(?:,\d{3})*만원?',
            r'\d+(?:\.\d+)?%',
            r'\d+(?:,\d{3})*명',
            r'\d+(?:,\d{3})*건',
            r'\d+(?:,\d{3})*가구',
            r'\d+(?:,\d{3})*곳',
            r'\d+(?:,\d{3})*개',
            r'\d+(?:,\d{3})*회',
            r'\d+배',
            r'\d+(?:,\d{3})*원',
            r'\d+일',
            r'\d+개월',
            r'\d+년',
            r'\d+분기'
        ]
        
        all_matches = set()
        for pattern in patterns:
            matches = re.findall(pattern, content)
            all_matches.update(matches)
            
        numbers = list(all_matches)
        
        if not numbers:
            return {
                'numbers': [],
                'instruction': '\\n【숫자 제약】본문에 구체적 수치가 없습니다. 숫자 없이 제목을 작성하세요.\\n'
            }
            
        formatted_numbers = ', '.join(numbers[:10])
        if len(numbers) > 10:
            formatted_numbers += f' (외 {len(numbers) - 10}개)'
            
        instruction = f"""
<number_validation priority="critical">
  <description>본문에 등장하는 숫자만 사용 가능</description>
  <allowed_numbers>{formatted_numbers}</allowed_numbers>
  <rule type="must-not">위 목록에 없는 숫자는 절대 제목에 넣지 마세요</rule>
  <examples>
    <good>본문에 "274명"이 있으면 "청년 일자리 274명"</good>
    <bad reason="날조">본문에 "85억"이 없는데 "지원금 85억"</bad>
  </examples>
</number_validation>
"""
        return {'numbers': numbers, 'instruction': instruction}
    except Exception as e:
        logger.error(f'Error in extract_numbers_from_content: {e}')
        return {'numbers': [], 'instruction': ''}

def get_election_compliance_instruction(status: str) -> str:
    try:
        election_stage = get_election_stage(status)
        is_pre_candidate = election_stage.get('name') == 'STAGE_1'
        
        if not is_pre_candidate: return ''
        
        return f"""
<election_compliance status="{status}" stage="pre-candidate" priority="critical">
  <description>선거법 준수 (현재 상태: {status} - 예비후보 등록 이전)</description>
  <banned_expressions>
    <expression>"약속", "공약", "약속드립니다"</expression>
    <expression>"당선되면", "당선 후"</expression>
    <expression>"~하겠습니다" (공약성 미래 약속)</expression>
    <expression>"지지해 주십시오"</expression>
  </banned_expressions>
  <allowed_expressions>
    <expression>"정책 방향", "정책 제시", "비전 공유"</expression>
    <expression>"연구하겠습니다", "노력하겠습니다"</expression>
    <expression>"추진", "추구", "검토"</expression>
  </allowed_expressions>
  <examples>
    <bad>"청년 기본소득, 꼭 약속드리겠습니다"</bad>
    <good>"청년 기본소득, 정책 방향 제시"</good>
  </examples>
</election_compliance>
"""
    except Exception as e:
        logger.error(f'Error in get_election_compliance_instruction: {e}')
        return ''

def are_keywords_similar(kw1: str, kw2: str) -> bool:
    """
    두 키워드가 유사한지 판별 (공통 어절이 있는지)
    예: "서면 영광도서", "부산 영광도서" → 공통 "영광도서" → 유사
    예: "계양산 러브버그 방역", "계양구청" → 공통 없음 → 독립
    """
    if not kw1 or not kw2:
        return False
    words1 = kw1.split()
    words2 = kw2.split()
    return any(w in words2 and len(w) >= 2 for w in words1)

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
                f'"{build_role_keyword_intent_text(keyword, context="title", variant_index=0)}"처럼 '
                f'출마/거론 의도를 붙여 표현할 것.'
                f"</rule>"
            )
        elif mode == "blocked":
            source_role = str(entry.get("sourceRole") or "").strip() or "입력 근거"
            lines.append(
                f'  <rule keyword="{keyword}" mode="blocked">'
                f'"{keyword}"는 입력 근거의 현재 직함("{source_role}")과 충돌하고 '
                f"target role 근거도 없으므로 제목에서 사용 금지."
                f"</rule>"
            )
    if not lines:
        return ""
    return "<role_keyword_policy>\n" + "\n".join(lines) + "\n</role_keyword_policy>"


def _filter_required_title_keywords(
    user_keywords: List[str],
    role_keyword_policy: Optional[Dict[str, Any]] = None,
) -> List[str]:
    filtered: List[str] = []
    for item in user_keywords or []:
        keyword = str(item or "").strip()
        if not keyword:
            continue
        if should_block_role_keyword(role_keyword_policy, keyword):
            continue
        filtered.append(keyword)
    return filtered


def _validate_role_keyword_title_policy(title: str, role_keyword_policy: Dict[str, Any]) -> Dict[str, Any]:
    cleaned_title = str(title or "").strip()
    if not cleaned_title:
        return {"passed": True}
    entries = role_keyword_policy.get("entries") if isinstance(role_keyword_policy, dict) else {}
    if not isinstance(entries, dict) or not entries:
        return {"passed": True}

    for keyword, raw_entry in entries.items():
        entry = raw_entry if isinstance(raw_entry, dict) else {}
        normalized_keyword = str(keyword or "").strip()
        if not normalized_keyword or normalized_keyword not in cleaned_title:
            continue
        mode = str(entry.get("mode") or "").strip()
        start_index = cleaned_title.find(normalized_keyword)
        end_index = start_index + len(normalized_keyword)
        if mode == "blocked":
            source_role = str(entry.get("sourceRole") or "").strip() or "입력 근거"
            return {
                "passed": False,
                "reason": f'"{normalized_keyword}"는 입력 근거의 현재 직함("{source_role}")과 충돌해 제목에 사용할 수 없습니다.',
            }
        if mode == "intent_only" and not is_role_keyword_intent_surface(cleaned_title, start_index, end_index):
            return {
                "passed": False,
                "reason": (
                    f'"{normalized_keyword}"는 완성된 호칭처럼 쓰지 말고 '
                    f'"{build_role_keyword_intent_text(normalized_keyword, context="title", variant_index=0)}"처럼 '
                    "출마/거론 의도를 붙여 제목에 사용하세요."
                ),
            }
    return {"passed": True}


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


def _detect_event_label(topic: str) -> str:
    for marker in EVENT_NAME_MARKERS:
        if marker in (topic or ''):
            return marker
    return '행사'


def _build_few_shot_slot_values(params: Dict[str, Any]) -> Dict[str, str]:
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
    first_number = str(numbers[0]).strip() if numbers else '수치'

    return {
        '지역명': primary_kw or location_hint or '지역명',
        '장소명': location_hint or primary_kw or '장소명',
        '인물명': full_name or '인물명',
        '행사명': event_label or '행사명',
        '날짜': date_hint or '날짜',
        '주제명': topic_label or '주제명',
        '정책명': topic_label or '정책명',
        '사업명': topic_label or '사업명',
        '수치': first_number,
        '수량': first_number,
        '금액': first_number,
        '단위': '명',
        '성과지표': '개선',
        '지원항목': '지원',
        '현안': topic_label or '현안',
        '민원주제': topic_label or '민원 주제',
        '이슈명': topic_label or '이슈명',
        '정책쟁점': topic_label or '정책 쟁점',
        '문제명': topic_label or '문제명',
        '대안수': '3',
        '이전값': '기존 수치',
        '현재값': '개선 수치',
        '개선폭': '대폭',
        '기존안': '기존안',
        '개선안': '개선안',
        '비용항목': '운영비',
        '이전금액': '기존 예산',
        '현재금액': '절감 예산',
        '개관시기': '올해 하반기',
        '기간': '6개월',
        '개선수치': '35',
        '법안명': topic_label or '법안명',
        '핵심지원': '지원 확대',
        '조례명': topic_label or '조례명',
        '핵심변경': '핵심 조항',
        '숫자': '3',
        '핵심혜택': '핵심 혜택',
        '핵심변화': '핵심 변화',
        '연도/분기': '2026년 상반기',
        '보고서명': '활동 보고서',
        '핵심성과수': '5',
        '월/분기': '6월',
        '업무명': '민원 처리',
        '건수': '1,234',
        '정기브리핑명': '월간 브리핑',
        '월호': '7월호',
        '핵심주제': topic_label or '핵심 주제',
        '예산항목': '국비',
        '혜택수치': '월 15만원',
        '성과수': '5',
        '업무': '핵심 업무',
    }


def _render_slot_template(template: str, slot_values: Dict[str, str]) -> str:
    rendered = str(template or '')
    for slot_name, slot_value in slot_values.items():
        rendered = rendered.replace(f'[{slot_name}]', str(slot_value))
    return re.sub(r'\s+', ' ', rendered).strip()


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


def _extract_date_hint(text: str) -> str:
    if not text:
        return ''
    month_day = re.search(r'(\d{1,2}\s*월\s*\d{1,2}\s*일)', text)
    if month_day:
        return re.sub(r'\s+', ' ', month_day.group(1)).strip()
    iso_like = re.search(r'(\d{4}[./-]\d{1,2}[./-]\d{1,2})', text)
    if iso_like:
        return iso_like.group(1).strip()
    return ''


def _contains_date_hint(title: str, date_hint: str) -> bool:
    if not title:
        return False
    if date_hint:
        no_space_title = re.sub(r'\s+', '', title)
        no_space_hint = re.sub(r'\s+', '', date_hint)
        if no_space_hint in no_space_title:
            return True
        month_day = re.search(r'(\d{1,2})\s*월\s*(\d{1,2})\s*일', date_hint)
        if month_day:
            m, d = month_day.group(1), month_day.group(2)
            if re.search(fr'{m}\s*월\s*{d}\s*일', title):
                return True
    return bool(_extract_date_hint(title))


def _normalize_digit_token(value: str) -> str:
    digits = re.sub(r'\D', '', str(value or ''))
    if not digits:
        return ''
    normalized = digits.lstrip('0')
    return normalized or '0'


def _extract_digit_tokens(text: str) -> List[str]:
    if not text:
        return []
    tokens = []
    seen = set()
    for match in re.findall(r'\d+', str(text)):
        normalized = _normalize_digit_token(match)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(normalized)
    return tokens


def _split_hint_tokens(text: str) -> List[str]:
    if not text:
        return []
    clean = re.sub(r'[\(\)\[\]\{\},]', ' ', str(text))
    tokens = [t.strip() for t in re.split(r'\s+', clean) if t.strip()]
    result: List[str] = []
    for token in tokens:
        if len(token) >= 2:
            result.append(token)
    return result


BOOK_TITLE_QUOTE_PATTERNS = (
    ('angle', re.compile(r'<\s*([^<>]{2,80}?)\s*>')),
    ('double_angle', re.compile(r'《\s*([^《》]{2,80}?)\s*》')),
    ('single_angle', re.compile(r'〈\s*([^〈〉]{2,80}?)\s*〉')),
    ('double_quote', re.compile(r'"\s*([^"\n]{2,80}?)\s*"')),
    ('single_quote', re.compile(r"'\s*([^'\n]{2,80}?)\s*'")),
    ('curly_double_quote', re.compile(r'“\s*([^”\n]{2,80}?)\s*”')),
    ('curly_single_quote', re.compile(r'‘\s*([^’\n]{2,80}?)\s*’')),
    ('corner_quote', re.compile(r'「\s*([^「」]{2,80}?)\s*」')),
    ('white_corner_quote', re.compile(r'『\s*([^『』]{2,80}?)\s*』')),
)
BOOK_TITLE_WRAPPER_PAIRS = (
    ('<', '>'),
    ('《', '》'),
    ('〈', '〉'),
    ('「', '」'),
    ('『', '』'),
    ('"', '"'),
    ("'", "'"),
    ('“', '”'),
    ('‘', '’'),
)
BOOK_TITLE_CONTEXT_MARKERS = (
    '책',
    '저서',
    '도서',
    '신간',
    '출간',
    '출판',
    '북토크',
    '토크콘서트',
    '출판행사',
    '출판기념회',
    '제목',
)
BOOK_TITLE_EVENT_MARKERS = (
    '출판기념회',
    '북토크',
    '토크콘서트',
    '출판행사',
    '출간기념',
)
BOOK_TITLE_DISALLOWED_TOKENS = (
    '출판기념회',
    '북토크',
    '토크콘서트',
    '행사',
    '초대',
    '안내',
    '개최',
)
BOOK_TITLE_LOCATION_HINTS = (
    '도서',
    '센터',
    '홀',
    '광장',
    '시청',
    '구청',
)
BOOK_TITLE_LOCATION_SUFFIXES = (
    '도서',
    '센터',
    '홀',
    '광장',
    '시청',
    '구청',
)


def _normalize_book_title_candidate(text: str) -> str:
    normalized = str(text or '').strip()
    if not normalized:
        return ''

    while True:
        changed = False
        for left, right in BOOK_TITLE_WRAPPER_PAIRS:
            if normalized.startswith(left) and normalized.endswith(right) and len(normalized) > len(left) + len(right):
                normalized = normalized[len(left):len(normalized) - len(right)].strip()
                changed = True
        if not changed:
            break

    normalized = normalize_title_surface(normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip(' ,')
    normalized = re.sub(r'^[\-–—:;]+', '', normalized).strip()
    normalized = re.sub(r'[\-–—:;]+$', '', normalized).strip()
    return normalized


def _collect_book_title_candidates(topic: str) -> List[Dict[str, Any]]:
    text = str(topic or '').strip()
    if not text:
        return []

    candidates: List[Dict[str, Any]] = []

    for source, pattern in BOOK_TITLE_QUOTE_PATTERNS:
        for match in pattern.finditer(text):
            raw = str(match.group(1) or '').strip()
            if not raw:
                continue
            candidates.append(
                {
                    'raw': raw,
                    'start': int(match.start(1)),
                    'end': int(match.end(1)),
                    'source': source,
                }
            )

    event_pattern = re.compile(
        r'([가-힣A-Za-z0-9][^\n]{1,80}?)\s*(?:출판기념회|북토크|토크콘서트|출판행사)'
    )
    for match in event_pattern.finditer(text):
        raw = str(match.group(1) or '').strip()
        if not raw:
            continue
        candidates.append(
            {
                'raw': raw,
                'start': int(match.start(1)),
                'end': int(match.end(1)),
                'source': 'event_context',
            }
        )

    after_book_pattern = re.compile(
        r'(?:^|[\s\(\[\{\'"“‘<《])(?:책|저서|도서|신간|작품|제목)\s*(?:(?:은|는|이|가)\s+|[:：]\s*)?([^\n]{2,80})'
    )
    for match in after_book_pattern.finditer(text):
        raw = str(match.group(1) or '').strip()
        if not raw:
            continue
        clipped = re.split(r'(?:출판기념회|북토크|토크콘서트|출판행사|안내|초대|개최|에서|현장)', raw, maxsplit=1)[0].strip()
        if clipped:
            candidates.append(
                {
                    'raw': clipped,
                    'start': int(match.start(1)),
                    'end': int(match.start(1) + len(clipped)),
                    'source': 'book_context',
                }
            )

    return candidates


def _score_book_title_candidate(
    candidate: Dict[str, Any],
    topic: str,
    full_name: str,
) -> int:
    raw = str(candidate.get('raw') or '')
    text = _normalize_book_title_candidate(raw)
    if not text:
        return -999

    if not re.search(r'[가-힣A-Za-z0-9]', text):
        return -999

    score = 0
    source = str(candidate.get('source') or '')
    start = int(candidate.get('start') or 0)
    end = int(candidate.get('end') or start)
    topic_text = str(topic or '')

    if source in {'angle', 'double_angle', 'single_angle', 'double_quote', 'single_quote', 'curly_double_quote', 'curly_single_quote', 'corner_quote', 'white_corner_quote'}:
        score += 5
    elif source in {'author_event_context', 'event_context', 'book_context'}:
        score += 3

    if 4 <= len(text) <= 30:
        score += 3
    elif 2 <= len(text) <= 45:
        score += 1
    else:
        score -= 4

    if len(text) <= 3:
        score -= 5

    for token in BOOK_TITLE_DISALLOWED_TOKENS:
        if token in text:
            score -= 8

    if full_name and text == full_name:
        score -= 8

    if re.fullmatch(r'[\d\s.,:/-]+', text):
        score -= 6
    if re.search(r'\d+\s*월(?:\s*\d+\s*일)?', text):
        score -= 10
    if any(ch in text for ch in '<>《》〈〉「」『』'):
        score -= 8

    left_context = topic_text[max(0, start - 22):start]
    right_context = topic_text[end:min(len(topic_text), end + 22)]
    around_context = f'{left_context} {right_context}'

    if any(marker in around_context for marker in BOOK_TITLE_CONTEXT_MARKERS):
        score += 5
    if any(marker in right_context for marker in BOOK_TITLE_EVENT_MARKERS):
        score += 4
    if any(marker in left_context for marker in BOOK_TITLE_EVENT_MARKERS):
        score += 2

    has_location_hint = any(loc in text for loc in BOOK_TITLE_LOCATION_HINTS)
    if has_location_hint:
        score -= 2
        if source in {'event_context', 'book_context'}:
            score -= 4
    if any(text.endswith(suffix) for suffix in BOOK_TITLE_LOCATION_SUFFIXES):
        score -= 12
    if source in {'event_context', 'book_context'} and not any(marker in text for marker in BOOK_TITLE_CONTEXT_MARKERS):
        score -= 3

    if ',' in text or '·' in text:
        score += 1

    return score


def _extract_book_title(topic: str, params: Optional[Dict[str, Any]] = None) -> str:
    if not topic:
        return ''

    full_name = ''
    if isinstance(params, dict):
        full_name = str(params.get('fullName') or '').strip()

        context_analysis = params.get('contextAnalysis') if isinstance(params.get('contextAnalysis'), dict) else {}
        must_preserve = context_analysis.get('mustPreserve') if isinstance(context_analysis.get('mustPreserve'), dict) else {}
        explicit = _normalize_book_title_candidate(str(must_preserve.get('bookTitle') or ''))
        if explicit:
            return explicit

    candidates = _collect_book_title_candidates(topic)
    if full_name:
        author_event_pattern = re.compile(
            rf'{re.escape(full_name)}\s+([^\n]{{2,80}}?)\s*(?:출판기념회|북토크|토크콘서트|출판행사)'
        )
        for match in author_event_pattern.finditer(str(topic)):
            raw = str(match.group(1) or '').strip()
            if not raw:
                continue
            candidates.append(
                {
                    'raw': raw,
                    'start': int(match.start(1)),
                    'end': int(match.end(1)),
                    'source': 'author_event_context',
                }
            )
    best_title = ''
    best_score = -999
    seen: set[str] = set()

    for candidate in candidates:
        normalized = _normalize_book_title_candidate(str(candidate.get('raw') or ''))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)

        nested_candidates = _collect_book_title_candidates(normalized)
        nested_title = ''
        nested_score = -999
        for nested in nested_candidates:
            nested_score_candidate = _score_book_title_candidate(nested, normalized, full_name)
            nested_normalized = _normalize_book_title_candidate(str(nested.get('raw') or ''))
            if nested_score_candidate > nested_score and nested_normalized:
                nested_score = nested_score_candidate
                nested_title = nested_normalized

        score = _score_book_title_candidate(candidate, topic, full_name)
        title = normalized
        if nested_title and nested_score > score:
            score = nested_score
            title = nested_title

        if score > best_score:
            best_score = score
            best_title = title

    if best_score >= 5:
        if full_name and best_title.startswith(f'{full_name} '):
            tail = _normalize_book_title_candidate(best_title[len(full_name):])
            if tail:
                best_title = tail
        return best_title

    return ''


def normalize_title_surface(title: str) -> str:
    cleaned = str(title or '').translate(
        str.maketrans(
            {
                '“': '"',
                '”': '"',
                '„': '"',
                '‟': '"',
            }
        )
    )
    cleaned = cleaned.strip().strip('"\'')
    if not cleaned:
        return ''

    candidate = cleaned
    # 소수점 앞뒤 공백 정리: "0. 7%" -> "0.7%", "3 .5" -> "3.5"
    candidate = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', candidate)
    cleaned = candidate

    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'\s+([,.:;!?])', r'\1', cleaned)
    cleaned = re.sub(r'([,:;!?])(?=[^\s\]\)\}])', r'\1 ', cleaned)
    # 마침표는 소수점/날짜 숫자 구간을 제외하고만 뒤 공백을 부여한다.
    cleaned = re.sub(r'(\d)\.(?=[^\s\]\)\}\d])', r'\1. ', cleaned)
    cleaned = re.sub(r'(?<!\d)\.(?=[^\s\]\)\}\d])', '. ', cleaned)
    cleaned = re.sub(r'\(\s+', '(', cleaned)
    cleaned = re.sub(r'\s+\)', ')', cleaned)
    cleaned = re.sub(r'\[\s+', '[', cleaned)
    cleaned = re.sub(r'\s+\]', ']', cleaned)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    cleaned = re.sub(r',(?:\s*,)+', ', ', cleaned)
    cleaned = re.sub(r'[!?]{2,}', '?', cleaned)
    return cleaned.strip(' ,')


def _fit_title_length(title: str) -> str:
    if not title:
        return ''
    normalized = re.sub(r'\s+', ' ', title).strip()
    if len(normalized) <= TITLE_LENGTH_HARD_MAX:
        return normalized
    compact = normalized.replace(' 핵심 메시지', '').replace(' 핵심', '').replace(' 현장', '')
    compact = re.sub(r'\s+', ' ', compact).strip()
    return compact


def _detect_truncated_title_reason(title: str) -> str:
    normalized = normalize_title_surface(title)
    if not normalized:
        return ''

    stripped = normalized.strip()
    if not stripped:
        return ''
    if '...' in stripped or '…' in stripped:
        return '말줄임표 포함'
    if re.search(r'(?:^|[\s,:;!?])\d{1,3}$', stripped):
        return '숫자로 비정상 종료'

    wrapper_pairs = (
        ('(', ')'),
        ('[', ']'),
        ('<', '>'),
        ('《', '》'),
        ('"', '"'),
        ("'", "'"),
    )
    for opener, closer in wrapper_pairs:
        if opener == closer:
            if stripped.count(opener) % 2 == 1:
                return f'{opener} 인용부호 불균형'
            continue
        if stripped.count(opener) > stripped.count(closer):
            return f'{opener} 닫힘 누락'

    return ''


def _normalize_generated_title_without_fit(generated_title: str, params: Dict[str, Any]) -> str:
    if not generated_title:
        return ''

    normalized = normalize_title_surface(generated_title)
    # 도서명 꺾쇠 표기는 유지하되 내부 공백만 정리한다.
    normalized = re.sub(r'<\s*([^>]+?)\s*>', r'<\1>', normalized)
    normalized = re.sub(r'《\s*([^》]+?)\s*》', r'《\1》', normalized)
    normalized = re.sub(r'\s+,', ',', normalized)
    normalized = re.sub(r',\s*,', ',', normalized)
    normalized = normalize_title_surface(normalized)

    topic = str(params.get('topic') or '')
    title_purpose = resolve_title_purpose(topic, params)
    book_title = _extract_book_title(topic, params) if title_purpose == 'event_announcement' else ''
    if book_title:
        # 모델이 빈 꺾쇠(<>, 《》)를 출력한 경우 책 제목을 복원한다.
        if re.search(r'<\s*>', normalized) and book_title not in normalized:
            normalized = re.sub(r'<\s*>', f'<{book_title}>', normalized)
        if re.search(r'《\s*》', normalized) and book_title not in normalized:
            normalized = re.sub(r'《\s*》', f'《{book_title}》', normalized)
        normalized = normalize_title_surface(normalized)

    return normalized


def _normalize_generated_title(generated_title: str, params: Dict[str, Any]) -> str:
    normalized = _normalize_generated_title_without_fit(generated_title, params)
    if not normalized:
        return ''

    topic = str(params.get('topic') or '')
    title_purpose = resolve_title_purpose(topic, params)

    if len(normalized) <= TITLE_LENGTH_HARD_MAX:
        return normalized

    if title_purpose == 'event_announcement':
        normalized = re.sub(r'\s{2,}', ' ', normalized).strip(' ,')
        if len(normalized) <= TITLE_LENGTH_HARD_MAX:
            return normalized

    return _fit_title_length(normalized)


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

    if TITLE_LENGTH_OPTIMAL_MAX < title_length <= TITLE_LENGTH_HARD_MAX:
        return {
            'length': title_length,
            'penalty': 12,
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


def _build_initial_length_discipline_feedback(meta: Dict[str, Any]) -> str:
    title_length = int(meta.get('length', 0) or 0)
    status = str(meta.get('status') or '').strip().lower()
    if status == 'short_borderline':
        return (
            f'초기 생성 제목이 {title_length}자로 짧습니다. '
            f'처음부터 {TITLE_LENGTH_OPTIMAL_MIN}-{TITLE_LENGTH_OPTIMAL_MAX}자 안으로 다시 쓰세요.'
        )
    if status == 'long_borderline':
        return (
            f'초기 생성 제목이 {title_length}자로 깁니다. '
            f'뒤를 자르지 말고 정보를 줄여 {TITLE_LENGTH_OPTIMAL_MAX}자 이하로 다시 쓰세요.'
        )
    if status == 'hard_violation':
        return (
            f'초기 생성 제목이 {title_length}자로 기준을 넘었습니다. '
            f'사후 축약에 기대지 말고 {TITLE_LENGTH_OPTIMAL_MIN}-{TITLE_LENGTH_OPTIMAL_MAX}자로 새로 작성하세요.'
        )
    if status == 'empty':
        return '후보 제목이 비어 있습니다. 1개의 완결된 제목을 다시 작성하세요.'
    return ''


def _normalize_title_for_similarity(title: str) -> str:
    normalized = str(title or '').lower().strip()
    normalized = re.sub(r'[\s\W_]+', '', normalized, flags=re.UNICODE)
    return normalized


def _title_similarity(a: str, b: str) -> float:
    norm_a = _normalize_title_for_similarity(a)
    norm_b = _normalize_title_for_similarity(b)
    if not norm_a or not norm_b:
        return 0.0
    return SequenceMatcher(None, norm_a, norm_b).ratio()


def _build_title_candidate_prompt(
    base_prompt: str,
    attempt: int,
    candidate_index: int,
    candidate_count: int,
    disallow_titles: List[str],
    title_purpose: str,
) -> str:
    event_variants = [
        '일정/장소 전달을 우선하되, 마지막 명사구를 바꿔 새 어감으로 작성',
        '행동 유도(참여/방문/동행) 중심으로 후킹 단어를 새롭게 선택',
        '인물/도서/날짜 중 2개를 결합해 현장감 있는 문장으로 구성',
        '같은 정보라도 어순을 바꿔 다른 리듬으로 작성',
        '행사 안내 어조를 유지하되 추상 표현 없이 구체 정보 중심으로 작성',
    ]
    default_variants = [
        '질문형 긴장감을 유지하되 핵심 동사를 기존과 다르게 선택',
        '숫자/팩트 중심으로 간결하게 구성하고 문장 종결을 새롭게 작성',
        '원인-결과 흐름을 넣어 클릭 이유가 생기게 작성',
        '핵심 키워드 이후의 어구를 완전히 새롭게 재구성',
        '정보요소 3개 이내를 지키면서 대비/변화 포인트를 부각',
    ]
    variants = event_variants if title_purpose == 'event_announcement' else default_variants
    variant = variants[(candidate_index - 1) % len(variants)]

    blocked = [f'"{t}"' for t in disallow_titles[-4:] if t]
    blocked_line = (
        f"다음 제목/문구를 반복하지 마세요: {', '.join(blocked)}"
        if blocked else
        "직전 시도와 동일한 문구/어순 반복 금지"
    )

    return f"""{base_prompt}

<diversity_hint attempt="{attempt}" candidate="{candidate_index}/{candidate_count}">
  <focus>{variant}</focus>
  <blocked>{blocked_line}</blocked>
  <rule>1순위 키워드 시작 규칙은 반드시 지키되, 그 뒤 문장은 새롭게 작성</rule>
  <rule>출력 직전에 제목 글자 수를 직접 세고 {TITLE_LENGTH_OPTIMAL_MIN}-{TITLE_LENGTH_OPTIMAL_MAX}자에 맞출 것</rule>
  <rule>{TITLE_LENGTH_OPTIMAL_MAX}자를 넘으면 자르지 말고 더 짧은 새 문장으로 다시 쓸 것</rule>
  <rule>{TITLE_LENGTH_HARD_MIN}-{TITLE_LENGTH_HARD_MAX}자 예외 통과에 기대지 말고, 처음부터 권장 범위에 맞춘 최종 1개만 출력</rule>
</diversity_hint>

"""


def _compute_similarity_penalty(
    title: str,
    previous_titles: List[str],
    threshold: float,
    max_penalty: int,
) -> Dict[str, Any]:
    if not title or not previous_titles or max_penalty <= 0:
        return {'penalty': 0, 'maxSimilarity': 0.0, 'against': ''}

    best_similarity = 0.0
    against = ''
    for prev in previous_titles:
        if not prev:
            continue
        similarity = _title_similarity(title, prev)
        if similarity > best_similarity:
            best_similarity = similarity
            against = prev

    if best_similarity < threshold:
        return {'penalty': 0, 'maxSimilarity': round(best_similarity, 3), 'against': against}

    span = max(0.01, 1.0 - threshold)
    ratio = (best_similarity - threshold) / span
    penalty = max(1, min(max_penalty, int(round(ratio * max_penalty))))
    return {'penalty': penalty, 'maxSimilarity': round(best_similarity, 3), 'against': against}


def resolve_title_purpose(topic: str, params: Dict[str, Any]) -> str:
    event_markers = EVENT_NAME_MARKERS + (
        '행사',
        '개최',
        '열리는',
        '열립니다',
        '초대',
        '참석',
    )
    if any(marker in (topic or '') for marker in event_markers):
        return 'event_announcement'

    context_analysis = params.get('contextAnalysis') if isinstance(params.get('contextAnalysis'), dict) else {}
    intent = str(context_analysis.get('intent') or '').strip().lower()
    offline_intents = {
        'event_announcement',
        'offline_engagement',
        'event_participation',
        'event_attendance',
        'brief_notice',
        'schedule_notice',
    }
    if intent in offline_intents:
        return 'event_announcement'
    if intent:
        return intent
    return ''


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
    if any(phrase in cleaned for phrase in banned_phrases) or '?' in cleaned:
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


def _build_event_title_prompt(params: Dict[str, Any]) -> str:
    topic = str(params.get('topic') or '')
    full_name = str(params.get('fullName') or '').strip()
    content_preview = str(params.get('contentPreview') or '')
    prompt_lite = bool(params.get('titlePromptLite'))
    role_keyword_policy = params.get('roleKeywordPolicy') if isinstance(params.get('roleKeywordPolicy'), dict) else {}
    user_keywords = _filter_required_title_keywords(
        params.get('userKeywords') if isinstance(params.get('userKeywords'), list) else [],
        role_keyword_policy,
    )
    context_analysis = params.get('contextAnalysis') if isinstance(params.get('contextAnalysis'), dict) else {}
    must_preserve = context_analysis.get('mustPreserve') if isinstance(context_analysis.get('mustPreserve'), dict) else {}

    primary_keyword = str(user_keywords[0]).strip() if user_keywords else ''
    event_date = str(must_preserve.get('eventDate') or '').strip()
    date_hint = _extract_date_hint(event_date) or _extract_date_hint(topic)
    event_location = str(must_preserve.get('eventLocation') or '').strip() or primary_keyword
    event_label = _detect_event_label(topic)
    book_title = _extract_book_title(topic, params)
    is_book_event = any(marker in topic for marker in ('출판기념회', '북토크', '토크콘서트'))
    hook_words = "현장, 직접, 일정, 안내, 초대, 만남, 참석"
    number_validation = extract_numbers_from_content(content_preview)
    content_preview_limit = 260 if prompt_lite else 500

    return f"""<event_title_prompt priority="critical">
<role>당신은 행사 안내형 블로그 제목 에디터입니다. 목적 적합성과 규칙 준수를 최우선으로 합니다.</role>

<input>
  <topic>{topic}</topic>
  <author>{full_name or '(없음)'}</author>
  <primary_keyword>{primary_keyword or '(없음)'}</primary_keyword>
  <date_hint>{date_hint or '(없음)'}</date_hint>
  <location_hint>{event_location or '(없음)'}</location_hint>
  <book_title>{book_title or '(없음)'}</book_title>
  <event_label>{event_label}</event_label>
  <content_preview>{content_preview[:content_preview_limit]}</content_preview>
</input>

<hard_rules>
  <rule>제목은 기본적으로 {TITLE_LENGTH_OPTIMAL_MIN}-{TITLE_LENGTH_OPTIMAL_MAX}자로 작성.</rule>
  <rule>검증 허용 범위는 {TITLE_LENGTH_HARD_MIN}-{TITLE_LENGTH_HARD_MAX}자(예외 구간 포함).</rule>
  <rule>출력 직전에 제목 글자 수를 직접 세고 {TITLE_LENGTH_OPTIMAL_MIN}-{TITLE_LENGTH_OPTIMAL_MAX}자가 아니면 내부에서 다시 고친 뒤 1개만 출력.</rule>
  <rule>{TITLE_LENGTH_OPTIMAL_MAX}자를 넘으면 자르지 말고, 정보 요소를 줄여 더 짧은 새 제목으로 다시 작성.</rule>
  <rule>물음표(?)와 추측/논쟁형 어투 금지.</rule>
  <rule>안내 목적이 즉시 드러나도록 "{event_label}" 또는 "안내/초대/개최/행사" 포함.</rule>
  <rule>후킹 단어 1개 이상 포함: {hook_words}.</rule>
  <rule>1순위 검색어가 있으면 반드시 포함: "{primary_keyword or '(없음)'}".</rule>
  <rule>날짜 힌트가 있으면 반드시 포함: "{date_hint or '(없음)'}".</rule>
  <rule>인물명이 있으면 반드시 포함: "{full_name or '(없음)'}".</rule>
  <rule>도서 행사({is_book_event})이고 도서명이 있으면 도서명 단서를 포함: "{book_title or '(없음)'}".</rule>
  <rule>장소 힌트가 있으면 가능한 한 포함: "{event_location or '(없음)'}".</rule>
</hard_rules>

{number_validation.get('instruction', '')}

</event_title_prompt>"""


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


def build_title_prompt(params: Dict[str, Any]) -> str:
    # No try/except blocking logic here. Let it propagate.
    content_preview = params.get('contentPreview', '')
    background_text = params.get('backgroundText', '')
    topic = params.get('topic', '')
    full_name = params.get('fullName', '')
    keywords = params.get('keywords', [])
    role_keyword_policy = params.get('roleKeywordPolicy') if isinstance(params.get('roleKeywordPolicy'), dict) else {}
    user_keywords = _filter_required_title_keywords(
        params.get('userKeywords') if isinstance(params.get('userKeywords'), list) else [],
        role_keyword_policy,
    )
    category = params.get('category', '')
    status = params.get('status', '')
    title_scope = params.get('titleScope', {})
    forced_type = params.get('_forcedType')
    stance_text = params.get('stanceText', '')  # 🔑 [NEW] 입장문
    prompt_lite = bool(params.get('titlePromptLite'))
    title_purpose = resolve_title_purpose(topic, params)
    if title_purpose == 'event_announcement':
        return _build_event_title_prompt(params)
    event_title_policy = build_event_title_policy_instruction(params) if title_purpose == 'event_announcement' else ''
    
    avoid_local_in_title = bool(title_scope and title_scope.get('avoidLocalInTitle'))
    detected_type_id = None
    
    if forced_type and forced_type in TITLE_TYPES:
        detected_type_id = forced_type
    else:
        detected_type_id = detect_content_type(content_preview, category)
        if avoid_local_in_title and detected_type_id == 'LOCAL_FOCUSED':
            detected_type_id = 'ISSUE_ANALYSIS' # avoidLocalInTitle 정책 적용
            
    primary_type = TITLE_TYPES.get(detected_type_id) or TITLE_TYPES['DATA_BASED']
    # If default was chosen but really we want Viral Hook for general cases:
    if detected_type_id == 'VIRAL_HOOK':
         primary_type = TITLE_TYPES['VIRAL_HOOK']
    
    number_validation = extract_numbers_from_content(content_preview)
    election_compliance = get_election_compliance_instruction(status)
    keyword_strategy = get_keyword_strategy_instruction(
        user_keywords,
        keywords,
        role_keyword_policy,
    )
    user_few_shot = build_user_provided_few_shot_instruction(primary_type['id'], params)
    narrative_principle_xml = '' if prompt_lite else _render_narrative_principle_xml(primary_type.get('principle', ''))

    good_examples_source = list(primary_type.get('good', []))
    bad_examples_source = list(primary_type.get('bad', []))
    if prompt_lite:
        good_examples_source = good_examples_source[:2]
        bad_examples_source = bad_examples_source[:2]

    stance_limit = 240 if prompt_lite else 500
    content_limit = 420 if prompt_lite else 800
    background_limit = 160 if prompt_lite else 300
    
    region_scope_instruction = ""
    if avoid_local_in_title:
        region_scope_instruction = f"""
<title_region_scope>
  <target_position>{title_scope.get('position', 'metro-level') if title_scope else 'metro-level'}</target_position>
  <rule>Do NOT use district/town names (gu/gun/dong/eup/myeon) in the title.</rule>
  <metro_region>{title_scope.get('regionMetro', 'the city/province') if title_scope else 'the city/province'}</metro_region>
</title_region_scope>
"""

    good_lines = []
    for i, ex in enumerate(good_examples_source):
        good_lines.append(
            f'  <example index="{i + 1}" chars="{int(ex.get("chars", 0) or 0)}">'
            f'<title>{ex["title"]}</title>'
            f'<analysis>{ex.get("analysis", "")}</analysis>'
            f'</example>'
        )
    good_examples = "\n".join(good_lines)

    bad_lines = []
    for i, ex in enumerate(bad_examples_source):
        bad_lines.append(
            f'  <example index="{i + 1}">'
            f'<bad>{ex["title"]}</bad>'
            f'<problem>{ex.get("problem", "")}</problem>'
            f'<fix>{ex.get("fix", "")}</fix>'
            f'</example>'
        )
    bad_examples = "\n\n".join(bad_lines)

    primary_kw_str = user_keywords[0] if user_keywords else '(없음)'
    objective_block = """
<objective>
  <goal>아래 내용을 분석하여, 독자가 클릭하고 싶어지는 서사적 긴장감의 블로그 제목을 작성하십시오.</goal>
  <core_principle name="information_gap">좋은 제목은 답보다 질문을 남깁니다.</core_principle>
  <examples>
    <bad reason="긴장감 부족">이재성이 경제 0.7%를 바꾼다</bad>
    <bad reason="문장 불완전">이재성 부산 AI 3대 강국?</bad>
    <good reason="팩트+미해결질문">부산 경제 0.7%, 왜 이 남자가 뛰어들었나</good>
  </examples>
  <banned_styles>
    <item>지루한 공무원 스타일("~개최", "~참석", "~발표")</item>
    <item>선언형 결론("~바꾼다", "~이끈다", "~완성한다")</item>
    <item>키워드 나열만 하고 문장을 완성하지 않는 표현</item>
    <item>과도한 자극("충격", "경악", "결국 터졌다")</item>
  </banned_styles>
</objective>
""".strip()
    style_ban_rule = '"발표", "개최", "참석" 등 보도자료 스타일 금지'
    keyword_position_rule = (
        f'핵심 키워드 "{primary_kw_str}" 반드시 포함. 키워드 직후에 구분자(쉼표, 물음표, 조사+쉼표)를 넣어라. '
        '"부산 지방선거, 왜~", "부산 지방선거에 뛰어든~", "부산 지방선거 이재성" '
        '(네이버가 하나의 키워드로 인식)'
    )

    if title_purpose == 'event_announcement':
        event_label = _detect_event_label(topic)
        objective_block = f"""
<objective>
  <goal>아래 내용을 분석하여, 행사 안내 목적이 분명하면서도 클릭하고 싶어지는 제목을 작성하십시오.</goal>
  <core_principle name="purpose_fit">안내/초대 목적이 먼저 드러나고 후킹은 그 다음에 배치합니다.</core_principle>
  <allowed>
    <item>안내형 표현: "안내", "초대", "개최", "열립니다", "행사명"</item>
    <item>날짜/장소/행사명을 자연스럽게 포함한 제목</item>
    <item>안전한 후킹 단어: "현장", "직접", "일정", "안내", "초대", "만남", "참석"</item>
  </allowed>
  <recommended_formula>[메인 SEO 키워드] + [날짜/장소] + [후킹 단어] + [[행사명]/안내]</recommended_formula>
  <example>[장소명], [날짜] [{event_label}] 안내</example>
  <banned_styles>
    <item>추측형/논쟁형/공격형 표현: "진짜 속내", "왜 왔냐", "답할까"</item>
    <item>물음표(?) 기반 도발형 제목</item>
    <item>과도한 자극("충격", "경악", "결국 터졌다")</item>
  </banned_styles>
</objective>
""".strip()
        style_ban_rule = '행사 안내 목적을 흐리는 논쟁형/도발형 카피 금지 (추측·공격·선동 어투 금지)'
        keyword_position_rule = (
            f'핵심 키워드 "{primary_kw_str}" 반드시 포함. 키워드 직후에는 쉼표(,) 또는 조사(에/의/에서 등)를 사용해 분리하세요. '
            '"[장소명], [날짜] [행사명] 안내", "[장소명]에서 열리는 [행사명] 안내", "[장소명] [인물명] [행사명]"'
        )
    
    return f"""<title_generation_prompt>

<role>네이버 블로그 제목 전문가 (클릭률 1위 카피라이터)</role>

{objective_block}

<content_type detected="{primary_type['id']}">
  <name>{primary_type['name']}</name>
  <when>{primary_type['when']}</when>
  <pattern>{primary_type['pattern']}</pattern>
  <naver_tip>{primary_type['naverTip']}</naver_tip>
</content_type>

{narrative_principle_xml}

<input>
  <topic>{topic}</topic>
  <author>{full_name}</author>
  <stance_summary priority="Highest">{stance_text[:stance_limit] if stance_text else '(없음) - 입장문이 없으면 본문 내용 바탕으로 작성'}</stance_summary>
  <content_preview>{(content_preview or '')[:content_limit]}</content_preview>
  <background>{background_text[:background_limit] if background_text else '(없음)'}</background>
</input>

<examples type="good">
{good_examples}
</examples>

<examples type="bad">
{bad_examples}
</examples>

{user_few_shot}

<rules priority="critical">
  <rule id="length_target">제목은 기본적으로 {TITLE_LENGTH_OPTIMAL_MIN}-{TITLE_LENGTH_OPTIMAL_MAX}자로 작성 (최우선 목표).</rule>
  <rule id="length_max">{TITLE_LENGTH_HARD_MAX}자 이내 (네이버 검색결과 잘림 방지) - 절대 초과 금지.</rule>
  <rule id="length_floor">{TITLE_LENGTH_HARD_MIN}자 미만 금지. {TITLE_LENGTH_HARD_MIN}-14자와 31-{TITLE_LENGTH_HARD_MAX}자는 예외 구간이므로 가급적 피할 것.</rule>
  <rule id="length_self_check">출력 직전에 제목 글자 수를 직접 세고, {TITLE_LENGTH_OPTIMAL_MIN}-{TITLE_LENGTH_OPTIMAL_MAX}자가 아니면 내부에서 다시 써서 맞춘 뒤 최종 1개만 출력.</rule>
  <rule id="no_length_repair_dependency">길이가 길다고 느껴지면 뒤를 자르지 말고, 정보 요소를 줄여 더 짧은 새 문장으로 다시 작성. 31-35자 예외 통과에 기대지 말 것.</rule>
  <rule id="no_slot_placeholder">슬롯 플레이스홀더([행사명], [지역명], [정책명] 등)를 제목에 그대로 출력하지 마세요.</rule>
  <rule id="no_ellipsis">말줄임표("...") 절대 금지</rule>
  <rule id="keyword_position">{keyword_position_rule}</rule>
  <rule id="no_greeting">인사말("안녕하세요"), 서술형 어미("~입니다") 절대 금지</rule>
  <rule id="style_ban">{style_ban_rule}</rule>
  <rule id="narrative_tension">읽은 뒤 "그래서?" "왜?"가 떠오르는 제목이 좋다. 기법을 억지로 넣지 말고 자연스러운 호기심을 만들어라. 선언형 종결("~바꾼다") 금지. 정보 요소 3개 이하.</rule>
  <rule id="info_density">제목에 담는 정보 요소는 최대 3개. SEO 키워드는 1개로 카운트. 요소: SEO키워드, 인명, 수치, 정책명, 수식어. "부산 지방선거, 왜 이 남자가 뛰어들었나" = 2개 OK. "부산 지방선거 이재명 2호 이재성 원칙 선택" = 5개 NG.</rule>
  <rule id="no_topic_copy">주제(topic) 텍스트를 그대로 또는 거의 그대로 제목으로 사용 금지. 주제의 핵심 방향만 따르되, 표현·어순·구성은 반드시 새롭게 작성할 것.</rule>
</rules>

{event_title_policy}
{election_compliance}
{keyword_strategy}
{number_validation['instruction']}
{region_scope_instruction}

<topic_priority priority="highest">
  <instruction>제목의 방향은 반드시 주제(topic)를 따라야 합니다. 본문 내용이 아무리 많아도 topic이 절대 우선입니다.</instruction>
  <rules>
    <rule>주제가 "후원"이면 제목도 후원/응원/함께에 관한 것이어야 함 — 경제/AI/정책으로 빠지면 안 됨</rule>
    <rule>주제가 "원칙"이면 제목도 원칙/품격에 관한 것이어야 함</rule>
    <rule>본문(content_preview)은 배경 정보일 뿐, 제목 방향을 결정하지 않음</rule>
    <rule>주제 키워드를 전부 넣을 필요는 없지만, 주제의 핵심 행동/요청은 반드시 반영</rule>
  </rules>
  <example>
    <topic>원칙과 품격, 부산시장 예비후보 이재성 후원</topic>
    <good>부산 지방선거, 이재성에게 힘을 보태는 방법</good>
    <bad reason="주제 이탈 — 후원이 주제인데 경제로 빠짐">부산 지방선거, 경제 0.7% 늪에서 이재성이 꺼낸 비책은</bad>
  </example>
</topic_priority>

<output_rules>
  <rule>{TITLE_LENGTH_OPTIMAL_MIN}-{TITLE_LENGTH_OPTIMAL_MAX}자로 작성 (기본 목표)</rule>
  <rule>검증 허용 범위는 {TITLE_LENGTH_HARD_MIN}-{TITLE_LENGTH_HARD_MAX}자 (예외 구간)</rule>
  <rule>슬롯 플레이스홀더([행사명] 등) 출력 금지</rule>
  <rule>말줄임표 금지</rule>
  <rule>핵심 키워드 포함</rule>
  <rule>본문에 실제 등장하는 숫자만 사용</rule>
  <rule>지루한 표현 금지</rule>
</output_rules>

</title_generation_prompt>
"""

def extract_topic_keywords(topic: str) -> List[str]:
    keywords = []
    try:
        # Names (simple heuristic for Korean names)
        name_matches = re.findall(r'[가-힣]{2,4}(?=\s*(?:의원|시장|구청장|대통령|총리|장관|대표)?(?:$|\s))', topic)
        if name_matches:
            keywords.extend(name_matches[:3])
            
        action_keywords = ['칭찬', '질타', '비판', '논평', '발언', '소신', '침묵', '사형', '구형', '협력', '대립']
        for action in action_keywords:
            if action in topic:
                keywords.append(action)
                
        number_matches = re.findall(r'\d+(?:억|만원|%|명|건)?', topic)
        if number_matches:
            keywords.extend(number_matches[:2])
    except:
        pass
        
    return list(set(keywords))

def validate_theme_and_content(topic: str, content: str, title: str = '') -> Dict[str, Any]:
    try:
        if not topic or not content:
            return {
                'isValid': False,
                'mismatchReasons': ['주제 또는 본문이 비어있습니다'],
                'topicKeywords': [],
                'contentKeywords': [],
                'overlapScore': 0
            }
            
        topic_keywords = extract_topic_keywords(topic)
        content_lower = content.lower()
        matched_keywords = []
        missing_keywords = []
        
        for kw in topic_keywords:
            if kw.lower() in content_lower:
                matched_keywords.append(kw)
            else:
                missing_keywords.append(kw)
                
        overlap_score = round(len(matched_keywords) / len(topic_keywords) * 100) if topic_keywords else 0
        mismatch_reasons = []
        
        if overlap_score < 50:
             mismatch_reasons.append(f"주제 핵심어 중 {len(missing_keywords)}개가 본문에 없음: {', '.join(missing_keywords)}")
             
        if title:
            title_lower = title.lower()
            title_missing = [kw for kw in topic_keywords if kw.lower() not in title_lower]
            if len(title_missing) > len(topic_keywords) * 0.5:
                 mismatch_reasons.append(f"제목에 주제 핵심어 부족: {', '.join(title_missing[:3])}")
                 
        return {
            'isValid': overlap_score >= 50 and not mismatch_reasons,
            'mismatchReasons': mismatch_reasons,
            'topicKeywords': topic_keywords,
            'matchedKeywords': matched_keywords,
            'missingKeywords': missing_keywords,
            'overlapScore': overlap_score
        }
    except:
        return {'isValid': True, 'overlapScore': 100, 'mismatchReasons': []}


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


def _assess_title_frame_alignment(topic: str, title: str) -> Dict[str, Any]:
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
    if any(token in title_text for token in ("양자대결", "가상대결", "맞대결", "대결", "접전")):
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


def validate_theme_and_content(topic: str, content: str, title: str = '') -> Dict[str, Any]:
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
        content_text = str(content or '')
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

        if content_overlap_score < 50:
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
            frame_alignment_meta = _assess_title_frame_alignment(topic, title_text)
            effective_title_score = max(
                effective_title_score,
                int(frame_alignment_meta.get("score") or 0),
            )
            if len(title_missing) > len(topic_keywords) * 0.5 and int(frame_alignment_meta.get("score") or 0) < 70:
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
        }
    except:
        return {
            'isValid': True,
            'overlapScore': 100,
            'contentOverlapScore': 100,
            'titleOverlapScore': 100,
            'effectiveTitleScore': 100,
            'frameAlignmentScore': 100,
            'frameAlignmentStyle': 'fallback',
            'frameMatchedPeople': [],
            'mismatchReasons': [],
        }


def _validate_user_keyword_title_requirements(title: str, user_keywords: List[str]) -> Dict[str, Any]:
    """사용자 지정 검색어의 제목 반영 여부를 강제 검증한다."""
    cleaned_title = str(title or '').strip()
    normalized_user_keywords = [str(item or '').strip() for item in (user_keywords or []) if str(item or '').strip()]
    if not normalized_user_keywords:
        return {'passed': True}

    primary_kw = normalized_user_keywords[0]
    if primary_kw not in cleaned_title:
        return {
            'passed': False,
            'reason': f'1순위 검색어 "{primary_kw}"가 제목에 없습니다.',
        }

    if len(normalized_user_keywords) < 2:
        return {'passed': True}

    secondary_kw = normalized_user_keywords[1]
    if not secondary_kw or secondary_kw == primary_kw:
        return {'passed': True}

    similar = are_keywords_similar(primary_kw, secondary_kw)
    if similar:
        kw2_words = [w for w in secondary_kw.split() if len(w) >= 2]
        kw1_words = set(primary_kw.split())
        unique_words = [w for w in kw2_words if w not in kw1_words]
        if unique_words and not any(word in cleaned_title for word in unique_words):
            return {
                'passed': False,
                'severity': 'soft',
                'missingType': 'secondary_unique',
                'primaryKw': primary_kw,
                'secondaryKw': secondary_kw,
                'uniqueWords': unique_words,
                'reason': (
                    f'2순위 검색어 "{secondary_kw}"의 고유 어절({", ".join(unique_words)})이 제목에 없습니다.'
                ),
            }
        return {'passed': True}

    if secondary_kw not in cleaned_title:
        return {
            'passed': False,
            'missingType': 'secondary_full',
            'primaryKw': primary_kw,
            'secondaryKw': secondary_kw,
            'uniqueWords': [],
            'reason': f'2순위 검색어 "{secondary_kw}"가 제목에 없습니다.',
        }

    return {'passed': True}


_ROLE_KEYWORD_TOKENS = (
    '부산시장',
    '시장',
    '국회의원',
    '의원',
    '후보',
)


def _is_role_keyword_token(token: str) -> bool:
    normalized = str(token or '').strip()
    if not normalized:
        return False
    return any(role_token == normalized for role_token in _ROLE_KEYWORD_TOKENS)


def _repair_title_for_missing_keywords(
    title: str,
    keyword_gate: Dict[str, Any],
) -> Optional[str]:
    """2순위 키워드 고유 어절을 1순위 키워드를 보존하면서 제목에 삽입한다.

    전략: primary_kw 직후에 괄호 또는 중간점으로 missing word를 추가.
    예: "부산 영광도서, ..." → "부산 영광도서(서면), ..."
    """
    missing_type = keyword_gate.get('missingType', '')
    primary_kw = str(keyword_gate.get('primaryKw') or '')
    missing_words = keyword_gate.get('uniqueWords') or []

    if not primary_kw or primary_kw not in title:
        return None

    if missing_type == 'secondary_unique' and missing_words:
        secondary_kw = str(keyword_gate.get('secondaryKw') or '').strip()
        normalized_missing_roles = [word for word in missing_words if _is_role_keyword_token(word)]
        has_primary_role = bool(
            re.search(
                rf"{re.escape(primary_kw)}\s*(?:현\s*)?(?:부산시장|국회의원|의원|시장)(?:\s*후보)?",
                title,
            )
        )
        # 호칭 충돌(예: "주진우 국회의원" + 2순위 "주진우 부산시장")은
        # 괄호 삽입 대신 검색 의도형 질문 제목으로 치환한다.
        if secondary_kw and normalized_missing_roles and has_primary_role:
            conflict_candidates = (
                build_role_keyword_intent_text(secondary_kw, context='title', variant_index=0),
                build_role_keyword_intent_text(secondary_kw, context='title', variant_index=1),
                build_role_keyword_intent_text(secondary_kw, context='title', variant_index=2),
            )
            for candidate in conflict_candidates:
                if TITLE_LENGTH_HARD_MIN <= len(candidate) <= TITLE_LENGTH_HARD_MAX:
                    return candidate

        # 고유 어절만 삽입: "부산 영광도서" → "부산 영광도서(서면)"
        suffix = '·'.join(missing_words)
        repaired = title.replace(primary_kw, f"{primary_kw}({suffix})", 1)
    elif missing_type == 'secondary_full':
        secondary_kw = str(keyword_gate.get('secondaryKw') or '')
        if not secondary_kw:
            return None
        # 전체 2순위 키워드 삽입: primary_kw 뒤에 추가
        repaired = title.replace(primary_kw, f"{primary_kw}·{secondary_kw}", 1)
    else:
        return None

    if len(repaired) > TITLE_LENGTH_HARD_MAX:
        return None
    if len(repaired) < TITLE_LENGTH_HARD_MIN:
        return None

    return repaired


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
    
    if not title:
        return {'score': 0, 'breakdown': {}, 'passed': False, 'suggestions': ['제목이 없습니다']}
        
    # 0. Critical Failure Checks
    has_html_tag = bool(re.search(r'<\s*/?\s*[a-zA-Z][^>]*>', title))
    has_slot_placeholder = any(f'[{name}]' in title for name in SLOT_PLACEHOLDER_NAMES)
    looks_like_content = (
        '여러분' in title or
        has_html_tag or
        has_slot_placeholder or
        title.endswith('입니다') or
        title.endswith('습니다') or
        title.endswith('습니까') or
        title.endswith('니다') or
        len(title) > 50
    )
    
    if looks_like_content:
        reason = (
            '호칭("여러분") 포함' if '여러분' in title else
            ('HTML 태그 포함' if has_html_tag else
             ('슬롯 플레이스홀더 포함' if has_slot_placeholder else
              ('50자 초과' if len(title) > 50 else '서술형 종결어미')))
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
    if normalized_author and ("그의" in title or "그녀의" in title) and normalized_author not in normalized_title:
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
        }

    # 0-b. Topic 직복 감지: 주제 텍스트와 지나치게 유사한 제목은 hard fail
    if topic and len(topic) >= 12:
        title_purpose = resolve_title_purpose(topic, params)
        topic_sim_threshold = 0.85 if title_purpose == 'event_announcement' else 0.75
        topic_sim = _title_similarity(title, topic)
        if topic_sim >= topic_sim_threshold:
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

    title_purpose = resolve_title_purpose(topic, params)
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

    keyword_gate = _validate_user_keyword_title_requirements(title, user_keywords)
    if not keyword_gate.get('passed'):
        repaired_candidate = _repair_title_for_missing_keywords(title, keyword_gate)
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

    # 일반 검증 경로에서는 길이 초과를 한 번 축약해볼 수 있지만,
    # 제목 생성 경로에서는 auto_fit_length=False로 두고 초기 생성본을 그대로 평가한다.
    if auto_fit_length and title_length > TITLE_LENGTH_HARD_MAX:
        fitted_title = _fit_title_length(title)
        if fitted_title and fitted_title != title:
            fitted_gate = _validate_user_keyword_title_requirements(fitted_title, user_keywords)
            fitted_severity = str(fitted_gate.get('severity') or '').strip().lower()
            fitted_gate_passed = bool(fitted_gate.get('passed')) or fitted_severity == 'soft'
            if not fitted_gate.get('passed'):
                recovered_title = _repair_title_for_missing_keywords(fitted_title, fitted_gate)
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
        delimiters = (',', '?', '!', '.', '에', '의', '을', '를', '은', '는', '이', '가', ':', ' ')
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
        breakdown['keywordPosition'] = {'score': 10, 'max': 20, 'status': '키워드없음'}
             
    # 3. Numbers Score (Max 15)
    has_numbers = bool(re.search(r'\d+(?:억|만원|%|명|건|가구|곳)?', title))
    if has_numbers:
        content_numbers_res = extract_numbers_from_content(content)
        safe_content_numbers = content_numbers_res.get('numbers', [])
        content_number_tokens = [_normalize_digit_token(c_num) for c_num in safe_content_numbers]

        allowed_event_tokens: set[str] = set()
        if title_purpose == 'event_announcement':
            allowed_event_tokens.update(_extract_digit_tokens(topic))
            allowed_event_tokens.update(_extract_digit_tokens(event_anchor_context.get('dateHint', '')))

        title_numbers = re.findall(r'\d+(?:억|만원|%|명|건|가구|곳)?', title)

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

        if all_valid:
                breakdown['numbers'] = {'score': 15, 'max': 15, 'status': '검증됨'}
        else:
                breakdown['numbers'] = {'score': 5, 'max': 15, 'status': '미검증'}
                suggestions.append('제목의 숫자가 본문에서 확인되지 않았습니다.')
    else:
        breakdown['numbers'] = {'score': 8, 'max': 15, 'status': '없음'}
        
    # 4. Topic Match (Max 25)
    if topic:
        theme_val = validate_theme_and_content(topic, content, title)
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
        category_text = str(params.get('category') or '').strip().lower()
        commentary_purposes = {'commentary', 'issue_analysis', 'current_affairs'}
        commentary_categories = {'current-affairs', 'bipartisan-cooperation'}
        prefers_relationship_style = (
            title_purpose in commentary_purposes or category_text in commentary_categories
        )

        if author_name in title:
            speaker_patterns = [
                f"{author_name}이 본", f"{author_name}가 본", f"{author_name}의 평가", f"{author_name}의 시각",
                f"칭찬한 {author_name}", f"질타한 {author_name}", f"{author_name} [\"'`]"
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

async def generate_and_validate_title(generate_fn, params: Dict[str, Any], options: Dict[str, Any] = {}) -> Dict[str, Any]:
    min_score = int(options.get('minScore', 70))
    max_attempts = int(options.get('maxAttempts', 3))
    candidate_count = max(1, int(options.get('candidateCount', 5)))
    similarity_threshold = float(options.get('similarityThreshold', 0.78))
    similarity_threshold = min(max(similarity_threshold, 0.50), 0.95)
    max_similarity_penalty = max(0, int(options.get('maxSimilarityPenalty', 18)))
    on_progress = options.get('onProgress')

    option_recent_titles = options.get('recentTitles') if isinstance(options.get('recentTitles'), list) else []
    param_recent_titles = params.get('recentTitles') if isinstance(params.get('recentTitles'), list) else []
    recent_titles: List[str] = []
    seen_recent_titles = set()
    for value in option_recent_titles + param_recent_titles:
        title = str(value or '').strip()
        if not title or title in seen_recent_titles:
            continue
        seen_recent_titles.add(title)
        recent_titles.append(title)

    history = []
    best_title = ''
    best_score = -1
    best_result = None
    title_purpose = resolve_title_purpose(str(params.get('topic') or ''), params)
    generation_failure_streak = 0

    for attempt in range(1, max_attempts + 1):
        effective_candidate_count = 1 if generation_failure_streak > 0 else candidate_count
        if on_progress:
            on_progress({
                'attempt': attempt,
                'maxAttempts': max_attempts,
                'status': 'generating',
                'candidateCount': effective_candidate_count
            })

        # 1. Prompt generation
        prompt = ""
        if attempt == 1 or not history:
            prompt = build_title_prompt(params)
        else:
            last_attempt = history[-1]
            suggestion_items = ''
            for suggestion in last_attempt.get('suggestions', []):
                suggestion_text = str(suggestion or '').strip()
                if suggestion_text:
                    suggestion_items += f"\n    <item>{suggestion_text}</item>"
            if not suggestion_items:
                suggestion_items = "\n    <item>이전 문제를 보완해 새 제목을 생성하세요.</item>"
            feedback_prompt = f"""
<previous_attempt_feedback attempt="{attempt - 1}" score="{last_attempt.get('score', 0)}">
  <previous_title>{last_attempt.get('title', '')}</previous_title>
  <issues>{suggestion_items}
  </issues>
  <instruction>위 문제를 해결한 새로운 제목을 작성하세요.</instruction>
</previous_attempt_feedback>
"""
            prompt = feedback_prompt + build_title_prompt(params)

        disallow_titles = list(recent_titles)
        disallow_titles.extend([
            str(item.get('title') or '').strip()
            for item in history
            if isinstance(item, dict) and str(item.get('title') or '').strip()
        ])

        candidate_prompts = [
            _build_title_candidate_prompt(
                prompt,
                attempt,
                idx + 1,
                effective_candidate_count,
                disallow_titles,
                title_purpose,
            )
            for idx in range(effective_candidate_count)
        ]

        # 2. Multi-candidate generation
        if effective_candidate_count == 1:
            try:
                responses = [await generate_fn(candidate_prompts[0])]
            except Exception as error:
                responses = [error]
        else:
            # 빈 응답 예방: 다중 후보를 병렬 호출하지 않고 순차 생성해 모델 부하를 낮춘다.
            responses = []
            for candidate_prompt in candidate_prompts:
                try:
                    responses.append(await generate_fn(candidate_prompt))
                except Exception as error:
                    responses.append(error)

        generation_errors: List[str] = []
        candidate_results: List[Dict[str, Any]] = []
        for idx, response in enumerate(responses, start=1):
            if isinstance(response, Exception):
                err = str(response)
                generation_errors.append(err)
                logger.warning("[TitleGen] 후보 %s 생성 실패 (attempt=%s): %s", idx, attempt, err)
                continue

            raw_generated_title = str(response or '').strip().strip('"\'')
            initial_generated_title = _normalize_generated_title_without_fit(raw_generated_title, params)
            generated_title = _normalize_generated_title(raw_generated_title, params)
            if raw_generated_title != initial_generated_title:
                logger.info(
                    "[TitleGen] 제목 정규화 적용(후보 %s): raw=\"%s\" -> normalized=\"%s\"",
                    idx,
                    raw_generated_title,
                    initial_generated_title,
                )

            if not initial_generated_title:
                continue

            initial_length_meta = _assess_initial_title_length_discipline(initial_generated_title)
            length_feedback = _build_initial_length_discipline_feedback(initial_length_meta)
            score_result = calculate_title_quality_score(
                initial_generated_title,
                params,
                {'autoFitLength': False},
            )
            repaired_title = str(score_result.get('repairedTitle') or '').strip()
            candidate_title = initial_generated_title
            if repaired_title and repaired_title != candidate_title:
                logger.info(
                    "[TitleGen] 키워드 repair 적용(후보 %s): \"%s\" -> \"%s\"",
                    idx,
                    candidate_title,
                    repaired_title,
                )
                candidate_title = repaired_title
            similarity_meta = _compute_similarity_penalty(
                candidate_title,
                disallow_titles,
                threshold=similarity_threshold,
                max_penalty=max_similarity_penalty,
            )
            adjusted_score = max(
                0,
                int(score_result.get('score', 0))
                - int(similarity_meta.get('penalty', 0))
                - int(initial_length_meta.get('penalty', 0)),
            )

            candidate_results.append({
                'candidateIndex': idx,
                'title': candidate_title,
                'rawTitle': raw_generated_title,
                'initialTitle': initial_generated_title,
                'postFitTitle': generated_title,
                'baseScore': int(score_result.get('score', 0)),
                'adjustedScore': adjusted_score,
                'scoreResult': score_result,
                'similarityMeta': similarity_meta,
                'initialLengthMeta': initial_length_meta,
                'initialLengthFeedback': length_feedback,
                'initialLengthPenalty': int(initial_length_meta.get('penalty', 0)),
            })

        if not candidate_results:
            generation_failure_streak += 1
            if generation_errors and len(generation_errors) == len(candidate_prompts):
                first_error = str(generation_errors[0])
                logger.warning(
                    "[TitleGen] attempt %s에서 후보 %s개 생성이 모두 실패했습니다. 첫 오류: %s",
                    attempt,
                    effective_candidate_count,
                    first_error,
                )
                history.append({
                    'attempt': attempt,
                    'title': '',
                    'score': 0,
                    'suggestions': [
                        f'모델 생성 오류: {first_error[:180]}',
                        '다음 시도에서 후보 수를 줄여 안정적으로 재생성합니다.',
                    ],
                    'breakdown': {'generationError': {'score': 0, 'max': 100, 'status': '실패'}},
                    'candidateCount': effective_candidate_count,
                    'generationErrors': generation_errors[:3],
                })
                continue

            history.append({
                'attempt': attempt,
                'title': '',
                'score': 0,
                'suggestions': ['후보 제목이 모두 비어 있습니다. 프롬프트 또는 모델 응답을 확인하세요.'],
                'breakdown': {'empty': {'score': 0, 'max': 100, 'status': '실패'}},
                'candidateCount': effective_candidate_count,
            })
            continue

        generation_failure_streak = 0
        selected = max(
            candidate_results,
            key=lambda item: (
                int(bool((item.get('initialLengthMeta') or {}).get('inOptimalRange'))),
                item.get('adjustedScore', 0),
                item.get('baseScore', 0),
            ),
        )
        selected_score_result = selected.get('scoreResult', {})
        selected_similarity = selected.get('similarityMeta', {})
        selected_initial_length = selected.get('initialLengthMeta', {})
        selected_suggestions = list(selected_score_result.get('suggestions', []))
        if int(selected_similarity.get('penalty', 0)) > 0:
            selected_suggestions.append(
                f"이전 제목과 유사도 {selected_similarity.get('maxSimilarity', 0)}로 "
                f"{selected_similarity.get('penalty', 0)}점 감점"
            )
        selected_length_feedback = str(selected.get('initialLengthFeedback') or '').strip()
        if selected_length_feedback:
            selected_suggestions.append(selected_length_feedback)

        selected_breakdown = dict(selected_score_result.get('breakdown', {}))
        selected_breakdown['diversityPenalty'] = {
            'score': int(selected_similarity.get('penalty', 0)),
            'max': max_similarity_penalty,
            'status': '적용' if int(selected_similarity.get('penalty', 0)) > 0 else '없음',
            'similarity': selected_similarity.get('maxSimilarity', 0),
            'against': selected_similarity.get('against', ''),
        }
        selected_breakdown['initialLengthDiscipline'] = {
            'score': max(0, 20 - int(selected.get('initialLengthPenalty', 0) or 0)),
            'max': 20,
            'status': '적합' if bool(selected_initial_length.get('inOptimalRange')) else '재작성 필요',
            'length': int(selected_initial_length.get('length', 0) or 0),
            'penalty': int(selected.get('initialLengthPenalty', 0) or 0),
        }

        history_item = {
            'attempt': attempt,
            'title': selected.get('title', ''),
            'score': selected.get('adjustedScore', 0),
            'baseScore': selected.get('baseScore', 0),
            'candidateCount': candidate_count,
            'selectedCandidate': selected.get('candidateIndex', 1),
            'similarityPenalty': int(selected_similarity.get('penalty', 0)),
            'similarity': selected_similarity.get('maxSimilarity', 0),
            'initialLengthPenalty': int(selected.get('initialLengthPenalty', 0) or 0),
            'initialTitleLength': int(selected_initial_length.get('length', 0) or 0),
            'suggestions': selected_suggestions[:4],
            'breakdown': selected_breakdown,
        }
        if selected.get('rawTitle') != selected.get('title'):
            history_item['rawTitle'] = selected.get('rawTitle', '')
        if selected.get('initialTitle') != selected.get('title'):
            history_item['initialTitle'] = selected.get('initialTitle', '')
        history.append(history_item)

        current_score = int(selected.get('adjustedScore', 0))
        if best_result is None or current_score > best_score:
            best_score = current_score
            best_title = str(selected.get('title') or '')
            best_result = history_item

        if current_score >= min_score:
            if on_progress:
                on_progress({
                    'attempt': attempt,
                    'maxAttempts': max_attempts,
                    'status': 'passed',
                    'score': current_score,
                    'baseScore': selected.get('baseScore', 0),
                    'candidateCount': effective_candidate_count
                })

            return {
                'title': selected.get('title', ''),
                'score': current_score,
                'baseScore': selected.get('baseScore', 0),
                'similarityPenalty': int(selected_similarity.get('penalty', 0)),
                'initialLengthPenalty': int(selected.get('initialLengthPenalty', 0) or 0),
                'attempts': attempt,
                'passed': True,
                'history': history,
                'breakdown': selected_breakdown,
            }

    if on_progress:
        on_progress({
            'attempt': max_attempts,
            'maxAttempts': max_attempts,
            'status': 'failed',
            'score': max(best_score, 0),
            'candidateCount': candidate_count
        })

    if best_result is None:
        last_generation_error = ''
        for item in reversed(history):
            if not isinstance(item, dict):
                continue
            errors = item.get('generationErrors')
            if isinstance(errors, list) and errors:
                last_generation_error = str(errors[0])
                break
        if last_generation_error:
            raise RuntimeError(
                f"[TitleGen] 제목 생성 실패: {max_attempts}회 시도 모두 생성 오류가 발생했습니다. "
                f"마지막 오류: {last_generation_error}"
            )
        raise RuntimeError(
            f"[TitleGen] 제목 생성 실패: {max_attempts}회 시도 모두 유효한 제목을 생성하지 못했습니다."
        )

    best_suggestions = best_result.get('suggestions', []) if isinstance(best_result, dict) else []
    suggestion_text = ', '.join(best_suggestions) if best_suggestions else '없음'
    raise RuntimeError(
        f"[TitleGen] 제목 생성 실패: 최소 점수 {min_score}점 미달 "
        f"(최고 {best_score}점, 제목: \"{best_title}\"). 개선 힌트: {suggestion_text}"
    )
