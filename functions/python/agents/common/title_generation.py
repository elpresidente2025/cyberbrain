
import re
import logging
import json
from typing import Dict, Any, List, Optional
from .election_rules import get_election_stage

logger = logging.getLogger(__name__)

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
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 【숫자 제약】본문에 등장하는 숫자만 사용 가능!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ 사용 가능 숫자: {formatted_numbers}
❌ 위 목록에 없는 숫자는 절대 제목에 넣지 마세요!

예시:
• 본문에 "274명"이 있으면 → "청년 일자리 274명" ✅
• 본문에 "85억"이 없는데 → "지원금 85억" ❌ (날조!)
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
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 선거법 준수 (현재 상태: {status} - 예비후보 등록 이전)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ 절대 금지 표현:
• "약속", "공약", "약속드립니다"
• "당선되면", "당선 후"
• "~하겠습니다" (공약성 미래 약속)
• "지지해 주십시오"

✅ 허용 표현:
• "정책 방향", "정책 제시", "비전 공유"
• "연구하겠습니다", "노력하겠습니다"
• "추진", "추구", "검토"

예시:
❌ "청년 기본소득, 꼭 약속드리겠습니다"
✅ "청년 기본소득, 정책 방향 제시"
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

def get_keyword_strategy_instruction(user_keywords: List[str], keywords: List[str]) -> str:
    try:
        has_user_keywords = bool(user_keywords)
        primary_kw = user_keywords[0] if has_user_keywords else (keywords[0] if keywords else '')
        secondary_kw = (user_keywords[1] if len(user_keywords) > 1 else (keywords[0] if keywords else '')) if has_user_keywords else (keywords[1] if len(keywords) > 1 else '')

        # 두 키워드 간 유사/독립 판별
        has_two_keywords = bool(primary_kw and secondary_kw and primary_kw != secondary_kw)
        similar = has_two_keywords and are_keywords_similar(primary_kw, secondary_kw)

        title_keyword_rule = ""
        if has_two_keywords:
            if similar:
                # 유사 키워드: 제목은 1번 키워드로 시작, 2번 키워드는 어절 해체하여 배치
                kw2_words = secondary_kw.split()
                kw1_words = primary_kw.split()
                unique_words = [w for w in kw2_words if w not in kw1_words]
                unique_hint = f'"{", ".join(unique_words)}"를 제목 뒤쪽에 녹여넣기' if unique_words else '공통 어절로 자동 충족'
                example_word = unique_words[0] if unique_words else kw2_words[0]
                title_keyword_rule = f"""
📌 **제목 키워드 배치 규칙 (유사 키워드)**
두 검색어("{primary_kw}", "{secondary_kw}")가 공통 어절을 공유하므로:
• 제목은 반드시 "{primary_kw}"로 시작
• "{secondary_kw}"는 어절 단위로 해체하여 자연스럽게 배치 ({unique_hint})
• 예시: "{primary_kw}, <보고있나, {example_word}> 출판기념회에 초대합니다"
"""
            else:
                # 독립 키워드: 제목은 1번 키워드로 시작, 2번 키워드는 뒤에 배치
                title_keyword_rule = f"""
📌 **제목 키워드 배치 규칙 (독립 키워드)**
두 검색어("{primary_kw}", "{secondary_kw}")가 독립적이므로:
• 제목은 반드시 "{primary_kw}"로 시작
• "{secondary_kw}"는 제목 뒤쪽에 자연스럽게 배치
• 예시: "{primary_kw}, 확장 공사에 {secondary_kw} 적극 구제 촉구"
"""

        kw_instruction = ""
        if primary_kw:
            kw_instruction += f"**1순위 키워드**: \"{primary_kw}\" → 제목 앞 8자 이내 배치 권장 (필수 아님, 자연스러움 우선)\n"
        if secondary_kw:
            placement = '어절 해체하여 자연 배치' if similar else '제목 뒤쪽 배치'
            kw_instruction += f"**2순위 키워드**: \"{secondary_kw}\" → {placement}\n"

        return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔑 SEO 키워드 삽입 전략
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📍 **앞쪽 1/3 법칙** (가장 중요!)
네이버는 제목 앞 8-10자를 가장 중요하게 평가합니다.
→ 핵심 키워드는 제목 시작 부분 배치를 권장하나, **강렬한 카피(Viral Hook)**를 위해 문장 중간에 자연스럽게 녹여도 됩니다.

