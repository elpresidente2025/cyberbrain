# functions/python/agents/common/seo.py

from .editorial import SEO_RULES

def calculate_min_insertions(keyword_count=1):
    """
    키워드별 적정 삽입 횟수 계산
    키워드 2개 기준: 각 3~4회, 총합 7~8회 (15문단 기준 약 2문단당 1회)
    """
    if keyword_count >= 2:
        return 3  # 각 3~4회, 총합 7~8회
    return 5  # 키워드 1개면 5~6회

def calculate_distribution(per_keyword):
    """
    키워드 배치 구간 계산 (15문단 기준, 2문단당 1개 꼴)
    """
    if per_keyword <= 3:
        return {'intro': 1, 'body': 1, 'conclusion': 1}
    return {
        'intro': 1,
        'body': max(1, per_keyword - 2),
        'conclusion': 1
    }

def build_seo_instruction(params):
    """
    SEO 최적화 지침 생성 (XML 형식)
    """
    keywords = params.get('keywords', [])
    target_word_count = params.get('targetWordCount') or SEO_RULES['wordCount']['target']

    min_len = SEO_RULES['wordCount']['min']
    max_len = SEO_RULES['wordCount']['max']

    kw_count = len(keywords) if keywords else 0
    min_insertions = calculate_min_insertions(kw_count)
    distribution = calculate_distribution(min_insertions)
    total_insertions = min_insertions * kw_count
    max_per_keyword = min_insertions + 1  # 3~4회 허용

    keyword_section = ''
    if keywords:
        keyword_items = '\n'.join([f'    <keyword text="{kw}" min_count="{min_insertions}" max_count="{max_per_keyword}"/>' for kw in keywords])
        first_kw = keywords[0]

        keyword_section = f"""
  <keywords>
{keyword_items}
    <total_target min="{total_insertions}" max="{total_insertions + kw_count}" note="키워드 {kw_count}개 × 각 {min_insertions}~{max_per_keyword}회 = 총 {total_insertions}~{total_insertions + kw_count}회"/>
    <distribution intro="{distribution['intro']}" body="{distribution['body']}" conclusion="{distribution['conclusion']}" note="15문단 기준 약 2문단당 1개 꼴로 배치"/>
    <insertion_method>
      <good position="주어">"{first_kw}은(는) 이번 행사에서..."</good>
      <good position="목적어">"...에서 {first_kw}을(를) 논의했습니다."</good>
      <good position="수식어">"{first_kw}의 성과로..."</good>
      <bad>동일 문단에 같은 키워드 2회 이상 반복</bad>
      <bad>키워드만 나열하는 스터핑</bad>
      <bad>띄어쓰기 임의 변경</bad>
      <bad>같은 키워드를 연속 문단에 배치 (최소 1문단 간격 유지)</bad>
    </insertion_method>
  </keywords>
  <keyword_quality severity="critical">
    <bad>키워드만으로 구성된 독립 문장: "OO 공약은 ~을 위한 약속입니다."</bad>
    <bad>문맥과 무관한 키워드 삽입: "OO 관련 현황을 반드시 이뤄낼 것입니다."</bad>
    <good>앞 문단과 연결어(이러한, 이처럼)로 이어지는 자연스러운 문장 속 배치</good>
    <good>구체적 정보(수치, 사례)와 함께 키워드가 등장하는 문장</good>
    <test>이 키워드를 빼도 문장이 성립하는가? → NO면 자연 삽입 성공</test>
  </keyword_quality>"""

    checklist_keywords = ''
    if keywords:
        checklist_keywords = f"""
    <item>각 키워드를 {min_insertions}~{max_per_keyword}회씩, 총 {total_insertions}~{total_insertions + kw_count}회 자연스럽게 배치</item>
    <item>키워드가 도입부/본론/결론에 고르게 분산 (약 2문단당 1개 꼴)</item>
    <item>같은 키워드를 연속 문단에 넣지 않기 (최소 1문단 간격)</item>"""

    return f"""
<seo_rules priority="highest" warning="위반 시 원고 폐기">
  <word_count min="{min_len}" max="{max_len}"/>
{keyword_section}
  <checklist>
    <item>글자수 {min_len}~{max_len}자 범위 준수</item>{checklist_keywords}
    <item>도입-본론-결론 구조로 내용 구성</item>
  </checklist>
</seo_rules>
"""

