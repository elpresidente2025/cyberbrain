# functions/python/agents/common/leadership.py
# 리더십 철학/핵심가치/선호표현 — leadership.js 완전 이식
# ※ 범용성 원칙의 명시적 예외로 사용자가 승인한 파일
#
# 이 파일은 프로젝트의 영혼이다.
# 모든 사용자가 이 정치 철학을 기본 프레임으로 갖고 글을 쓴다.
# communicationStyle, frequentPhrases, peopleFirstTone, PRAGMATIC_EXPERIENCE는
# 커뮤니케이션 방식이므로 프롬프트에 주입하지 않는다 (각자의 fingerprint 영역).

from __future__ import annotations

import re
from typing import Any, Iterable

from .local_currency_names import LOCAL_CURRENCY_ENTRIES

# ============================================================================
# 5대 핵심 가치
# ============================================================================

CORE_LEADERSHIP_VALUES = {
    'basicSociety': {
        'vision': '모든 국민의 기본적 생활 보장과 인간다운 삶',
        'principles': [
            '누구도 배제되지 않는 사회 안전망',
            '최소한의 인간다운 삶 보장',
            '기본권으로서의 생존권 확립',
            '국가의 기본 책무 이행',
        ],
        'policies': ['기본소득제 도입', '전국민 기본서비스', '주거권 보장', '의료접근권 확대'],
        'philosophy': '인간의 존엄성이 정치의 출발점',
    },
    'inclusiveNation': {
        'vision': '차별 없는 사회, 소외계층을 품는 따뜻한 공동체',
        'principles': [
            '그 누구도 뒤처지지 않는 사회',
            '다양성을 인정하고 포용하는 문화',
            '사회적 약자 우선 배려',
            '공동체 연대와 상생',
        ],
        'policies': ['차별금지법 제정', '사회적 약자 보호 강화', '지역 균형발전', '세대 간 상생정책'],
        'philosophy': '다름을 인정하고 함께 가는 사회',
    },
    'fairEconomy': {
        'vision': '기회의 평등, 불평등 해소, 상생발전',
        'principles': [
            '출발선의 공정성 확보',
            '과정의 투명성과 공정성',
            '결과의 합리적 분배',
            '대기업과 중소기업의 상생',
        ],
        'policies': ['재벌개혁과 경제민주화', '중소기업 지원 확대', '공정거래질서 확립', '노동자 권익 보호'],
        'philosophy': '시장의 효율성과 사회적 책임의 조화',
    },
    'peopleFirst': {
        'vision': '서민과 중산층 중심의 실용적 정책',
        'principles': [
            '현장에서 답을 찾는 정치',
            '이론보다 실효성 중시',
            '서민 체감도 우선 고려',
            '즉시 실행 가능한 대안',
        ],
        'policies': ['생활밀착형 정책 우선', '서민 부담 경감', '중산층 복원', '생활임금제 확산'],
        'philosophy': '화려한 구호보다 실질적 변화',
    },
    'basicIncome': {
        'vision': '보편적 복지로 모든 국민의 존엄성 보장',
        'principles': [
            '일할 권리와 쉴 권리의 균형',
            '기술발전 혜택의 공유',
            '개인의 선택권 존중',
            '사회 전체의 안정성 확보',
        ],
        'policies': [
            '전국민 기본소득 단계적 도입',
            '청년기본소득 확대',
            '농민기본소득 실시',
            '일하는 모든 이에게 기본소득',
        ],
        'philosophy': '개인의 자유와 사회적 연대의 새로운 결합',
    },
}

# ============================================================================
# 리더십 철학
# ============================================================================

LEADERSHIP_PHILOSOPHY = {
    'coreprinciples': {
        'humanCentered': {
            'principle': '사람이 우선',
            'meaning': '모든 정책과 주장은 사람이 우선이라는 가치에서 출발',
            'application': '경제성장도 사람을 위해, 제도개선도 사람을 위해',
        },
        'fieldBased': {
            'principle': '현장 중심',
            'meaning': '현장에서 답을 찾고 현실에 기반한 정책',
            'application': '성남·경기도 경험을 통한 검증된 정책',
        },
        'resultOriented': {
            'principle': '결과 중심',
            'meaning': '화려한 말보다 실질적 변화와 성과',
            'application': '체감할 수 있는 변화, 측정 가능한 성과',
        },
        'inclusive': {
            'principle': '포용적 접근',
            'meaning': '대립보다 통합, 갈등보다 협력',
            'application': '반대 의견도 인정하되 더 나은 대안 제시',
        },
    },
    'policyApproach': {
        'pragmatic': {
            'style': '실용주의적 접근',
            'characteristics': ['이념보다 실효성', '이론보다 현실성', '완벽보다 개선', '점진적 변화 추구'],
        },
        'evidenceBased': {
            'style': '근거 기반 정책',
            'characteristics': [
                '성남시·경기도 실험과 검증',
                '데이터와 통계 활용',
                '파일럿 프로그램 우선',
                '성과 측정과 개선',
            ],
        },
        'collaborative': {
            'style': '협력적 거버넌스',
            'characteristics': [
                '시민 참여 중시',
                '전문가 의견 수렴',
                '사회적 합의 추구',
                '지속가능한 정책 설계',
            ],
        },
    },
    'communicationStyle': {
        'tone': {
            'warm': '따뜻하고 친근한 어조',
            'humble': '겸손하고 진솔한 자세',
            'confident': '확신에 찬 비전 제시',
            'empathetic': '서민의 아픔에 공감',
        },
        'method': {
            'storytelling': '개인 경험과 현장 사례 활용',
            'datadriven': '구체적 수치와 근거 제시',
            'futureoriented': '희망적 미래 비전 제시',
            'actionable': '실행 가능한 구체적 방안',
        },
    },
}

# ============================================================================
# 균형 접근법
# ============================================================================