❌ "우리 지역 청년들을 위한 청년 기본소득"
✅ "청년 기본소득, 분당구 월 50만원 지원"

🚨 **키워드 구분자 필수** (매우 중요!)
키워드 직후에 쉼표(,) 또는 조사(에, 의, 에서 등)를 넣어 다음 단어와 분리하세요.
네이버는 공백만으로는 키워드 경계를 인식하지 못합니다.
✅ "부산 지방선거, 왜 이 남자가" → 키워드 = "부산 지방선거"
✅ "부산 지방선거에 뛰어든 부두 노동자" → 키워드 = "부산 지방선거"
❌ "부산 지방선거 이재성 원칙" → 키워드 = "부산 지방선거 이재성 원칙"(잘못 인식)
{title_keyword_rule}
📊 **키워드 밀도: 최소 1개, 최대 3개**
• 최적: 2개 (가장 자연스럽고 효과적)
• 4개 이상: 스팸으로 판단, CTR 감소

📍 **위치별 배치 전략**
┌─────────────────────────────────────────────┐
│ [0-8자]     │ [9-20자]      │ [21-35자]   │
│ 지역/정책명  │ 수치/LSI     │ 행동/긴급성  │
│ 가중치 100% │ 가중치 80%   │ 가중치 60%  │
└─────────────────────────────────────────────┘

{kw_instruction}
🔄 **동의어 활용** (반복 방지)
• 지원 → 지원금, 보조금, 혜택
• 문제 → 현안, 과제, 어려움
• 해결 → 개선, 완화, 해소
"""
    except Exception as e:
        logger.error(f'Error in get_keyword_strategy_instruction: {e}')
        return ''

def build_title_prompt(params: Dict[str, Any]) -> str:
    # No try/except blocking logic here. Let it propagate.
    content_preview = params.get('contentPreview', '')
    background_text = params.get('backgroundText', '')
    topic = params.get('topic', '')
    full_name = params.get('fullName', '')
    keywords = params.get('keywords', [])
    user_keywords = params.get('userKeywords', [])
    category = params.get('category', '')
    status = params.get('status', '')
    title_scope = params.get('titleScope', {})
    forced_type = params.get('_forcedType')
    stance_text = params.get('stanceText', '')  # 🔑 [NEW] 입장문
    
    avoid_local_in_title = bool(title_scope and title_scope.get('avoidLocalInTitle'))
    detected_type_id = None
    
    if forced_type and forced_type in TITLE_TYPES:
        detected_type_id = forced_type
    else:
        detected_type_id = detect_content_type(content_preview, category)
        if avoid_local_in_title and detected_type_id == 'LOCAL_FOCUSED':
            detected_type_id = 'ISSUES_ANALYSIS' # Fallback
            
    primary_type = TITLE_TYPES.get(detected_type_id) or TITLE_TYPES['DATA_BASED']
    # If default was chosen but really we want Viral Hook for general cases:
    if detected_type_id == 'VIRAL_HOOK':
         primary_type = TITLE_TYPES['VIRAL_HOOK']
    
    number_validation = extract_numbers_from_content(content_preview)
    election_compliance = get_election_compliance_instruction(status)
    keyword_strategy = get_keyword_strategy_instruction(user_keywords, keywords)
    
    region_scope_instruction = ""
    if avoid_local_in_title:
        region_scope_instruction = f"""
