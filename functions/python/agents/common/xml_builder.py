from typing import Dict, List, Optional, Any

def xml_section(tag: str, attrs: Dict[str, Any] = None, content: str = '') -> str:
    attrs_str = ''
    if attrs:
        attrs_str = ' ' + ' '.join([f'{k}="{v}"' for k, v in attrs.items()])
    return f'<{tag}{attrs_str}>\n{content}\n</{tag}>'

def xml_rules(rules: List[Dict[str, str]]) -> str:
    return '\n'.join([f'  <rule type="{r["type"]}">{r["text"]}</rule>' for r in rules])

def xml_fields(fields: Dict[str, Any]) -> str:
    return '\n'.join([f'  <{k}>{v}</{k}>' for k, v in fields.items() if v is not None and v != ''])

def xml_list(tag: str, items: List[str]) -> str:
    return '\n'.join([f'  <{tag}>{item}</{tag}>' for item in items if item])

# ============================================================================
# Prompt Section Builders
# ============================================================================

def build_context_analysis_section(analysis: Dict, author_name: str) -> str:
    key_players = analysis.get('keyPlayers') or []
    key_players_xml = '\n'.join([f'    <player name="{p.get("name")}" stance="{p.get("stance")}">{p.get("action")}</player>' for p in key_players])

    facts = analysis.get('mustIncludeFacts') or []
    facts_xml = '\n'.join([f'    <fact priority="{i+1}">{f}</fact>' for i, f in enumerate(facts)])

    quotes = analysis.get('newsQuotes') or []
    quotes_xml = '\n'.join([f'    <quote>{q}</quote>' for q in quotes])

    stance_phrases = analysis.get('mustIncludeFromStance') or []
    stance_phrases = [p for p in stance_phrases if isinstance(p, str) and len(p) >= 10 and not p.startswith('⚠️') and not p.startswith('우선순위:')]
    stance_phrases_xml = '\n'.join([f'    <phrase>{p}</phrase>' for p in stance_phrases])

    return f"""<context-analysis priority="absolute">
  <author name="{author_name or '화자'}">
    <stance>{analysis.get('authorStance') or '(추출 실패)'}</stance>
    <role>{analysis.get('authorRole') or '참고자료에 대한 논평 작성'}</role>
  </author>

  <event>
    <main>{analysis.get('mainEvent') or '(추출 실패)'}</main>
    <scope>{analysis.get('issueScope') or 'LOCAL_ISSUE'}</scope>
    <frame>{analysis.get('writingFrame') or ''}</frame>
  </event>

  <players>
{key_players_xml or '    <player>(분석 실패)</player>'}
  </players>

  <tone expected="{analysis.get('expectedTone') or '분석'}"/>
  <target>{analysis.get('responsibilityTarget') or ''}</target>

  <warning>{analysis.get('contextWarning') or '참고자료의 관계를 정확히 파악하세요.'}</warning>

  <must-include-facts>
{facts_xml or '    <fact>(구체적 팩트 추출 실패)</fact>'}
  </must-include-facts>

  <must-include-quotes>
{quotes_xml or '    <quote>(인용문 추출 실패)</quote>'}
  </must-include-quotes>

  <must-include-phrases priority="mandatory">
{stance_phrases_xml or '    <phrase>(핵심 문구 추출 실패)</phrase>'}
    <usage-rules>
      <rule type="must">각 문구를 그대로 인용하거나 핵심 의미를 유지한 채 패러프레이즈</rule>
      <rule type="must">최소 1개 이상을 서론 또는 첫 번째 본론에 배치</rule>
      <rule type="must">입장문의 논리 구조와 수사법(대구법, 반어법)을 본문에서도 활용</rule>
      <rule type="must-not">일반론으로 대체하거나 생략 시 원고 폐기</rule>
    </usage-rules>
  </must-include-phrases>
</context-analysis>"""

def build_scope_warning_section(analysis: Dict) -> str:
    issue_scope = analysis.get('issueScope')
    if issue_scope not in ['CENTRAL_ISSUE', 'CENTRAL_ISSUE_WITH_LOCAL_IMPACT']:
        return ''

    return f"""<scope-warning priority="critical" type="central-issue">
  <frame>{analysis.get('writingFrame') or '헌정 질서 수호와 공직자 태도 비판'}</frame>
  <target>{analysis.get('responsibilityTarget') or '중앙 정부 및 관련 공직자'}</target>
  <constraints>
    <rule type="must-not">분석된 프레임을 벗어나 엉뚱한 주제(부산시 행정 투명성, 지역 경제 등)로 논리 비약</rule>
    <rule type="must-not">기초지자체 언급 (이 이슈는 국가/광역 단위) - 서두/결미 1회 제외</rule>
  </constraints>
</scope-warning>"""