BALANCED_APPROACH = {
    'reconciliation': {
        'ideologyVsPragmatism': {
            'approach': '이념적 순수성과 현실적 효과성의 조화',
            'method': '원칙은 지키되 방법은 유연하게',
        },
        'growthVsDistribution': {
            'approach': '성장과 분배의 선순환 구조',
            'method': '포용적 성장을 통한 동반 발전',
        },
        'efficiencyVsEquity': {
            'approach': '효율성과 형평성의 균형',
            'method': '시장 효율성 활용하되 사회적 책임 강조',
        },
        'centralVsLocal': {
            'approach': '중앙과 지방의 상생 협력',
            'method': '지방분권과 국가 역할의 조화',
        },
    },
    'constructiveCriticism': {
        'process': [
            '1. 상대방 논리 인정 → "~라는 관점도 이해하지만"',
            '2. 현실적 한계 지적 → "그러나 현장에서는..."',
            '3. 포용적 대안 제시 → "보다 따뜻하고 현실적인 방안은..."',
            '4. 구체적 근거와 사례 → "실제 성남·경기도에서의 경험을 보면..."',
            '5. 상생 발전 지향 → "결국 모든 국민이 함께 잘사는 길은..."',
        ],
        'principles': [
            '무조건적 반대보다 건설적 비판',
            '비판에는 반드시 대안 첨부',
            '개인 공격이 아닌 정책 논쟁',
            '미래 지향적 해결책 제시',
        ],
    },
}

# ============================================================================
# 선호 표현
# ============================================================================

PREFERRED_EXPRESSIONS = {
    'coreKeywords': {
        'values': ['기본사회', '포용', '공정', '민생', '서민', '복지국가', '기본소득', '상생', '연대', '공동체'],
        'policies': ['전국민기본소득', '국민취업지원제도', '부동산투기억제', '재벌개혁', '의료공공성'],
        'philosophy': ['사람중심', '생명존중', '평등', '정의', '소통', '혁신', '지속가능발전'],
    },
    'frequentPhrases': {
        'opening': ['"안녕하세요, 여러분"', '"주민 여러분과 함께하는"', '"현장에서 만난"'],
        'transition': [
            '"제가 성남시장·경기도지사로 일하면서 확인한 것은"',
            '"직접 경험해보니"',
            '"현장에서 답을 찾았습니다"',
        ],
        'policy': ['"사람이 우선되는 정책"', '"모든 국민이 함께 잘사는"', '"따뜻하고 현실적인"'],
        'closing': [
            '"여러분과 함께 만들어가겠습니다"',
            '"더 나은 미래를 위해 최선을 다하겠습니다"',
            '"계속해서 소통하겠습니다"',
        ],
    },
    'peopleFirstTone': {
        'characteristics': [
            '서민적이고 친근한 어투 (과도한 격식 지양)',
            '구체적 생활 사례 중심의 설명 (추상적 이론 지양)',
            '기득권 비판 시에도 건설적 개혁 방향 제시',
            '"더불어 사는 세상", "따뜻한 공동체" 등 포용적 가치 강조',
        ],
        'examples': [
            '"일하는 모든 분들이 안정된 생활을 할 수 있도록"',
            '"아이 키우기 좋은 세상을 만들겠습니다"',
            '"어르신들이 존경받는 사회를 구현하겠습니다"',
            '"청년들이 희망을 가질 수 있는 나라를 만들겠습니다"',
        ],
    },
}

# ============================================================================
# 실용주의 경험
# ============================================================================

PRAGMATIC_EXPERIENCE = {
    'seongnamExperience': {
        'achievements': [
            '청년배당(기본소득) 최초 도입',
            '무상급식 전면 실시',
            '산후조리비 지원(산모 건강지원사업 제도화)',
            '청년창업지원센터 설립',
        ],
        'lessons': [
            '작은 실험이 큰 변화의 시작',
            '시민과의 직접 소통의 중요성',
            '재정 건전성과 복지 확대의 양립 가능',
            '혁신 정책의 전국 확산 가능성',
        ],
    },
    'gyeonggiExperience': {
        'achievements': [
            '전국 최초 청년기본소득 도입',
            '농민기본소득 시범사업',
            '재난기본소득 도민 전원 지급(중앙정부 긴급재난지원금 촉발)',
            '공공병원 확충과 의료공공성 강화',
        ],
        'lessons': [
            '기본소득의 실현 가능성과 효과 입증',
            '위기 상황에서의 신속한 정책 대응',
            '광역자치단체 차원의 혁신 모델',
            '중앙정부와의 협력과 견제의 균형',
        ],
    },
    'policyValidation': {
        'method': '작은 실험 → 효과 검증 → 점진적 확대',
        'principle': '이론적 완벽성보다 현실적 효과성',
        'approach': '파일럿 프로그램 통한 사전 검증',
        'expansion': '성공 모델의 전국 확산',
    },
}


# ============================================================================
# 논거 레이어 — 변증법 구조의 higher_principle / counterargument_rebuttal 소재
# ============================================================================
# ChatGPT + Gemini 리서치 병합 (2026-04).
# expansion 단계에서만 선택적으로 주입된다.