def build_anti_repetition_instruction():
    """
    반복 금지 및 품질 규칙 지침 생성 (XML 형식)
    """
    return """
<anti_repetition_rules severity="critical" warning="위반 시 원고 폐기">
  <rule id="no_duplicate_sentence">
    동일 문장 2회 이상 등장 절대 금지. 표현만 살짝 바꾼 유사 문장도 반복으로 간주.
  </rule>
  <rule id="no_similar_paragraph">
    같은 주장을 표현만 바꿔 여러 번 반복 금지. 결론에서 본문 재요약 금지.
    각 문단은 하나의 핵심 메시지만 전달. 새 문단은 반드시 새로운 정보 포함.
  </rule>
  <rule id="no_verb_repeat">
    같은 동사/구문을 원고 전체에서 3회 이상 사용 금지.
    <bad>"던지면서" 6회 반복</bad>
    <fix>제시하며, 약속하며, 열며, 보여드리며 등 동의어 교체</fix>
  </rule>
  <rule id="no_slogan_repeat">
    캐치프레이즈, 비전 문구, 벤치마크 비유는 결론부에서 1회만 사용.
    <bad>"아시아의 싱가포르" 2회 사용</bad>
    <fix>첫 등장만 유지, 두 번째는 "세계적인 경제·관광 도시"로 변형</fix>
  </rule>
  <rule id="no_section_closing_repeat" severity="critical">
    CTA(행사 안내, 장소·일시, 참여 요청)는 도입부(1회)와 결론부(1회)에만 허용.
    본론 섹션(소제목 아래)은 CTA 없이 다음 주제로 자연스럽게 연결해야 함.
    <bad>5개 섹션 모두 "3월 1일, 서면 영광도서에서 여러분을 기다리겠습니다"로 끝남</bad>
    <fix>본론 섹션은 "이러한 경험이 다음 비전의 토대가 되었습니다" 식으로 다음 주제 예고</fix>
  </rule>
  <rule id="no_phrase_repeat" severity="critical">
    3어절 이상의 동일 구문은 원고 전체에서 2회까지만 허용.
    <bad>"부산 경제 대혁신을 반드시 이뤄내겠습니다" 5회 등장</bad>
    <bad>"평범한 이웃들의 월급봉투" 4회 등장</bad>
    <fix>핵심 메시지는 결론에서 1회만, 본론에서는 구체적 정책/사례로 대체</fix>
  </rule>
  <rule id="no_forced_insertion">
    프롬프트에서 요청한 톤 키워드("그래도", "함께" 등)를 매 섹션에 기계적으로 삽입 금지.
    톤 키워드는 원고 전체에서 자연스러운 맥락에서 1~2회만 사용.
    <bad>"그래도"가 5개 섹션 모두에 1회씩 = 5회 등장</bad>
    <fix>"그래도"는 가장 효과적인 위치(역경 서사 또는 결론) 1곳에서만 사용</fix>
  </rule>
  <rule id="structure_consistency">
    마무리 인사("감사합니다", "~드림") 이후 본문 절대 재시작 금지.
  </rule>
  <checklist>
    <item>같은 문장 2번 이상 등장하지 않는가?</item>
    <item>같은 동사 3번 이상 반복하지 않았는가?</item>
    <item>같은 슬로건/비유 2번 이상 반복하지 않았는가?</item>
    <item>각 문단이 새로운 정보를 담고 있는가?</item>
    <item>마무리 인사 이후 본문이 재시작되지 않는가?</item>
    <item>CTA(장소·일시·참여 요청)가 도입부와 결론부에만 있는가?</item>
    <item>3어절 이상 동일 구문이 3회 이상 등장하지 않는가?</item>
    <item>톤 키워드("그래도" 등)가 2회 이하인가?</item>
  </checklist>
</anti_repetition_rules>
"""
