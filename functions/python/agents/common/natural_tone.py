
# functions/python/agents/common/natural_tone.py

BLACKLIST_PATTERNS = {
    'common_cliches': [
        '결론적으로', '요약하자면', '정리하면', '종합하면',
        '전반적으로 볼 때', '전체적으로 살펴보면', '마지막으로 정리하자면'
    ],
    'excessive_conjunctions': [
        '또한', '한편', '더 나아가', '이러한 점에서', '이와 관련하여',
        '이와 함께', '그럼에도 불구하고', '따라서', '이에 따라', '결과적으로'
    ],
    'euphemisms': [
        '인 것 같습니다', '로 보입니다', '라고 여겨집니다',
        '라고 볼 수 있습니다', '라고 할 수 있습니다',
        '일 수 있습니다', '할 수 있습니다'
    ],
    'abstract_must': [
        '할 필요가 있습니다', '해야 할 것입니다', '하는 것이 중요합니다',
        '하는 것이 바람직합니다', '할 것으로 기대됩니다', '필요할 것으로 생각됩니다'
    ],
    'verb_repetition': [
        '던지면서', '던지며',
        '이끌어내며', '이끌어가며'
    ]
}

def build_natural_tone_prompt(options={}):
    platform = options.get('platform', 'general')
    severity = options.get('severity', 'standard')
    
    is_strict = severity == 'strict' or platform in ['title', 'sns']

    cliches = ", ".join(BLACKLIST_PATTERNS['common_cliches'][:4])
    conjunctions = ", ".join(['또한', '한편', '더 나아가', '이러한 점에서'])
    euphemisms = "~것 같습니다, ~로 보입니다"
    musts = "~할 필요가 있습니다"
    
    strict_extras = ""
    if is_strict:
        strict_extras = """
    <category name="격식체 잔여" action="간결한 구어체로 변환">따라서, 결과적으로, ~라고 할 수 있습니다</category>"""

    return f"""
<natural_tone_rules>
  <banned_expressions>
    <category name="결론 클리셰" action="접속어 없이 핵심만 제시">{cliches} 등</category>
    <category name="과도한 접속어" action="조사와 어순으로 자연스럽게 연결">{conjunctions}</category>
    <category name="완곡 표현" action="단정형 사용: ~입니다, ~합니다">{euphemisms}</category>
    <category name="당위 남발" action="구체적 약속: ~하겠습니다, 추진합니다">{musts}</category>{strict_extras}
    <category name="동사/구문 반복" severity="critical" action="동의어 교체 필수">
      같은 동사를 원고 전체에서 3회 이상 사용 금지 (최대 2회)
      <example>
        <bad>"던지면서" 6회 반복</bad>
        <alternatives>제시하며, 약속하며, 열며, 보여드리며, 선보이며</alternatives>
      </example>
      <example>
        <bad>"이끌어내며" 반복</bad>
        <alternatives>달성하며, 만들어내며, 실현하며</alternatives>
      </example>
    </category>
    <category name="슬로건/캐치프레이즈 반복" severity="critical" action="결론부 1회만 사용">
      같은 비전 문구, 벤치마크 비유를 여러 섹션에서 반복 금지
      <example>
        <bad>도입부+본론+결론에서 "청년이 돌아오는 부산" 3회 반복</bad>
        <good>도입부: "청년 일자리가 풍부한 부산" / 결론부: "청년이 돌아오는 부산" (1회만)</good>
      </example>
    </category>
  </banned_expressions>
  <preferred_style>
    <rule>서론 접속어 없이 바로 본론 시작</rule>
    <rule>단정형 종결: ~입니다, ~합니다</rule>
    <rule>약속형 공약: ~하겠습니다, 추진합니다 (~할 필요가 있습니다 금지)</rule>
  </preferred_style>
</natural_tone_rules>
"""