ARGUMENT_LAYER = {
    'basicSociety': {
        'argument_chains': [
            {
                'policy_domain': '보편적 안전망',
                'logic': '4차 산업혁명 → AI·로봇 일자리 대체 가속 → 다수 소득 급감 → 선별적 복지로 방어 불가',
                'connection': '생존 필수 조건(소득·주거·의료·돌봄·교육)을 시장 논리 대신 보편적 권리로 보장 = 기본사회',
            },
            {
                'policy_domain': '주거 정책',
                'logic': '주거 불안 → 노동·교육·건강 전 영역 불안정 전이',
                'connection': '주거권 보장 = 기본권으로서의 생존권 확립의 제도적 실현',
            },
            {
                'policy_domain': '거버넌스 설계',
                'logic': '8대 핵심 과제(소득보장·공공의료·돌봄·주거·교육·일과삶균형·이동권·에너지전환) → 기본사회위원회 설치로 총괄',
                'connection': '비전이 구속력 있는 거버넌스 개편으로 이어짐',
            },
            {
                'policy_domain': '민간 공백의 공공 대체',
                'logic': '민간 병원 철수·수익성 낮은 돌봄 영역 외면 → 생애주기 위기 구간(출산·질병·고령)의 시장 실패',
                'connection': '주민발의 공공병원·공공실버주택·예방 치과주치의로 공공이 인프라를 직접 떠안는 기본사회',
            },
        ],
        'empirical_evidence': [
            {
                'claim': '핀란드 Housing First 프로그램으로 노숙률 35% 감소, 유럽 유일 노숙 감소국',
                'source': 'Y-Foundation, 2019',
            },
            {
                'claim': '한국 OECD 노인빈곤율 1위, 자살률 1위, 출산율 최저 — 각자도생 시스템의 구조적 결과',
                'source': 'OECD, 2024',
            },
            {
                'claim': '성남시의료원(517병상·주민발의 10년 프로젝트)을 2013년 기공, 2017년 공사 재개로 실질 궤도 진입. 수정·중원 지역 의료공백 해소가 목적(개원은 2020년 7월로 재임 이후)',
                'source': '성남시 재정공시·연합뉴스, 2015-2020',
            },
            {
                'claim': '성남 초등 치과주치의 시범 1,763명(2016) → 8,000명 전면 확대(2017), 수검률 89.8%. 치료비 보전이 아니라 불소도포·구강검사·홈메우기 등 예방 중심 공공보건',
                'source': '성남시 보건소, 2016-2017',
            },
            {
                'claim': '위례공공실버주택 164가구 + 위례·목련 공공실버복지관 결합형 모델 — 주거·돌봄·여가를 분리하지 않고 고령 저소득층 생활동선 안에 통합',
                'source': '성남시, 2016-2017',
            },
        ],
        'international_precedents': [
            {
                'country': '덴마크·스웨덴',
                'policy': '유연안정성(Flexicurity)',
                'outcome': '강력한 안전망이 기업의 유연한 노동시장 운영과 거시 경제 혁신을 동시 가능케 함',
            },
            {
                'country': 'EU',
                'policy': '정의로운 전환(Just Transition)',
                'outcome': '2050 탄소중립 + 디지털 혁신 투자 → 과실로 불평등 완화',
            },
        ],
        'counter_rebuttals': [
            {
                'criticism': '복지 확대는 재정 건전성을 해치는 포퓰리즘이다',
                'rebuttal': '한국 국가부채 비율은 선진국 대비 현저히 낮은데, 정부 긴축 강박이 오히려 가계부채를 세계 최고 수준으로 폭증시켰다. 기본사회 투자는 소비 진작 + 조세 수익 증대로 돌아오는 거시경제적 투자다.',
            },
            {
                'criticism': '무상 복지가 국민을 나태하게 만든다',
                'rebuttal': '독일 베를린 기본소득 3년 실험(2021-2024): 수급자 90%가 주당 40시간 정상 근로 유지. 불안 제거 시 교육 투자·창업 시도 등 사회적 도약대 효과 확인.',
            },
        ],
        'korean_context': [
            {
                'context': '한국 자영업자 비율 OECD 3위(~24%), 경기 충격 = 대규모 생존 위기',
                'implication': '자영업자 안전망은 기본사회의 핵심 과제',
            },
            {
                'context': '세계 10위 경제 규모이나 OECD 최악 노인빈곤율·자살률, 최저 출산율',
                'implication': '압축성장 과정에서 개인 보호를 방기한 각자도생 시스템의 비극적 결과 → 기본사회는 국가 역할 재정의',
            },
            {
                'context': '성남 본시가지 종합병원 2곳 폐업(2003) 후 10년 넘게 멈춰 있던 주민발의 공공병원 운동이 성남시의료원 착공으로 이어짐',
                'implication': '시장이 버린 생애주기 위기 구간을 공공이 직접 떠안는 한국형 기본사회의 실증 — "민간 철수 = 공공 공백"이 아닌 "민간 철수 = 공공 책임"',
            },
        ],
    },
    'inclusiveNation': {
        'argument_chains': [
            {
                'policy_domain': '억강부약의 재정의',
                'logic': '억강 = 기득권 카르텔의 의사결정 독점·룰 조작 차단 / 부약 = 약자의 협상력·역량(Empowerment) 강화',
                'connection': '포용국가는 억강부약의 저울이 평형을 이룰 때 완성',
            },
            {
                'policy_domain': '대동세상의 현대적 구현',
                'logic': '천하위공(天下爲公) → 유아·노인·병자·홀로된 자를 공동체가 보듬는 대동세상',
                'connection': '동양 평등주의 이상을 현대 복지국가 언어로 치환한 것이 포용국가',
            },
            {
                'policy_domain': '금융 포용',
                'logic': '제1금융권 소외 → 불법 사금융 → 경제 공동체 이탈',
                'connection': '극저신용대출 2.0으로 저신용자를 경제 공동체 안으로 재포용',
            },
        ],
        'empirical_evidence': [
            {
                'claim': '경기도 극저신용대출 2.0: 제1금융권 소외 저신용자에게 공공 직접 금융 제공',
                'source': '경기도, 2025',
            },
            {
                'claim': '5대 돌봄 국가 책임제(영유아·초등·노인·장애인·간호간병) + 지역사회 통합돌봄 고도화',
                'source': '기본사회 8대 과제, 2025',
            },
            {
                'claim': '플랫폼·특수고용 노동자 고용보험 확대, 상병수당 도입, 영케어러 맞춤형 소득지원',
                'source': '기본사회 정책 패키지',
            },
            {
                'claim': '경기도 극저신용대출 1만8,233명 296억 원(연 1% 저금리·최대 300만 원) + 재도전론 6,039명 158억 원 — 불법사금융 이탈을 막는 생활안전망',
                'source': '경기도 복지국, 2021',
            },
            {
                'claim': '성남시 장애인 일자리 54명(2010) → 177명(2017), 장애인 권리증진센터 전국 최초 설치, 인식개선 교육 4만8,320명(2013-2017)',
                'source': '성남시, 2017',
            },
        ],
        'international_precedents': [
            {
                'country': '미국',
                'policy': 'Biden 포용적 자본주의(Inclusive Capitalism) + 친노동 입법',
                'outcome': '거대 자본 독주 제어, 노동자·시민 권리 격상',
            },
            {
                'country': 'EU / ILO',
                'policy': '유럽 사회적 권리 기둥(European Pillar of Social Rights) + ILO 플랫폼 노동자 보호 기준',
                'outcome': '약자 협상력 복원이 지속 가능한 경제 체제의 글로벌 스탠더드로 정립',
            },
        ],
        'counter_rebuttals': [
            {
                'criticism': '억강부약은 기업 혁신을 적으로 매도하는 반기업적 이분법이다',
                'rebuttal': '억강부약은 가장 합리적인 친시장 정책이다. 독점 카르텔이 가로막은 다수의 창의성과 기회를 해방시켜 기업인·사업자 모두에게 더 큰 성장 공간을 만든다. 기울어진 운동장을 평평하게 만드는 것이지 성장 동력을 부정하는 것이 아니다.',
            },
            {
                'criticism': '이재명식 복지는 시민 합의 없이 강행됐다',
                'rebuttal': '반대다. 성남시의료원은 2003년 주민발의 조례 운동에서 출발한 프로젝트였고 시민 요구가 시장보다 먼저 있었다. 막은 것은 시의회였다(2011년 건립비 102.8억 중 56.8억 삭감). 시민 합의 부재가 아니라 대의기구의 봉쇄가 사실관계다.',
            },
        ],
        'korean_context': [
            {
                'context': '이재명의 소년공 산재 경험 — 노동권 유린·국가 부재 시절의 상흔',
                'implication': '억강부약의 실존적 원동력이자, 엘리트 관료주의에서 포착 불가능한 현장밀착형 정책의 사상적 뿌리',
            },
            {
                'context': '코로나 + 내란 복합 위기 → 청년 실업 치솟고 민생 피폐',
                'implication': '국가가 최후의 보루 역할을 수행해야 한다는 부약(扶弱) 철학의 시대적 긴급성',
            },
            {
                'context': '경기도 2차 재난기본소득은 도민 기준을 국적이 아닌 거주·생활기반으로 재정의(등록외국인·거소신고자 58만 명 포함, 13개 언어 안내)',
                'implication': '포용국가를 추상적 다문화 담론이 아닌 세금·지역경제 공동체 단위로 실증한 광역 지방정부 사례. 감염병·경제위기에서는 배제보다 생활권 단위 보호가 공중보건·지역경제 모두에 유리',
            },
        ],
    },
    'fairEconomy': {
        'argument_chains': [
            {
                'policy_domain': '지대 추구 타파',
                'logic': '저성장·청년 좌절의 원인은 자원 부족이 아니라 다수 노력이 소수 불로소득으로 치환되는 불공정 구조',
                'connection': '행정력으로 불법·편법·독점·카르텔을 응징 → 시장 효율성 복원 → 과실을 대중에게 환원',
            },
            {
                'policy_domain': '정보 투명성',
                'logic': '불투명 정보에 기생 → 부풀려진 수익 → 원가 공개 + 단속으로 지대 차단',
                'connection': '공공건설 원가 공개가 납세자 주권 회복의 시작',
            },
            {
                'policy_domain': '플랫폼 독점 해체',
                'logic': '대형 배달앱 독과점 → 수수료 착취 → 소상공인·소비자 비용 전가',
                'connection': '공공배달앱(배달특급)으로 시장 실패 교정, 데이터 국민 환원',
            },
            {
                'policy_domain': '분배의 지역경제 순환',
                'logic': '청년배당 → 지역화폐 유통 → 골목상권 가맹점 확대 → 생활비·자기계발 소비 → 노동시장 진입 질 개선',
                'connection': '분배정책은 소비 진작 + 지역경제 기반 복원 + 노동조건 완충까지 연결되는 순환 설계 — 낙수효과 대신 분수효과',
            },
        ],
        'empirical_evidence': [
            {
                'claim': '공공건설 원가 공개(10억 이상): 도민 찬성 90-92%, 아파트 분양가 인하 기대 74%',
                'source': '케이스탯리서치 여론조사',
            },
            {
                'claim': '표준시장단가 적용(100억 미만 소규모 공사): 평균 4.4% 예산 절감 효과',
                'source': '경기도 자체 분석',
            },
            {
                'claim': '페이퍼컴퍼니 사전단속 8개월 만에 42개사 적발, 공공입찰 응찰률 22% 감소(좀비 기업 퇴출)',
                'source': '경기도, 2019',
            },
            {
                'claim': '187개 하천 1,437곳 불법 시설물(평상 등) 강제 철거 — 사유화된 자연을 도민에게 환원',
                'source': '경기도 계곡 불법시설 정비',
            },
            {
                'claim': '체납관리단 2019년 795억 원 체납 세금 징수 + 생계형 체납자 1,421명은 복지서비스로 연계 — 조세정의와 복지 동시 작동',
                'source': '경기도 체납관리단, 2019',
            },
            {
                'claim': '성남사랑상품권 유통 2015년 133억 → 2016년 249억(87%↑), 가맹점 2017년 7,151 → 8,738곳. 청년배당 지역화폐가 골목상권 총량을 견인하고 생활비·자기계발 비중이 다수 사용처',
                'source': '성남농협·성남시, 2016-2017',
            },
            {
                'claim': '경기도 지역화폐 발행 2019년 4,961억 → 2021년 4조6,453억으로 9.4배 확장. 기본소득·면접수당·생리용품 지원이 동일 인프라 위에서 순환하는 광역 정책 플랫폼으로 기능',
                'source': '경기도, 2019-2021',
            },
            {
                'claim': '경기도 공정특별사법경찰단 3년간 2,402명 적발·836명 송치. 불법 대부업 경제범죄 174명 적발(황금대부파 연 31,000% 금리·피해자 3,600명 적발 포함)',
                'source': '경기도 공정특사경, 2018-2021',
            },
        ],
        'international_precedents': [
            {
                'country': '에스토니아·핀란드',
                'policy': '전자정부: 모든 입찰·지출 내역 시민 공개',
                'outcome': '정보 비대칭 해소 → 부패 원천 차단',
            },
            {
                'country': '미국(FTC) / EU(DMA)',
                'policy': '빅테크 게이트키퍼 해체, 시장지배력 남용 제재',
                'outcome': '시장 규칙 훼손자에 대한 강력한 행정 제재가 글로벌 스탠더드로 정립',
            },
        ],
        'counter_rebuttals': [
            {
                'criticism': '원가 공개·표준시장단가가 중소 건설업체의 적정 이윤을 박탈한다',
                'rebuttal': '불투명 정보에 기생한 부풀려진 수익은 적정 이윤이 아니다. 4.4% 절감은 노동자 임금이 아니라 중간에서 불법적으로 새는 지대(Rent)를 차단한 것이며, 절약분은 복지·지역경제에 재투입된다.',
            },
            {
                'criticism': '공공배달앱은 민간 혁신 영역에 세금 투입하는 관치 경제다',
                'rebuttal': '플랫폼 사업자의 사실상 독점적 지위를 이용한 소상공인·소비자 비용 전가는 시장 실패다. 공공이 마중물 역할을 하는 정당한 시장 안정화 조치.',
            },
            {
                'criticism': '지역화폐는 효과 없다는 국책연구 결과(한국조세재정연구원 2020)가 있다',
                'rebuttal': '조세연 분석은 2010-2018년 전국 사업체 단면 자료를 사용했다. 경기도 지역화폐가 본격 확대된 2019년 이후 국면은 반영되지 않았다. 이후 경기연구원의 2차 재난기본소득 경제적 효과 분석(2021)과 경기도 거래 데이터는 소비 견인 효과를 확인했다. "실패 확정"이 아니라 초기 단면과 확대 이후 데이터의 충돌로 읽어야 정확하다.',
            },
        ],
        'korean_context': [
            {
                'context': '부동산·건설 이권은 한국 현대사에서 정치자금과 유착된 가장 고질적 부패 카르텔',
                'implication': '계곡 평상 철거·원가 공개는 일상 속 기득권 불로소득을 직접 파괴하는 카타르시스 — 거창한 거시담론이 아닌 생활밀착 공정',
            },
        ],
    },
    'peopleFirst': {
        'argument_chains': [
            {
                'policy_domain': '골든타임 재정 투입',
                'logic': '거시 충격 → 정부 긴축 → 저소득층·소상공인 직격 → 양극화·생태계 붕괴',
                'connection': '위기일수록 신속한 추경 + 과감한 재정 = 민생 방어적 투자',
            },
            {
                'policy_domain': '직접 지원 vs 일률 감면',
                'logic': '80조 조세감면·유류세 인하 = 일률적, 양극화 미제어, 체감도 극저',
                'connection': '취약계층 타겟 + 지역화폐 지급 → 민생구제 + 골목상권 이중 효과',
            },
            {
                'policy_domain': '재정정상화 뒤 복지확장',
                'logic': '모라토리엄 선언(2010) → 비공식 부채 7,285억(판교특별회계 전입금 5,400억 + 예산 미편성 의무금 1,885억) 구조조정 → 재정 정상화 뒤 보편복지 전개',
                'connection': '복지 확대와 재정 건전성은 대립이 아니라 우선순위 재배치. "빚을 갚으면서도 복지를 늘린다"는 모델',
            },
            {
                'policy_domain': '정치적 봉쇄 ≠ 재정 불가능',
                'logic': '의료원 건립비 56.8억 삭감, 무상교복 29억 삭감, 청년배당 폐지조례안 발의 — 재정여력이 아닌 보수 다수 시의회의 이념적 저지',
                'connection': '복지 실현의 장벽은 재정 불가능이 아니라 정치적 봉쇄라는 진단이 민생 우선 정치의 전제',
            },
        ],
        'empirical_evidence': [
            {
                'claim': '성남시 3대 무상복지: 청년배당 연 100만 원(지역화폐), 무상교복(중학교 신입생 전원), 공공산후조리비 50만 원',
                'source': '성남시, 2016',
            },
            {
                'claim': '경기도 재난기본소득: 도민 전원 1인당 10만 원 지역화폐, 중앙정부보다 선제 집행 → 전국 재난지원금 마중물',
                'source': '경기도, 2020',
            },
            {
                'claim': '경기도 생활임금 12,152원 확정 — 국가 최저임금 10,030원 대비 121.2%',
                'source': '경기도, 2025',
            },
            {
                'claim': '성남시 3대 무상복지 재원은 모라토리엄 극복 과정의 예산 구조조정으로 자력 마련한 95억 원 — 빚이 아닌 절약금',
                'source': '성남시 재정 분석',
            },
            {
                'claim': '성남시 채무 2015년 1,184억 → 2017년 결산 198.8억 → 2018년 1월 일반회계 190억 전액 상환·사실상 채무 제로 선언. 재정자립도 62.09%(유사 지자체 평균 50.84%)',
                'source': '성남시 재정공시·뉴시스, 2015-2018',
            },
            {
                'claim': '성남 무상급식 2010년 시비 260.9억 투입 67개 초등 6만4,500명 + 중학교 단계 확대. 2017년 205개교 8만4천여명 235억 + 친환경 우수농산물 47억 127개교',
                'source': '성남시·연합뉴스, 2010·2017',
            },
            {
                'claim': '경기도 공공버스 2021년 220개 노선 2,069대로 준공영제 확대 — 이동권·노동권·적자노선 유지를 공공이 떠받치는 기본서비스',
                'source': '경기도 공공버스 자료, 2021',
            },
        ],
        'international_precedents': [
            {
                'country': '미국',
                'policy': '2008 오바마 부족한 부양책 vs 2020 코로나 Stimulus Checks 직접 투입',
                'outcome': '2008년 고용없는 성장 늪 vs 2020년 V자 반등 — 골든타임 직접 지원의 거시경제적 실증',
            },
        ],
        'counter_rebuttals': [
            {
                'criticism': '무상 포퓰리즘이다 + 박근혜 정부 지방교부세 감액 페널티',
                'rebuttal': '모라토리엄 극복하며 자력 마련한 95억을 시민에게 돌려주는 것이 어떻게 포퓰리즘인가. "어머니(성남시)가 아들에게 용돈 만 원을 주는데, 동네 깡패(정부)가 오천 원을 빼앗아 가는 격." 헌재 권한쟁의 결과를 기다리며 민생 고통을 방치할 수 없어 예산 절반이라도 우선 집행.',
            },
            {
                'criticism': '직접 현금성 지원은 비효율적 산포다',
                'rebuttal': '일률적 조세감면(80조)은 양극화를 제어하지 못하고 체감도도 극저. 취약계층 타겟 + 지역화폐 지급이 민생구제와 골목상권 매출 증대의 이중 효과.',
            },
            {
                'criticism': '복지 확대는 지방재정을 파탄낸다',
                'rebuttal': '성남시는 보편복지 확대 국면에도 채무를 2015년 1,184억 → 2017년 198.8억 → 2018년 채무 제로까지 연속 감축했다. 재정자립도 62.09%는 유사 지자체 평균 50.84%보다 높게 유지됐다. 실증은 "복지 = 재정 파탄" 통념과 반대 방향이다.',
            },
            {
                'criticism': '성남 복지 실험은 실현 불가능한 공약이었다',
                'rebuttal': '불가능이 아니라 봉쇄였다. 의료원 건립비 102.8억 중 56.8억 삭감, 무상교복 29억 전액 삭감, 청년배당 폐지조례안 발의 — 모두 재정여력 문제가 아닌 보수 다수 시의회의 이념적 저지다. 주민발의 의료원은 시민 요구가 시장보다 먼저 있었고, 막은 건 대의기구였다는 점이 사실관계다.',
            },
        ],
        'korean_context': [
            {
                'context': '지방정부가 중앙 권력과 헌법적 권한을 다투며 민생 어젠다를 주도한 사례',
                'implication': '전통적 상명하달 행정 구조에서 지방자치가 민생을 위해 독자적 복지 행보를 개척한 한국 정치사의 변곡점',
            },
            {
                'context': '성남 3대 복지(청년배당·무상교복·공공산후조리 지원)를 둘러싼 헌재 권한쟁의 3건(2015-2018)은 2018년 5월 성남시 자진 취하로 본안 판단 없이 종결. 지방분권 확대 방향 전환이 이유로 제시됨',
                'implication': '재임기 내 확정 패소가 아니라는 사실관계를 정확히 적어야 "불법 복지" 비판에 대한 재반론이 가능. 갈등의 의의는 승패보다 지방복지 실험의 제도 경계 논쟁을 전국 의제로 만든 프레임 형성',
            },
        ],
    },
    'basicIncome': {
        'argument_chains': [
            {
                'policy_domain': '거시경제 패러다임',
                'logic': 'AI·로봇 → 노동 종말 가속 → 다수 소득 급감 → 구매력 상실 → 과잉생산 구조적 침체',
                'connection': '기본소득은 복지가 아닌 거시 경제 정책 — 소비 역량 지속 강화가 자본주의 생태계 붕괴를 막는 유일한 해법',
            },
            {
                'policy_domain': '지역화폐 결합 모델',
                'logic': '현금 → 저축 또는 대기업 유출 vs 지역화폐 → 골목상권 강제 순환',
                'connection': '기본소득 + 지역화폐 = 모세혈관 경제 부양, 낙수효과 대신 분수효과(Trickle-up)',
            },
            {
                'policy_domain': '노동의 재정의',
                'logic': '생존 기본선 보장 → 노동이 생존 고통에서 자아실현으로 승화',
                'connection': '외부 위기에 상관없이 기본이 지켜지는 사회 = 진짜 대한민국',
            },
            {
                'policy_domain': '보편과 선별의 정책학습',
                'logic': '경기도 1·2차 재난기본소득 도민 전원 보편 → 3차는 중앙 긴급재난지원금 제외 상위 12% 보완형 설계',
                'connection': '"보편 vs 선별" 이분법이 아니라 초기 보편 + 후속 보정이라는 정책학습 모델. 속도·포용·재정을 회차별로 조정',
            },
        ],
        'empirical_evidence': [
            {
                'claim': '성남시 청년배당: 연 100만 원 지역화폐, "3년 만에 처음 과일을 사 먹었다" 증언, 동네 식당·전통시장 매출 증가',
                'source': '성남시, 2016',
            },
            {
                'claim': '경기도 청년기본소득 만족도: 1년차 80% → 7년차(2025) 94%',
                'source': '경기도 청년기본소득 만족도 조사, 2025',
            },
            {
                'claim': '독일 베를린 기본소득 실험(2021-2024): 수급자 90%가 주당 40시간 정상 근로 유지, 노동이탈 전혀 없음, 스트레스↓ 교육투자↑ 창업↑',
                'source': '독일경제연구소(DIW), 2024',
            },
            {
                'claim': '핀란드 기본소득 실험(2017-2018): 정부·사회제도 신뢰도 유의미 상승, 투표 참여율 증가 — 민주주의 역량 강화',
                'source': 'Kela, 2020',
            },
            {
                'claim': '신안군 햇빛연금: 재생에너지 이익 공유 월 ~20만 원, 향후 바람연금 포함 월 50-60만 원 → 지방소멸 방어',
                'source': '신안군, 2024',
            },
            {
                'claim': '경기도 2차 재난기본소득: 도민 1,399만 명 + 등록외국인·거소신고자 58만 명 포함, 온라인 안내 13개 언어. 도민 기준을 국적이 아닌 거주·생활기반으로 재정의',
                'source': '경기도, 2021',
            },
            {
                'claim': '경기도 3차 재난기본소득: 중앙 긴급재난지원금 제외 상위 12% 보완. 신청 대상 252만 명·지급 6,341억·신청률 81.7%',
                'source': '경기도, 2021',
            },
        ],
        'international_precedents': [
            {
                'country': '독일',
                'policy': '베를린 기본소득 3년 실험(Mein Grundeinkommen)',
                'outcome': '노동시간 감소·이탈 제로, 사회적 도약대(Social Launchpad) 효과 입증',
            },
            {
                'country': '핀란드',
                'policy': '2년간 실업자 대상 무조건적 소득 지급',
                'outcome': '사회제도 신뢰도↑, 민주주의 참여↑ — 사회적 통합 효과',
            },
        ],
        'counter_rebuttals': [
            {
                'criticism': '천문학적 재정 파탄, 전 국민 백수화 도덕적 해이',
                'rebuttal': '독일·핀란드 실증 데이터가 허구임을 증명 — 90%가 정상 근로 유지. 인간은 불안 제거 시 더 창의적이고 높은 가치를 추구한다.',
            },
            {
                'criticism': '부유층에게까지 나눠주는 비효율, 선별 복지가 합리적',
                'rebuttal': '선별복지는 세금만 내고 혜택 못 받는 계층의 조세 저항을 필연적으로 유발. 100% 혜택 공유하는 보편적 기본소득만이 증세에 대한 사회적 합의를 이끌어낼 유일한 정치적 기제.',
            },
            {
                'criticism': '재원 조달이 불가능하다',
                'rebuttal': '단계적 접근: 1년 1-4회씩 서서히 확대, 기존 조세감면 축소 + 예산 구조조정으로 시작 → 국민적 공감대 후 탄소세·국토보유세 등 목적세 신설로 지속가능성 확보.',
            },
            {
                'criticism': '보편지급은 비효율, 위기에는 선별이 합리적이다',
                'rebuttal': '경기도의 궤적은 "무조건 보편"이 아니라 보편을 기본값으로 두고 필요시 보정하는 실용주의였다. 1·2차 도민 전원 보편 + 3차 중앙 선별 제외 상위 12% 보완. 위기 초기는 속도와 포용이 선별 효율보다 우위이며, 필요한 보정은 후속 회차에서 설계로 해결할 수 있다. 이분법이 아니라 정책학습의 문제다.',
            },
        ],
        'korean_context': [
            {
                'context': '재벌 대기업 중심 낙수효과(Trickle-down)가 완전히 수명을 다한 한국 경제',
                'implication': '지역화폐형 기본소득 = 밑바닥 골목상권부터 돈을 돌게 만드는 상향식 분수효과(Trickle-up)의 한국형 실험',
            },
            {
                'context': '이재명 직접 번역 참여: 다니엘 라벤토스 «기본소득이란 무엇인가»',
                'implication': '빈곤 해소는 시혜가 아니라 시민 자유의 실현을 위한 절대적 조건 — 공화주의적 기본소득론의 한국 도입',
            },
        ],
    },
}