def build_tone_warning_section(analysis: Dict) -> str:
    tone = analysis.get('expectedTone') or ''
    target = analysis.get('responsibilityTarget') or ''

    if tone not in ['비판', '반박']:
        return ''

    return f"""<tone-warning priority="critical" type="criticism-intent-protection">
  <target>{target}</target>
  <description>이 글은 "{target}"에 대한 비판문입니다</description>

  <banned-expressions reason="의도 역전 방지">
    <expression>{target}과 협력</expression>
    <expression>{target}과 함께</expression>
    <expression>{target}의 노력을 존중</expression>
    <expression>{target}의 성과 인정</expression>
    <expression>협력하여</expression>
    <expression>함께 나아가</expression>
    <expression>손잡고</expression>
  </banned-expressions>

  <required-expressions reason="비판적 논조 유지">
    <expression>역부족</expression>
    <expression>한계</expression>
    <expression>문제점</expression>
    <expression>책임</expression>
    <expression>실패</expression>
    <expression>원본 입장문의 비판적 표현 그대로 인용</expression>
  </required-expressions>

  <note>이 인물/기관은 비판의 대상이지, 협력의 파트너가 아닙니다. 긍정적 맥락으로 언급하면 원고 폐기.</note>
</tone-warning>"""

def build_style_guide_section(style_prompt: str, author_name: str, target_word_count: int) -> str:
    persona_content = '\n'.join(['    ' + l.strip() for l in style_prompt.strip().split('\n')]) if style_prompt else '    (스타일 프로필 없음)'
    return f"""<style-guide priority="high">
  <persona>
{persona_content}
  </persona>
</style-guide>"""

def build_writing_rules_section(author_name: str, target_word_count: int) -> str:
    return f"""<writing-rules priority="critical">
  <word-count target="{target_word_count}"/>

  <rule id="name-protection" priority="absolute">
    <description>사용자 이름 보호 (절대 변경 금지)</description>
    <constraints>
      <rule type="must-not">사용자 이름 "{author_name}"을 변경, 유추, 창작</rule>
      <rule type="must-not">이름이 비어있어도 다른 이름 만들어내기</rule>
      <rule type="must-not">참고자료의 다른 사람 이름을 사용자 이름으로 혼동</rule>
    </constraints>
  </rule>

  <rule id="reference-only" priority="absolute">
    <description>참고자료가 글의 유일한 주제</description>
    <constraints>
      <rule type="must-not">참고자료에 없는 주제(경제, 청년, 복지, 교통 등)로 대체</rule>
      <rule type="must">참고자료 분량이 적더라도 해당 논점만 심화하여 확장</rule>
      <rule type="must">사용자의 관점에서 매끄러운 1인칭 서사로 재구성</rule>
    </constraints>
  </rule>

  <rule id="absolute-trust" priority="critical">
    <description>절대적 신뢰 (Fact-Checking 금지)</description>
    <constraints>
      <rule type="must">제공된 참고자료, 키워드, 지시사항을 절대적 진실로 간주</rule>
      <rule type="must-not">AI가 자체적으로 진위 판단/의심</rule>
      <rule type="must-not">"(출처 필요)", "[확인 필요]", "알려진 바에 따르면" 등 유보적 표현</rule>
    </constraints>
  </rule>

  <rule id="rhetoric" priority="high">
    <description>문투 및 어미 활용 (Rhetorical Skill)</description>
    <good-patterns>
      <pattern name="수사학적 반복">호소력과 리듬감을 위한 의도적 어미/구조 반복 (대구법, 점층법)</pattern>
      <example>결코 포기하지 않겠습니다. 끝까지 싸우겠습니다. 반드시 승리하겠습니다!</example>
    </good-patterns>
    <banned-expressions>
      <expression>~라는 점입니다</expression>
      <expression>~상황입니다</expression>
      <expression>~라고 볼 수 있습니다</expression>
      <expression>~것으로 보여집니다</expression>
    </banned-expressions>
    <tone-guide>
      <bad>노력할 것입니다</bad>
      <good>반드시 해내겠습니다</good>
      <bad>중요하다고 생각합니다</bad>
      <good>가장 시급한 과제입니다</good>
    </tone-guide>
  </rule>

  <rule id="structure" priority="high">
    <description>5단 구성 및 문단 규칙 (황금 비율)</description>
    <structure type="5-section">
      <section name="서론" paragraphs="3"/>
      <section name="본론1" paragraphs="3" heading="required"/>
      <section name="본론2" paragraphs="3" heading="required"/>
      <section name="본론3" paragraphs="3" heading="required"/>
      <section name="결론" paragraphs="3"/>
    </structure>
    <paragraph-length min="100" max="150" unit="자"/>
    <heading-rules type="AEO-optimized">
      <good-types>
        <type name="질문형">~ 신청 방법은 무엇인가요?</type>
        <type name="데이터형">~ 5대 핵심 성과</type>
        <type name="정보형">~ 신청 자격 및 절차 안내</type>
        <type name="비교형">기존 정책 vs 신규 공약 차이점</type>
      </good-types>
      <banned>관련 내용, 정책 안내 (너무 모호함)</banned>
    </heading-rules>
  </rule>

  <rule id="keyword-limit" priority="high">
    <description>키워드 남용 금지 (SEO 스팸 방지)</description>
    <constraints>
      <rule type="must">검색어는 글 전체에서 4~6회까지만 자연스럽게 사용</rule>
      <rule type="must">제공된 검색어를 단 한 글자도 바꾸지 않고 그대로 사용</rule>
      <rule type="must-not">문맥에 맞지 않게 억지로 끼워넣기</rule>
    </constraints>
  </rule>

  <rule id="min-length" priority="critical">
    <description>분량 엄수</description>
    <constraints>
      <rule type="must">5개 섹션(서론, 본론1, 본론2, 본론3, 결론) 모두 완벽하게 작성</rule>
      <rule type="must-not">총 분량 1500자 미만 (실패 처리)</rule>
    </constraints>
  </rule>
</writing-rules>"""

