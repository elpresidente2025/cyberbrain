# functions/python/agents/common/leadership.py
# 리더십 철학/핵심가치/선호표현 — leadership.js 완전 이식
# ※ 범용성 원칙의 명시적 예외로 사용자가 승인한 파일
#
# 이 파일은 프로젝트의 영혼이다.
# 모든 사용자가 이 정치 철학을 기본 프레임으로 갖고 글을 쓴다.
# communicationStyle, frequentPhrases, peopleFirstTone, PRAGMATIC_EXPERIENCE는
# 커뮤니케이션 방식이므로 프롬프트에 주입하지 않는다 (각자의 fingerprint 영역).

from __future__ import annotations

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
            '공공산후조리원 운영',
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
            '재난기본소득 전국민 지급',
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