# ============================================================================
# 프롬프트 빌더 — 정치 철학 주입
# ============================================================================

def _xml_esc(text: str) -> str:
    """XML 특수문자 이스케이프."""
    s = str(text or "")
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    return s


def build_leadership_philosophy_xml() -> str:
    """프로젝트 핵심 정치 철학을 XML 블록으로 반환.

    모든 사용자에게 상시 주입된다.
    주입 대상: CORE_LEADERSHIP_VALUES, corePrinciples, policyApproach,
               reconciliation, constructiveCriticism.principles, coreKeywords
    제외 대상: communicationStyle, frequentPhrases, peopleFirstTone, PRAGMATIC_EXPERIENCE
    """
    parts: list[str] = [
        '<political_philosophy priority="baseline">',
        '  <premise>'
        '이 글은 아래 정치 철학을 기본 전제로 삼는다. '
        '글의 논조·정책 방향·가치 판단이 이 철학과 충돌해서는 안 된다. '
        '이 전제는 화자의 소속 정당이나 개인 성향과 무관하게 적용된다.'
        '</premise>',
    ]

    # ── 5대 핵심 가치 ──
    parts.append('  <core_values>')
    for key, val in CORE_LEADERSHIP_VALUES.items():
        lines = [f'    <value id="{key}">']
        lines.append(f'      <vision>{_xml_esc(val["vision"])}</vision>')
        lines.append(f'      <philosophy>{_xml_esc(val["philosophy"])}</philosophy>')
        principles_str = " / ".join(val["principles"])
        lines.append(f'      <principles>{_xml_esc(principles_str)}</principles>')
        lines.append('    </value>')
        parts.append("\n".join(lines))
    parts.append('  </core_values>')

    # ── 리더십 원칙 (corePrinciples) ──
    parts.append('  <leadership_principles>')
    for key, val in LEADERSHIP_PHILOSOPHY['coreprinciples'].items():
        parts.append(
            f'    <principle id="{key}">'
            f'{_xml_esc(val["principle"])} — {_xml_esc(val["meaning"])}'
            f'</principle>'
        )
    parts.append('  </leadership_principles>')

    # ── 정책 접근법 (policyApproach) ──
    parts.append('  <policy_approach>')
    for key, val in LEADERSHIP_PHILOSOPHY['policyApproach'].items():
        chars = " / ".join(val["characteristics"])
        parts.append(
            f'    <approach id="{key}">'
            f'{_xml_esc(val["style"])}: {_xml_esc(chars)}'
            f'</approach>'
        )
    parts.append('  </policy_approach>')

    # ── 균형 접근 (reconciliation) ──
    parts.append('  <balanced_approach>')
    for key, val in BALANCED_APPROACH['reconciliation'].items():
        parts.append(
            f'    <balance id="{key}">'
            f'{_xml_esc(val["approach"])} — {_xml_esc(val["method"])}'
            f'</balance>'
        )
    parts.append('  </balanced_approach>')

    # ── 건설적 비판 원칙 (constructiveCriticism.principles만) ──
    parts.append('  <constructive_criticism>')
    for p in BALANCED_APPROACH['constructiveCriticism']['principles']:
        parts.append(f'    <principle>{_xml_esc(p)}</principle>')
    parts.append('  </constructive_criticism>')

    # ── 핵심 키워드 (coreKeywords) ──
    kw = PREFERRED_EXPRESSIONS['coreKeywords']
    all_keywords = kw['values'] + kw['policies'] + kw['philosophy']
    parts.append(f'  <core_keywords>{_xml_esc(", ".join(all_keywords))}</core_keywords>')

    # ── 사일런트 정치 가드: 기본 입장 설정 ──
    parts.append('  <baseline_stance>')
    parts.append(
        '    현 정부(국민주권정부)의 정책 방향은 이 철학의 실현으로 간주한다. '
        '글의 논조가 현 정부의 핵심 정책 기조와 정면 충돌하는 방향으로 '
        '전개되어서는 안 된다. 비판적 논의가 필요한 경우, '
        '건설적 비판 원칙(상대 논리 인정 → 현실적 한계 → 대안 제시)을 따르되 '
        '기본 철학의 가치 체계 안에서 전개할 것.'
    )
    parts.append('  </baseline_stance>')

    parts.append('</political_philosophy>')
    return "\n".join(parts)