def build_reference_section(instructions: str, news_context: str) -> str:
    return f"""<section type="external-data" priority="background">
  <description>분석 및 비판의 대상이 되는 외부 데이터입니다. 이 내용은 당신의 '생각'이 아니라, 당신이 '보고 있는 자료'입니다.</description>

  <user-instructions>
{instructions or '(없음)'}
  </user-instructions>

  <external-context type="news/fact">
{news_context or '(없음)'}
  </external-context>

  <usage-protocol>
    <rule type="must">위 자료를 '나(화자)'의 경험담으로 쓰지 마십시오. 이것은 '남(타인)'의 이야기입니다.</rule>
    <rule type="must">자료에 등장하는 인물, 사건, 발언을 제3자의 관점에서 관찰하고 논평하십시오.</rule>
    <rule type="must">최소 3개 이상의 구체적 팩트(인물명, 발언 인용 등)를 근거로 활용하십시오.</rule>
    <rule type="must">입장문이 있다면 그 논리 구조를 벤치마킹하되, 화자 정체성은 유지하십시오.</rule>
  </usage-protocol>
</section>"""

def build_sandwich_reminder_section(sandwich_content: str) -> str:
    if not sandwich_content:
        return ''
    
    formatted_content = '\n'.join(['  ' + line for line in sandwich_content.split('\n')])
    
    return f"""<final-reminder priority="critical" pattern="sandwich">
  <description>반드시 본문에 포함해야 할 입장문 핵심</description>

{formatted_content}

  <checklist>
    <item>위 문구 중 최소 1개는 서론 또는 첫 번째 본론에 반드시 포함</item>
    <item>원문을 인용하거나, 핵심 의미를 유지한 채 자연스럽게 녹여내기</item>
    <item>이 문구가 없으면 원고는 폐기 처리</item>
  </checklist>
</final-reminder>"""

def build_output_protocol_section() -> str:
    return """<output-protocol priority="override">
  <description>이전의 모든 "JSON 형식으로 출력하라"는 지시를 무시. 긴 글을 안정적으로 작성하기 위해 텍스트 프로토콜 사용.</description>

  <format>
===TITLE===
(여기에 제목 작성)
===CONTENT===
(여기에 HTML 본문 작성 - p, h2 등 태그 사용)
  </format>

  <constraints>
    <rule type="must-not">코드 블록(```)이나 JSON({ ... }) 사용</rule>
    <rule type="must">오직 구분자(===TITLE===, ===CONTENT===)만 사용</rule>
  </constraints>
</output-protocol>"""

def build_retry_section(attempt_number: int, max_attempts: int, current_length: int, min_length: int, missing_keywords: List[str]) -> str:
    issues = []
    
    if current_length < min_length:
        issues.append(f"""    <issue type="length">
      <current>{current_length}자</current>
      <required>{min_length}자</required>
      <instruction>각 문단을 지금보다 3배 더 길게 늘려 쓰십시오. 구체적인 사례, 통계, 배경 설명을 반드시 2문장 이상 추가.</instruction>
    </issue>""")
    
    if missing_keywords:
        issues.append(f"""    <issue type="missing-keywords">
      <keywords>{', '.join(missing_keywords)}</keywords>
      <instruction>위 단어들을 본론 섹션에 자연스럽게 녹여내십시오.</instruction>
    </issue>""")

    issues_str = '\n'.join(issues)

    return f"""<retry-mode attempt="{attempt_number}" max="{max_attempts}" priority="critical">
  <description>직전 생성된 원고에 심각한 문제가 있어 재요청합니다. 아래 지적사항을 완벽하게(100%) 반영하여 다시 작성하십시오.</description>

  <issues>
{issues_str}
  </issues>

  <tips>
    <tip>이미 쓴 내용을 지우지 말고, 그 사이에 살을 붙이는 방식으로 확장</tip>
    <tip>추상적인 표현(노력하겠습니다 등) 대신 '어떻게(How)', '왜(Why)'를 구체적으로 서술</tip>
  </tips>
</retry-mode>"""