[TITLE REGION SCOPE]
- Target position: {title_scope.get('position', 'metro-level') if title_scope else 'metro-level'}
- Do NOT use district/town names (gu/gun/dong/eup/myeon) in the title.
- Use the metro-wide region like "{title_scope.get('regionMetro', 'the city/province') if title_scope else 'the city/province'}".
"""

    good_lines = []
    for i, ex in enumerate(primary_type['good']):
        good_lines.append(f"{i+1}. \"{ex['title']}\" ({ex.get('chars', 0)}자)\n   → {ex.get('analysis', '')}")
    good_examples = "\n".join(good_lines)

    bad_lines = []
    for i, ex in enumerate(primary_type['bad']):
        bad_lines.append(f"{i+1}. ❌ \"{ex['title']}\"\n   문제: {ex.get('problem', '')}\n   ✅ 수정: \"{ex.get('fix', '')}\"")
    bad_examples = "\n\n".join(bad_lines)
    
    primary_kw_str = user_keywords[0] if user_keywords else '(없음)'
    
    return f"""<title_generation_prompt>

<role>네이버 블로그 제목 전문가 (클릭률 1위 카피라이터)</role>

<objective>
아래 내용을 분석하여, **독자가 클릭하지 않고는 못 배기는 서사적 긴장감이 있는 블로그 제목**을 작성하십시오.

【핵심 원칙: 정보 격차(Information Gap)】
좋은 제목은 "답"이 아니라 "질문"을 남깁니다.
- ❌ 선언형 (긴장감 없음): "이재성이 경제 0.7%를 바꾼다" → 답을 다 알려줘서 클릭 불필요
- ❌ 키워드 나열 (의미 없음): "이재성 부산 AI 3대 강국?" → 문장이 아님
- ✅ 서사적 긴장감: "부산 경제 0.7%, 왜 이 남자가 뛰어들었나" → 구체적 팩트 + 미해결 질문

【금지】
- 지루한 공무원 스타일("~개최", "~참석", "~발표")
- 선언형 결론("~바꾼다", "~이끈다", "~완성한다")
- 키워드만 나열하고 문장을 완성하지 않는 것
- 과도한 자극("충격", "경악", "결국 터졌다")
</objective>

<content_type detected="{primary_type['id']}">
  <name>{primary_type['name']}</name>
  <when>{primary_type['when']}</when>
  <pattern>{primary_type['pattern']}</pattern>
  <naver_tip>{primary_type['naverTip']}</naver_tip>
</content_type>

{('<narrative_principle>' + primary_type['principle'] + '</narrative_principle>') if primary_type.get('principle') else ''}

<input>
  <topic>{topic}</topic>
  <author>{full_name}</author>
  <stance_summary priority="Highest">{stance_text[:500] if stance_text else '(없음) - 입장문이 없으면 본문 내용 바탕으로 작성'}</stance_summary>
  <content_preview>{(content_preview or '')[:800]}</content_preview>
  <background>{background_text[:300] if background_text else '(없음)'}</background>
</input>

<examples type="good">
{good_examples}
</examples>

<examples type="bad">
{bad_examples}
</examples>

<rules priority="critical">
  <rule id="length_max">🚨 35자 이내 (네이버 검색결과 잘림 방지) - 절대 초과 금지!</rule>
  <rule id="length_optimal">18-30자 권장 (클릭률 최고 구간)
  <rule id="no_ellipsis">말줄임표("...") 절대 금지</rule>
  <rule id="keyword_position">핵심 키워드 "{primary_kw_str}" 반드시 포함. 키워드 직후에 반드시 구분자(쉼표, 물음표, 조사+쉼표)를 넣어라. ✅ "부산 지방선거, 왜~" ✅ "부산 지방선거에 뛰어든~" ❌ "부산 지방선거 이재성" (네이버가 하나의 키워드로 인식)</rule>
  <rule id="no_greeting">인사말("안녕하세요"), 서술형 어미("~입니다") 절대 금지</rule>
  <rule id="style_ban">"발표", "개최", "참석" 등 보도자료 스타일 금지</rule>
  <rule id="narrative_tension">읽은 뒤 "그래서?" "왜?"가 떠오르는 제목이 좋다. 기법을 억지로 넣지 말고 자연스러운 호기심을 만들어라. 선언형 종결("~바꾼다") 금지. 정보 요소 3개 이하.</rule>
  <rule id="info_density">제목에 담는 정보 요소는 최대 3개. SEO 키워드는 1개로 카운트. 요소: SEO키워드, 인명, 수치, 정책명, 수식어. "부산 지방선거, 왜 이 남자가 뛰어들었나" = 2개 OK. "부산 지방선거 이재명 2호 이재성 원칙 선택" = 5개 NG.</rule>