_MATERIAL_STOPWORDS = {
    "정책",
    "비전",
    "방안",
    "구체",
    "추진",
    "활성화",
    "필요",
    "경제",
    "사회",
    "시민",
    "주민",
    "국민",
    "의원",
    "후보",
}

_LOCAL_CURRENCY_BRAND_TERMS = tuple(
    name
    for name, region in LOCAL_CURRENCY_ENTRIES
    if region not in {"공통", "운영대행사", "한국조폐공사"}
)

_TOPIC_SIGNAL_TERMS = {
    "local_currency": (
        "지역화폐",
        "지역사랑상품권",
        "이음카드",
        "캐시백",
        "골목상권",
        "소상공인",
        "자영업",
        "전통시장",
        "지역순환",
        "역외유출",
        *_LOCAL_CURRENCY_BRAND_TERMS,
    ),
    "basic_income": (
        "기본소득",
        "기본사회",
        "청년배당",
        "청년기본소득",
        "기본서비스",
    ),
}
_COMPACT_TOPIC_SIGNAL_TERMS = {
    _compact_term
    for _terms in _TOPIC_SIGNAL_TERMS.values()
    for _compact_term in (re.sub(r"\s+", "", _term.lower()) for _term in _terms)
}


def _material_text(item: Any) -> str:
    if isinstance(item, dict):
        return " ".join(str(value or "") for value in item.values())
    return str(item or "")


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").lower())


def _query_terms(*, topic: str = "", instructions: str = "", keywords: Iterable[str] | None = None) -> set[str]:
    raw = " ".join(
        part
        for part in [
            str(topic or ""),
            str(instructions or ""),
            " ".join(str(k or "") for k in (keywords or [])),
        ]
        if part
    )
    if not raw.strip():
        return set()

    compact_raw = _compact(raw)
    terms = {
        term
        for term in re.findall(r"[가-힣A-Za-z0-9]+", raw)
        if len(term) >= 2 and term not in _MATERIAL_STOPWORDS
    }

    for signal_terms in _TOPIC_SIGNAL_TERMS.values():
        if any(_compact(signal) in compact_raw for signal in signal_terms):
            terms.update(signal_terms)

    return {_compact(term) for term in terms if _compact(term)}


def _score_material(item: Any, terms: set[str]) -> int:
    if not terms:
        return 0
    haystack = _compact(_material_text(item))
    score = 0
    for term in terms:
        if term and term in haystack:
            score += 3 if term in _COMPACT_TOPIC_SIGNAL_TERMS else 1
    return score


def _select_material(items: list[dict], terms: set[str]) -> dict:
    if not items:
        return {}
    if not terms:
        return items[0]
    ranked = sorted(
        ((-_score_material(item, terms), index, item) for index, item in enumerate(items)),
        key=lambda row: (row[0], row[1]),
    )
    best_score = -ranked[0][0]
    return ranked[0][2] if best_score > 0 else items[0]