</rules>

{election_compliance}
{keyword_strategy}
{number_validation['instruction']}
{region_scope_instruction}

<topic_priority priority="highest">
  <instruction>🚨 제목의 방향은 반드시 주제(topic)를 따라야 합니다. 본문 내용이 아무리 많아도 topic이 절대 우선.</instruction>
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
  <rule>🚨 35자 이내 필수</rule>
  <rule>18-30자 권장</rule>
  <rule>말줄임표 금지</rule>
  <rule>핵심 키워드 포함</rule>
  <rule>본문에 실제 등장하는 숫자만 사용</rule>
  <rule>지루한 표현 금지</rule>
</output_rules>

<output_format>순수한 제목 텍스트만. 따옴표 제외.</output_format>

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

def calculate_title_quality_score(title: str, params: Dict[str, Any]) -> Dict[str, Any]:
    # No try/except blocking logic here. Let it propagate.
    topic = params.get('topic', '')
    content = params.get('contentPreview', '')
    user_keywords = params.get('userKeywords', [])
    author_name = params.get('fullName', '')
    
    if not title:
        return {'score': 0, 'breakdown': {}, 'passed': False, 'suggestions': ['제목이 없습니다']}
        
    # 0. Critical Failure Checks
    looks_like_content = (
        '여러분' in title or
        '<' in title or
        title.endswith('입니다') or
        title.endswith('습니다') or
        title.endswith('습니까') or
        title.endswith('니다') or
        len(title) > 50
    )
    
    if looks_like_content:
        reason = '호칭("여러분") 포함' if '여러분' in title else ('HTML 태그 포함' if '<' in title else ('50자 초과' if len(title) > 50 else '서술형 종결어미'))
        return {
            'score': 0,
            'breakdown': {'contentPattern': {'score': 0, 'max': 100, 'status': '실패', 'reason': reason}},
            'passed': False,
            'suggestions': [f'제목이 본문처럼 보입니다 ({reason}). 검색어 중심의 간결한 제목으로 다시 작성하세요.']
        }
        
    if '...' in title or title.endswith('..'):
             return {
            'score': 0,
            'breakdown': {'ellipsis': {'score': 0, 'max': 100, 'status': '실패', 'reason': '말줄임표 포함'}},
            'passed': False,
            'suggestions': ['말줄임표("...") 사용 금지. 내용을 자르지 말고 완결된 제목을 작성하세요.']
        }
        
    breakdown = {}
    suggestions = []
    title_length = len(title)
    
    # Hard fail length check
    if title_length < 12 or title_length > 35:
             return {
            'score': 0,
            'breakdown': {'length': {'score': 0, 'max': 100, 'status': '실패', 'reason': f'{title_length}자 (18-35자 필요)'}},
            'passed': False,
            'suggestions': [f'제목이 {title_length}자입니다. 18-35자 범위로 작성하세요.']
        }

    # 1. Length Score (Max 20)
    if 18 <= title_length <= 30:
        breakdown['length'] = {'score': 20, 'max': 20, 'status': '최적'}
    elif 12 <= title_length < 18:
        breakdown['length'] = {'score': 12, 'max': 20, 'status': '짧음'}
        suggestions.append(f'제목이 {title_length}자입니다. 18자 이상 권장.')
    elif 30 < title_length <= 35:
        breakdown['length'] = {'score': 12, 'max': 20, 'status': '경계'}
        suggestions.append(f'제목이 {title_length}자입니다. 30자 이하가 클릭률 최고.')
    else:
        breakdown['length'] = {'score': 0, 'max': 20, 'status': '부적정'}
        suggestions.append(f'제목이 {title_length}자입니다. 18-30자 범위로 작성하세요.')
        
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
        kw_delimiter_ok = True
        for k in keyword_infos:
            if k['index'] >= 0:
                end_pos = k['index'] + len(k['keyword'])
                if end_pos < len(title):
                    next_char = title[end_pos]
                    # 구분자: 쉼표, 물음표, 조사(에,의,에서,을,를,은,는,이,가), 마침표, 느낌표
                    if next_char not in (',', '?', '!', '.', '에', '의', '을', '를', '은', '는', '이', '가', ':', ' '):
                        kw_delimiter_ok = False
                    elif next_char == ' ':
                        # 공백 뒤에 바로 한글(이름 등)이 오면 구분자 부족
                        if end_pos + 1 < len(title) and '\uac00' <= title[end_pos + 1] <= '\ud7a3':
                            kw_delimiter_ok = False

        # 듀얼 키워드 배치 검증: 1번 키워드가 제목 시작에 있는지
        dual_kw_bonus = 0
        dual_kw_penalty = 0
        if len(user_keywords) >= 2:
            kw1 = user_keywords[0]
            kw1_idx = title.find(kw1)
            kw1_starts_title = 0 <= kw1_idx <= 2  # 제목 맨 앞(0~2자 내)
            if kw1_starts_title:
                dual_kw_bonus = 3
            elif kw1_idx < 0:
                dual_kw_penalty = 5
                suggestions.append(f'1순위 키워드 "{kw1}"가 제목에 없습니다. 제목 시작 부분에 배치하세요.')

            # 2번 키워드: 유사면 어절 해체 충족, 독립이면 포함 여부
            kw2 = user_keywords[1]
            similar = are_keywords_similar(kw1, kw2)
            if similar:
                kw2_words = kw2.split()
                kw1_words = kw1.split()
                unique_words = [w for w in kw2_words if w not in kw1_words and len(w) >= 2]
                has_unique = len(unique_words) == 0 or any(w in title for w in unique_words)
                if not has_unique:
                    dual_kw_penalty += 3
                    suggestions.append(f'2순위 키워드 "{kw2}"의 고유 어절({", ".join(unique_words)})이 제목에 없습니다.')
            else:
                if kw2 not in title:
                    dual_kw_penalty += 3
                    suggestions.append(f'2순위 키워드 "{kw2}"가 제목에 포함되지 않았습니다.')

        if any_in_front10:
            score = min(20, max(0, (20 if kw_delimiter_ok else 15) + dual_kw_bonus - dual_kw_penalty))
            status = '최적' if kw_delimiter_ok else '최적(구분자 부족)'
            breakdown['keywordPosition'] = {'score': score, 'max': 20, 'status': status, 'keyword': front_keyword}
            if not kw_delimiter_ok:
                suggestions.append(f'키워드 "{front_keyword}" 뒤에 쉼표나 조사를 넣어 다음 단어와 분리하세요. (예: "부산 지방선거, ~")')
        elif any_in_title:
            score = max(0, 12 - dual_kw_penalty)
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
        
        title_numbers = re.findall(r'\d+(?:억|만원|%|명|건|가구|곳)?', title)
        
        # Check if all title numbers exist in content (fuzzy match)
        all_valid = True
        for t_num in title_numbers:
            t_val = re.sub(r'[^\d]', '', t_num)
            # Check if t_val exists inside any content number OR any content number exists inside t_val
            if not any(t_val in re.sub(r'[^\d]', '', c_num) or re.sub(r'[^\d]', '', c_num) in t_val for c_num in safe_content_numbers):
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
        if theme_val['overlapScore'] >= 80:
            breakdown['topicMatch'] = {'score': 25, 'max': 25, 'status': '높음', 'overlap': theme_val['overlapScore']}
        elif theme_val['overlapScore'] >= 50:
            breakdown['topicMatch'] = {'score': 15, 'max': 25, 'status': '보통', 'overlap': theme_val['overlapScore']}
            if theme_val['mismatchReasons']:
                suggestions.append(theme_val['mismatchReasons'][0])
        else:
            breakdown['topicMatch'] = {'score': 5, 'max': 25, 'status': '낮음', 'overlap': theme_val['overlapScore']}
            suggestions.append('제목이 주제와 많이 다릅니다. 주제 핵심어를 반영하세요.')
    else:
        breakdown['topicMatch'] = {'score': 15, 'max': 25, 'status': '주제없음'}
        
    # 5. Author Inclusion (Max 10)
    if author_name:
        if author_name in title:
            speaker_patterns = [
                f"{author_name}이 본", f"{author_name}가 본", f"{author_name}의 평가", f"{author_name}의 시각",
                f"칭찬한 {author_name}", f"질타한 {author_name}", f"{author_name} [\"'`]"
            ]
            has_pattern = any(re.search(p, title) for p in speaker_patterns)
            
            if has_pattern:
                breakdown['authorIncluded'] = {'score': 10, 'max': 10, 'status': '패턴 적용'}
            else:
                breakdown['authorIncluded'] = {'score': 6, 'max': 10, 'status': '단순 포함'}
                suggestions.append(f'"{author_name}이 본", "칭찬한 {author_name}" 등 관계형 표현 권장.')
        else:
            breakdown['authorIncluded'] = {'score': 0, 'max': 10, 'status': '미포함'}
            suggestions.append(f'화자 "{author_name}"를 제목에 포함하면 브랜딩에 도움됩니다.')
    else:
        breakdown['authorIncluded'] = {'score': 5, 'max': 10, 'status': '해당없음'}

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
    
    return {
        'score': normalized_score,
        'rawScore': total_score,
        'maxScore': max_possible,
        'breakdown': breakdown,
        'passed': normalized_score >= 70,
        'suggestions': suggestions[:3]
    }