def _select_material_with_score(items: list[dict], terms: set[str]) -> tuple[dict, int]:
    selected = _select_material(items, terms)
    return selected, _score_material(selected, terms)


def _build_evidence_brief(*, topic: str = "", instructions: str = "", keywords: Iterable[str] | None = None) -> str:
    terms = _query_terms(topic=topic, instructions=instructions, keywords=keywords)
    if not terms:
        return ""

    lines: list[str] = []
    for value_id, data in ARGUMENT_LAYER.items():
        chain, chain_score = _select_material_with_score(data.get("argument_chains") or [{}], terms)
        evidence, evidence_score = _select_material_with_score(data.get("empirical_evidence") or [{}], terms)
        if max(chain_score, evidence_score) <= 0:
            continue
        core = CORE_LEADERSHIP_VALUES.get(value_id, {})
        label = core.get("vision", value_id)
        lines.append(
            f"{label}: {chain.get('policy_domain', '')} — {chain.get('logic', '')} → "
            f"{chain.get('connection', '')}. 활용 가능한 근거: {evidence.get('claim', '')} "
            f"({evidence.get('source', '')})."
        )

    return "\n".join(lines[:3])


def _build_higher_principle_brief(*, topic: str = "", instructions: str = "", keywords: Iterable[str] | None = None) -> str:
    terms = _query_terms(topic=topic, instructions=instructions, keywords=keywords)
    lines: list[str] = []
    for value_id, data in ARGUMENT_LAYER.items():
        core = CORE_LEADERSHIP_VALUES.get(value_id, {})
        chain = _select_material(data.get("argument_chains") or [{}], terms)
        evidence = _select_material(data.get("empirical_evidence") or [{}], terms)
        korean_context = _select_material(data.get("korean_context") or [{}], terms)
        label = core.get("vision", value_id)
        lines.append(
            f"{label}: {chain.get('logic', '')} → {chain.get('connection', '')}. "
            f"근거는 {evidence.get('claim', '')} ({evidence.get('source', '')})이고, "
            f"한국 맥락은 {korean_context.get('context', '')} → {korean_context.get('implication', '')}."
        )
    return "\n".join(lines)


def _build_counterargument_rebuttal_brief(*, topic: str = "", instructions: str = "", keywords: Iterable[str] | None = None) -> str:
    terms = _query_terms(topic=topic, instructions=instructions, keywords=keywords)
    lines: list[str] = []
    for value_id, data in ARGUMENT_LAYER.items():
        core = CORE_LEADERSHIP_VALUES.get(value_id, {})
        rebuttal = _select_material(data.get("counter_rebuttals") or [{}], terms)
        label = core.get("vision", value_id)
        criticism = str(rebuttal.get("criticism", "")).strip()
        rebut = str(rebuttal.get("rebuttal", "")).strip()
        if criticism and rebut:
            lines.append(f"{label}: '{criticism}'라는 반론에는 '{rebut}'라는 재반론으로 답하십시오.")
    return "\n".join(lines)


def build_argument_role_material_block(
    role: str,
    *,
    topic: str = "",
    instructions: str = "",
    keywords: Iterable[str] | None = None,
) -> str:
    """역할 섹션 바로 아래에 붙일 자연어 소재 블록."""
    if role == "evidence":
        summary = _build_evidence_brief(
            topic=topic,
            instructions=instructions,
            keywords=keywords,
        )
    elif role == "higher_principle":
        summary = _build_higher_principle_brief(
            topic=topic,
            instructions=instructions,
            keywords=keywords,
        )
    elif role == "counterargument_rebuttal":
        summary = _build_counterargument_rebuttal_brief(
            topic=topic,
            instructions=instructions,
            keywords=keywords,
        )
    else:
        return ""

    if not summary.strip():
        return ""

    lines = [f'    <role_material role="{role}" priority="critical">']
    if role == "evidence":
        lines.append('      <instruction>아래 소재 중 이 글과 가장 맞는 1개 이상을 골라, 근거 문단에서 실행 방식·인과관계·사례로 직접 풀어 쓰십시오.</instruction>')
    elif role == "higher_principle":
        lines.append('      <instruction>아래 소재 중 이 글과 가장 맞는 1개를 골라, 가치 선언과 구체 근거와 한국 맥락을 한 섹션 안에서 함께 쓰십시오.</instruction>')
    else:
        lines.append('      <instruction>아래 소재 중 이 글과 가장 맞는 반론-재반론 1개를 골라, 반론을 인정한 뒤 사실·사례로 재반론하십시오.</instruction>')
    for line in summary.splitlines():
        if line.strip():
            lines.append(f'      <item>{_xml_esc(line.strip())}</item>')
    lines.append('    </role_material>')
    return "\n".join(lines)