async def generate_and_validate_title(generate_fn, params: Dict[str, Any], options: Dict[str, Any] = {}) -> Dict[str, Any]:
    min_score = options.get('minScore', 70)
    max_attempts = options.get('maxAttempts', 3)
    on_progress = options.get('onProgress')
    
    history = []
    best_title = ''
    best_score = 0
    best_result = None
    
    for attempt in range(1, max_attempts + 1):
        if on_progress:
            on_progress({'attempt': attempt, 'maxAttempts': max_attempts, 'status': 'generating'})
            
        # 1. Prompt generation
        # Allow build_title_prompt to throw -> fails whole process
        prompt = ""
        if attempt == 1 or not history:
            prompt = build_title_prompt(params)
        else:
            last_attempt = history[-1]
            feedback_prompt = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 이전 제목 피드백 (점수: {last_attempt.get('score', 0)}/100)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
이전 제목: "{last_attempt.get('title', '')}"
문제점:
{chr(10).join([f'• {s}' for s in last_attempt.get('suggestions', [])])}

위 문제를 해결한 새로운 제목을 작성하세요.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
            prompt = feedback_prompt + build_title_prompt(params)
            
        # 2. Generation
        # Allow generate_fn to throw (e.g. timeout) -> fails whole process
        generated_title = await generate_fn(prompt)
        generated_title = generated_title.strip().strip('"\'')
            
        if not generated_title:
            continue
            
        # 3. Score
        # Allow calculate_title_quality_score to throw -> fails whole process
        score_result = calculate_title_quality_score(generated_title, params)
        
        history.append({
            'attempt': attempt,
            'title': generated_title,
            'score': score_result['score'],
            'suggestions': score_result.get('suggestions', []),
            'breakdown': score_result.get('breakdown', {})
        })
        
        if score_result['score'] > best_score:
            best_score = score_result['score']
            best_title = generated_title
            best_result = score_result
            
        if score_result['score'] >= min_score:
            if on_progress:
                 on_progress({'attempt': attempt, 'maxAttempts': max_attempts, 'status': 'passed', 'score': score_result['score']})
            
            return {
                'title': generated_title,
                'score': score_result['score'],
                'attempts': attempt,
                'passed': True,
                'history': history,
                'breakdown': score_result.get('breakdown', {})
            }
            
    # Fallback checking
    if best_score < 30 or (best_title and len(best_title) > 35):
        logger.error(f"🚨 [TitleGen] 점수 미달 ({best_score}점) - 저품질 제목 리턴")
        # best_title might be empty if all failed
        
    if on_progress:
        on_progress({'attempt': max_attempts, 'maxAttempts': max_attempts, 'status': 'best_effort', 'score': best_score})
        
    return {
        'title': best_title,
        'score': best_score,
        'attempts': max_attempts,
        'passed': best_score >= min_score,
        'history': history,
        'breakdown': best_result.get('breakdown', {}) if best_result else {}
    }
