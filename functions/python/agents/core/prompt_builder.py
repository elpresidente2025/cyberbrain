"""StructureAgent 프롬프트 조립 로직 분리 모듈.

모든 함수는 stateless 순수 함수로, StructureAgent에서 추출되었다.
"""

from typing import Dict, Any, Optional, List

from ..common.warnings import generate_non_lawmaker_warning
from ..common.seo import build_seo_instruction
from ..common.h2_guide import (
    build_h2_examples,
    H2_MIN_LENGTH,
    H2_MAX_LENGTH,
    H2_OPTIMAL_MIN,
    H2_OPTIMAL_MAX,
)
from ..common.election_rules import get_prompt_instruction
from ..common.natural_tone import build_natural_tone_prompt
from ..common.editorial import STRUCTURE_SPEC, KEYWORD_SPEC, QUALITY_SPEC

from ..templates.daily_communication import build_daily_communication_prompt
from ..templates.activity_report import build_activity_report_prompt
from ..templates.policy_proposal import build_policy_proposal_prompt
from ..templates.current_affairs import build_critical_writing_prompt, build_diagnosis_writing_prompt
from ..templates.local_issues import build_local_issues_prompt

from .structure_utils import (
    strip_html, normalize_context_text, _xml_text, _xml_cdata,
    material_key, split_into_context_items,
)

# ---------------------------------------------------------------------------
# Template Builders Mapping
# ---------------------------------------------------------------------------
TEMPLATE_BUILDERS = {
    'emotional_writing': build_daily_communication_prompt,
    'logical_writing': build_policy_proposal_prompt,
    'direct_writing': build_activity_report_prompt,
    'critical_writing': build_critical_writing_prompt,
    'diagnostic_writing': build_diagnosis_writing_prompt,
    'analytical_writing': build_local_issues_prompt,
}


# ---------------------------------------------------------------------------
# Utility helpers (extracted from StructureAgent)
# ---------------------------------------------------------------------------

def is_current_lawmaker(user_profile: Dict) -> bool:
    """사용자가 현직 의원/단체장인지 판별한다."""
    if not user_profile or not isinstance(user_profile, dict):
        return False
    status = user_profile.get('status', '')
    position = user_profile.get('position', '')
    title = user_profile.get('customTitle', '')
    elected_keywords = ['의원', '구청장', '군수', '시장', '도지사', '교육감']
    text_to_check = status + position + title
    return any(k in text_to_check for k in elected_keywords)


# ---------------------------------------------------------------------------
# build_material_uniqueness_guard
# ---------------------------------------------------------------------------

def build_material_uniqueness_guard(
    context_analysis: Optional[Dict[str, Any]],
    *,
    body_sections: int,
) -> str:
    """소재 카드 중복 사용 방지 XML 가드를 생성한다."""
    if not isinstance(context_analysis, dict):
        return ""

    cards: List[Dict[str, str]] = []
    seen: set[str] = set()

    def add_card(card_type: str, raw_text: Any) -> None:
        text = normalize_context_text(raw_text)
        if len(strip_html(text)) < 8:
            return
        key = material_key(text)
        if not key or key in seen:
            return
        seen.add(key)
        cards.append({"type": card_type, "text": text})

    for item in context_analysis.get('mustIncludeFromStance') or []:
        if isinstance(item, dict):
            add_card("stance", item.get('topic'))
        else:
            add_card("stance", item)
    for item in context_analysis.get('mustIncludeFacts') or []:
        add_card("fact", item)
    for item in context_analysis.get('newsQuotes') or []:
        add_card("quote", item)

    if not cards:
        return ""

    body_count = max(1, int(body_sections or 1))
    max_cards = max(4, min(len(cards), body_count + 3))
    selected = cards[:max_cards]
    lines: List[str] = []
    for idx, card in enumerate(selected):
        section_slot = (idx % body_count) + 1
        lines.append(
            f'    <material id="M{idx + 1}" type="{card["type"]}" '
            f'section_hint="body_{section_slot}">{_xml_text(card["text"])}</material>'
        )

    allocated_count = min(body_count, len(selected))
    allocation_lines: List[str] = []
    for idx in range(allocated_count):
        allocation_lines.append(
            f'    <section index="{idx + 1}" use="M{idx + 1}" mode="exclusive_once"/>'
        )

    if body_count > allocated_count:
        banned_ids = ",".join(f"M{idx + 1}" for idx in range(allocated_count))
        for idx in range(allocated_count, body_count):
            allocation_lines.append(
                f'    <section index="{idx + 1}" use="DERIVED" mode="new_evidence_only" '
                f'ban_ids="{banned_ids}"/>'
            )

    lines_text = "\n".join(lines)
    allocation_text = "\n".join(allocation_lines)
    return f"""
<material_uniqueness_guard priority="critical">
  <rule id="one_material_one_use">소재 카드는 본문 전체에서 1회만 사용합니다.</rule>
  <rule id="follow_section_allocation">section_allocation 지시를 그대로 따르고, 이미 사용한 material id는 재사용 금지합니다.</rule>
  <rule id="no_recycled_quote">동일 인용/일화/근거 문장을 다른 섹션에서 다시 쓰지 않습니다.</rule>
  <rule id="body_diversity">각 본론 섹션은 서로 다른 근거를 사용해 논지를 전개합니다.</rule>
  <materials>
{lines_text}
  </materials>
  <section_allocation>
{allocation_text}
  </section_allocation>
</material_uniqueness_guard>
""".strip()


# ---------------------------------------------------------------------------
# build_retry_directive
# ---------------------------------------------------------------------------

def build_retry_directive(
    validation: Dict[str, Any],
    length_spec: Dict[str, int],
) -> str:
    """검증 실패 코드에 따른 재시도 지시문을 생성한다."""
    code = validation.get('code')
    total_sections = length_spec['total_sections']
    body_sections = length_spec['body_sections']
    min_chars = length_spec['min_chars']
    max_chars = length_spec['max_chars']
    per_section_recommended = length_spec['per_section_recommended']
    expected_h2 = length_spec['expected_h2']
    section_min_delta = int(STRUCTURE_SPEC['sectionCharTarget']) - int(STRUCTURE_SPEC['sectionCharMin'])
    section_max_delta = int(STRUCTURE_SPEC['sectionCharMax']) - int(STRUCTURE_SPEC['sectionCharTarget'])

    if code == 'LENGTH_SHORT':
        return (
            f"재작성 시 총 분량을 {min_chars}~{max_chars}자로 맞추십시오. "
            f"총 섹션은 도입 1 + 본론 {body_sections} + 결론 1(총 {total_sections})로 유지하고, "
            f"섹션당 {per_section_recommended}자 내외로 보강하십시오."
        )

    if code == 'LENGTH_LONG':
        return (
            f"재작성 시 총 분량을 {max_chars}자 이하로 압축하십시오(절대 초과 금지). "
            f"중복 문장, 수식어, 유사 사례를 제거하고 섹션당 {per_section_recommended}자 내외로 간결하게 작성하십시오."
        )

    if code in {'H2_SHORT', 'H2_LONG'}:
        return (
            f"섹션 구조를 정확히 맞추십시오: 도입 1 + 본론 {body_sections} + 결론 1. "
            f"<h2>는 본론과 결론에만 사용하여 총 {expected_h2}개로 작성하십시오. "
            f"소제목 태그는 속성 없이 반드시 <h2>텍스트</h2> 형식만 허용됩니다."
        )

    if code in {'P_SHORT', 'P_LONG'}:
        return (
            f"문단 수를 조정하십시오. 총 {total_sections}개 섹션 기준으로 문단은 2~3개씩 유지하고, "
            f"군더더기 없는 문장으로 길이 범위({min_chars}~{max_chars}자)를 지키십시오."
        )

    if code == 'EVENT_INVITE_REDUNDANT':
        return (
            "행사 안내 문구 반복을 줄이십시오. \"직접 만나\", \"진솔한 소통\", \"기다리겠습니다\" 류 표현은 "
            "각 2회 이하로 제한하고, 중복된 문장은 행사 핵심 정보(일시/장소/참여 방법)나 새로운 근거로 치환하십시오."
        )

    if code == 'EVENT_FACT_REPEAT':
        return (
            "행사 일시+장소가 결합된 안내 문장은 도입 1회, 결론 1회까지만 허용됩니다. "
            "3회째부터는 \"이번 행사 현장\"처럼 변형하여 반복 구문을 해소하십시오."
        )

    if code == 'META_PROMPT_LEAK':
        return (
            "프롬프트 규칙 설명 문장을 본문에 쓰지 마십시오. "
            "\"문제는~점검\"류 메타 문장을 제거하고 실제 사실/근거 문장으로 바꿔 작성하십시오."
        )

    if code == 'PHRASE_REPEAT_CAP':
        return (
            f"상투 구문 반복이 과다합니다. 동일 어구는 최대 {int(QUALITY_SPEC['phrase3wordMax'])}회로 제한하고, "
            "초과 구간은 새로운 근거·수치·사례 중심 문장으로 재작성하십시오."
        )

    if code == 'MATERIAL_REUSE':
        return (
            "같은 소재(인용/일화/근거)를 여러 번 재사용했습니다. "
            "본론 섹션마다 서로 다른 소재 카드를 배정하고, 각 카드는 1회만 사용하십시오."
        )

    if code == 'H2_TEXT_LONG':
        return (
            f"소제목(<h2>)이 {H2_MAX_LENGTH}자를 초과했습니다. "
            f"각 소제목을 {H2_OPTIMAL_MIN}~{H2_MAX_LENGTH}자 이내로 줄이십시오. "
            "질문형('~인가?', '~할까?') 또는 핵심 키워드 중심 명사구로 작성하고, "
            "수식어(~위한, ~향한, ~통한, ~에 대한)를 삭제하십시오."
        )

    if code == 'H2_TEXT_SHORT':
        return (
            f"소제목(<h2>)이 {H2_MIN_LENGTH}자 미만으로 너무 짧습니다. "
            f"각 소제목을 {H2_OPTIMAL_MIN}~{H2_OPTIMAL_MAX}자로 작성하십시오. "
            "핵심 키워드를 앞에 배치하고, 구체적 정보(수치/대상/장소)를 포함하십시오."
        )

    if code == 'H2_TEXT_MODIFIER':
        return (
            "소제목에 금지 수식어(위한/향한/만드는/통한/대한)가 포함되어 있습니다. "
            "해당 수식어를 제거하고 '명사+명사' 또는 '명사, 명사' 형태로 간결하게 재작성하십시오."
        )

    if code == 'H2_TEXT_FIRST_PERSON':
        return (
            "소제목에 1인칭 표현(저는/제가/나는/내가)이 포함되어 있습니다. "
            "소제목은 헤드라인형으로 작성하고, 대결/비교 문맥이면 'vs 주진우, 이재성의 약진'처럼 "
            "인물명+쟁점 중심 명사형으로 바꾸십시오."
        )

    if code == 'SECTION_LENGTH':
        return (
            f"원문 구조는 유지한 채 실패한 섹션만 부분 수정하십시오. "
            f"섹션별 글자 수를 {per_section_recommended}자 내외({per_section_recommended - section_min_delta}~{per_section_recommended + section_max_delta}자)로 조정하십시오. "
            f"결론부가 너무 짧으면 행동 제안이나 핵심 메시지를 보강하고, "
            f"특정 섹션이 너무 길면 마지막 문장부터 압축해 균형을 맞추십시오."
        )

    if code == 'SECTION_P_COUNT':
        return (
            "실패한 섹션의 문단 수만 부분 수정하십시오. "
            "서론은 1~4개, 나머지 섹션은 2~4개의 <p>를 유지하고, "
            "기존 사실/근거 문장은 최대한 보존하십시오."
        )

    if code == 'INTRO_STANCE_MISSING':
        return (
            "서론 첫 1~2문단에 입장문 핵심 주장/문제의식을 1~2문장으로 보강하십시오. "
            "본론/결론은 유지하고 서론만 부분 수정하십시오."
        )

    if code == 'INTRO_CONCLUSION_ECHO':
        return (
            "서론-결론의 중복 문구만 변형하십시오. "
            "결론 문장 중 반복 구간만 치환하고, 나머지 구조와 근거는 유지하십시오."
        )

    if code == 'DUPLICATE_SENTENCE':
        return (
            "동일 문장이 반복되었습니다. "
            "같은 의미를 전달하더라도 표현을 반드시 변형하여 재작성하십시오."
        )

    if code == 'PHRASE_REPEAT':
        return (
            "3어절 이상의 동일 구문이 과다 반복되었습니다. "
            "핵심 메시지는 결론에서 1회만, 본론에서는 구체적 정책/사례로 대체하십시오."
        )

    if code == 'VERB_REPEAT':
        return (
            "동일 동사/구문이 과다 반복되었습니다. "
            "동의어로 교체하십시오 (예: '던지면서' → '제시하며', '약속하며', '보여드리며')."
        )

    return (
        f"총 {total_sections}개 섹션 구조와 분량 범위({min_chars}~{max_chars}자)를 준수하되, "
        "전면 재작성보다 부분 수정을 우선하십시오."
    )


# ---------------------------------------------------------------------------
# build_structure_prompt
# ---------------------------------------------------------------------------

def build_structure_prompt(params: Dict[str, Any]) -> str:
    """StructureAgent용 XML 프롬프트를 조립한다.

    params에는 process()가 미리 계산한 값들이 포함된다:
    - lengthSpec: _build_length_spec() 결과 (필수)
    - contextAnalysis: 이미 정규화된 context analysis dict
    - 기타 topic, authorBio, userKeywords 등
    """
    # Extract params
    writing_method = params.get('writingMethod')
    template_builder = TEMPLATE_BUILDERS.get(writing_method, build_daily_communication_prompt)

    user_profile = params.get('userProfile', {})
    if not isinstance(user_profile, dict):
        user_profile = {}
    output_mode = str(params.get('outputMode') or 'xml').strip().lower()
    news_source_mode = str(params.get('newsSourceMode') or 'news').strip().lower()
    profile_support_context = normalize_context_text(params.get('profileSupportContext'))
    profile_substitute_context = normalize_context_text(params.get('profileSubstituteContext'))
    personalization_context = normalize_context_text(
        params.get('personalizationContext') or params.get('memoryContext'),
        sep="\n",
    )

    # Build base template prompt
    template_prompt = template_builder({
        'topic': params.get('topic'),
        'authorBio': params.get('authorBio'),
        'authorName': params.get('authorName'),
        'instructions': params.get('instructions'),
        'keywords': params.get('userKeywords'),
        'targetWordCount': params.get('targetWordCount'),
        'personalizedHints': personalization_context,
        'newsContext': params.get('newsContext'),
        'isCurrentLawmaker': is_current_lawmaker(user_profile),
        'politicalExperience': user_profile.get('politicalExperience', '정치 신인'),
        'familyStatus': user_profile.get('familyStatus', ''),
        'emotionalArchetypeId': params.get('emotionalArchetypeId'),
        'narrativeFrameId': params.get('narrativeFrameId'),
        'declarativeStructureId': params.get('declarativeStructureId'),
        'rhetoricalTacticId': params.get('rhetoricalTacticId'),
        'logicalStructureId': params.get('logicalStructureId'),
        'argumentationTacticId': params.get('argumentationTacticId'),
        'criticalStructureId': params.get('criticalStructureId'),
        'offensiveTacticId': params.get('offensiveTacticId'),
        'analyticalStructureId': params.get('analyticalStructureId'),
        'explanatoryTacticId': params.get('explanatoryTacticId'),
        'vocabularyModuleId': params.get('vocabularyModuleId'),
    })

    # Reference Materials Section
    instructions_text = normalize_context_text(params.get('instructions'))
    news_context_text = normalize_context_text(params.get('newsContext'))
    rag_context_text = normalize_context_text(params.get('ragContext'))
    source_blocks = [instructions_text]
    if news_context_text:
        source_blocks.append(news_context_text)
    if rag_context_text:
        source_blocks.append(f"[사용자 프로필 기반 맥락]\n{rag_context_text}")
    bio_source_line = ""
    bio_source_rule = "보조 자료: 사용자 프로필(Bio)은 화자 정체성과 어조 참고용이며, 분량이 부족할 때만 활용하세요."
    if news_source_mode == 'profile_fallback' and profile_substitute_context:
        source_blocks.append(f"[뉴스/데이터 대체자료]\n{profile_substitute_context}")
        bio_source_line = "- 대체 자료: 사용자 추가정보(공약/법안/성과) 무작위 3개 + Bio 보강"
        bio_source_rule = (
            "대체자료 활용: 뉴스/데이터가 비어 있으므로 사용자 추가정보(공약/법안/성과)와 "
            "Bio 보강 맥락에서 팩트를 추출해 사용하세요. 대체자료 3개는 매 요청마다 무작위 선정됩니다."
        )
    elif not news_context_text and profile_support_context:
        source_blocks.append(f"[작성자 BIO 보강 맥락]\n{profile_support_context}")
        bio_source_line = "- 보강 자료: 사용자 Bio (경력/이력/가치)"
        bio_source_rule = (
            "Bio 보강 활용: 뉴스/데이터와 구조화 추가정보가 모두 부족하므로 "
            "사용자 Bio에서 확인 가능한 경력/성과/핵심가치를 사실 근거로 활용하세요."
        )

    source_text = "\n\n---\n\n".join(block for block in source_blocks if block)
    ref_section = ""
    if source_text.strip():
        ref_section = f"""
<reference_materials priority="critical">
  <overview>아래 참고자료가 이 원고의 1차 자료(Primary Source)입니다.</overview>
  <source_order>
    <item order="1">첫 번째 자료: 작성자의 입장문/페이스북 글 (핵심 논조와 주장)</item>
    <item order="2">이후 자료: 뉴스/데이터 (근거, 팩트, 배경 정보)</item>
    {'<item order="3">' + _xml_text(bio_source_line) + '</item>' if bio_source_line else ''}
  </source_order>
  <source_body>{_xml_cdata(source_text[:6000])}</source_body>
  <processing_rules>
    <rule order="1">정보 추출: 핵심 팩트, 수치, 논점만 사용</rule>
    <rule order="2">재작성 필수: 참고자료 문장을 그대로 복사하지 않음</rule>
    <rule order="3">구어체를 문어체로 변환</rule>
    <rule order="4">창작 금지: 참고자료에 없는 팩트/수치 생성 금지</rule>
    <rule order="5">주제 유지: 참고자료 핵심 주제 이탈 금지</rule>
    <rule order="6">{_xml_text(bio_source_rule)}</rule>
  </processing_rules>
  <forbidden_examples>
    <example type="source">{_xml_cdata('정확하게 얘기를 하면 그래서 창의적이고 정말 압도적인...')}</example>
    <example type="bad">{_xml_cdata('정확하게 얘기를 하면 그래서 창의적이고...')}</example>
    <example type="good">{_xml_cdata('창의적이고 압도적인 콘텐츠 기반 전략이 핵심입니다.')}</example>
  </forbidden_examples>
</reference_materials>
"""
        print(f"📚 [StructureAgent] 참고자료 주입 완료: {len(source_text)}자")
    else:
        print("⚠️ [StructureAgent] 참고자료 없음 - 사용자 프로필만으로 생성")

    # Context Injection
    context_injection = ""
    is_event_announcement = False
    event_date_hint = ""
    event_location_hint = ""
    event_contact_hint = ""
    event_cta_hint = ""
    intro_anchor_topic = ""
    intro_anchor_why = ""
    intro_anchor_effect = ""
    intro_seed = ""

    intro_seed_candidates = split_into_context_items(instructions_text, min_len=10, max_items=6)
    if not intro_seed_candidates and profile_substitute_context:
        intro_seed_candidates = split_into_context_items(profile_substitute_context, min_len=10, max_items=6)
    if not intro_seed_candidates and news_context_text:
        intro_seed_candidates = split_into_context_items(news_context_text, min_len=10, max_items=6)
    if not intro_seed_candidates:
        intro_seed_candidates = split_into_context_items(
            normalize_context_text(params.get('topic')),
            min_len=6,
            max_items=2,
        )
    if intro_seed_candidates:
        intro_seed = intro_seed_candidates[0]

    context_analysis = params.get('contextAnalysis')
    if not isinstance(context_analysis, dict):
        context_analysis = {}

    if context_analysis:
        stance_list = context_analysis.get('mustIncludeFromStance', [])

        # 구조화된 stance 처리
        formatted_stances = []
        for i, p in enumerate(stance_list):
            if isinstance(p, dict):
                topic = p.get('topic', '')
                why_txt = p.get('expansion_why', '')
                how_txt = p.get('expansion_how', '')
                eff_txt = p.get('expansion_effect', '')

                block = f"""
<stance index="{i+1}" section_hint="본론 {i+1}">
  <topic>{_xml_text(topic)}</topic>
  <why>{_xml_text(why_txt)}</why>
  <how>{_xml_text(how_txt)}</how>
  <effect>{_xml_text(eff_txt)}</effect>
</stance>"""
                formatted_stances.append(block.strip())
            else:
                formatted_stances.append(
                    f"<stance index=\"{i+1}\" section_hint=\"본론 {i+1}\"><topic>{_xml_text(p)}</topic></stance>"
                )

        stance_phrases = "\n\n".join(formatted_stances)
        stance_count = len(stance_list)
        if stance_list:
            first = stance_list[0]
            if isinstance(first, dict):
                intro_anchor_topic = normalize_context_text(first.get('topic'))
                intro_anchor_why = normalize_context_text(first.get('expansion_why'))
                intro_anchor_effect = normalize_context_text(first.get('expansion_effect'))
            else:
                intro_anchor_topic = normalize_context_text(first)

        if stance_count > 0:
            context_injection = f"""
<body_expansion mandatory="true">
  <description>아래 {stance_count}개 설계도에 따라 본론 섹션을 확장합니다.</description>
  <stance_count>{stance_count}</stance_count>
  <stance_blueprints>
{stance_phrases}
  </stance_blueprints>
  <instructions>
    <instruction order="1">각 주제를 별도의 본론 섹션(H2)으로 구성</instruction>
    <instruction order="2">각 섹션에 Why/How/Effect 논리를 핵심 위주로 반영</instruction>
    <instruction order="3">How 단계에서 Bio(경력)를 근거로 전문성을 제시</instruction>
  </instructions>
</body_expansion>
"""

            intro_anchor_summary = " / ".join(
                part for part in [intro_anchor_topic, intro_anchor_why, intro_anchor_effect] if part
            ).strip()
            if intro_anchor_summary:
                context_injection += f"""
<intro_anchor mandatory="true">
  <description>서론 1~2문단은 입장문 핵심 요지를 재진술하고 본론으로 연결합니다.</description>
  <anchor>{_xml_text(intro_anchor_summary)}</anchor>
</intro_anchor>
"""

        # contentStrategy 주입
        content_strategy = context_analysis.get('contentStrategy', {})
        if content_strategy:
            tone = content_strategy.get('tone', '')
            structure = content_strategy.get('structure', '')
            emphasis = content_strategy.get('emphasis', [])

            if tone or structure:
                emphasis_str = ", ".join(emphasis) if emphasis else "없음"
                context_injection += f"""
<content_strategy>
  <tone>{_xml_text(tone)}</tone>
  <structure>{_xml_text(structure)}</structure>
  <emphasis>{_xml_text(emphasis_str)}</emphasis>
</content_strategy>
"""
                print(f"🎯 [StructureAgent] 콘텐츠 전략 주입: {tone} / {structure}")

        # mustPreserve 기반 CTA 정보 주입
        must_preserve = context_analysis.get('mustPreserve', {})
        intent = context_analysis.get('intent', '')

        if must_preserve and intent == 'donation_request':
            print("💡 [StructureAgent] 후원 정보 본문 주입 생략 (최종 출력 단계에서만 부착)")

        elif must_preserve and intent == 'event_announcement':
            is_event_announcement = True
            event_date = must_preserve.get('eventDate')
            event_location = must_preserve.get('eventLocation')
            contact_number = must_preserve.get('contactNumber')
            cta_phrase = must_preserve.get('ctaPhrase')

            event_date_hint = str(event_date or '').strip()
            event_location_hint = str(event_location or '').strip()
            event_contact_hint = str(contact_number or '').strip()
            event_cta_hint = str(cta_phrase or '').strip()

            if event_date or event_location:
                event_parts = []
                if event_date:
                    event_parts.append(f"- 일시: {event_date}")
                if event_location:
                    event_parts.append(f"- 장소: {event_location}")
                if contact_number:
                    event_parts.append(f"- 문의: {contact_number}")

                event_text = "\n".join(event_parts)

                context_injection += f"""
<event_context mandatory="true">
  <facts>{_xml_cdata(event_text)}</facts>
  <instructions>
    <instruction order="1">행사 정보(일시/장소/참여방법)를 도입에서 명확히 제시</instruction>
    <instruction order="2">동일한 일시+장소 결합 문장을 본문에서 반복하지 않음</instruction>
    <instruction order="3">결론 CTA는 행동 동사+구체 장소로 1회만 제시</instruction>
  </instructions>
</event_context>
"""
                print(f"📅 [StructureAgent] 행사 정보 주입: {event_date} / {event_location}")

    if not intro_anchor_topic:
        intro_anchor_topic = intro_seed or normalize_context_text(params.get('topic'))

    # Warning Generation (XML)
    warning_blocks: List[str] = []
    non_lawmaker_warn = generate_non_lawmaker_warning(
        is_current_lawmaker(user_profile),
        user_profile.get('politicalExperience'),
        params.get('authorBio')
    )
    if non_lawmaker_warn:
        warning_blocks.append(
            f"<non_lawmaker_warning>{_xml_cdata(non_lawmaker_warn)}</non_lawmaker_warning>"
        )

    if params.get('authorBio') and '"' in params.get('authorBio', ''):
        warning_blocks.append(
            """
<bio_quote_rules priority="critical">
  <rule order="1">Bio의 큰따옴표(" ")로 묶인 문장은 원문 그대로 인용</rule>
  <rule order="2">따옴표 문장의 단어/조사/어미를 임의 수정하지 않음</rule>
  <rule order="3">사람 이름으로 단어를 대체하지 않음</rule>
  <examples>
    <bad><![CDATA["벌써 국회의원 했을 텐데" -> "벌써 홍길동 했을 텐데"]]></bad>
    <good><![CDATA["벌써 국회의원 했을 텐데" (원문 그대로)]]></good>
  </examples>
</bio_quote_rules>
""".strip()
        )

    bio_warning = ""
    if warning_blocks:
        bio_warning = "<warning_bundle>\n" + "\n".join(warning_blocks) + "\n</warning_bundle>"

    # Length spec (반드시 params에서 전달받는다)
    length_spec = params.get('lengthSpec') or {}
    stance_count = 0
    if context_analysis:
        stance_count = len(context_analysis.get('mustIncludeFromStance', []))

    total_sections_default = int(STRUCTURE_SPEC['minSections'])
    body_sections_default = max(1, total_sections_default - 2)
    body_section_count = length_spec.get('body_sections', body_sections_default)
    total_section_count = length_spec.get('total_sections', total_sections_default)
    min_total_chars = length_spec.get('min_chars', int(STRUCTURE_SPEC['idealTotalMin']))
    max_total_chars = length_spec.get('max_chars', int(STRUCTURE_SPEC['idealTotalMax']))
    per_section_min = length_spec.get('per_section_min', int(STRUCTURE_SPEC['sectionCharMin']))
    per_section_max = length_spec.get('per_section_max', int(STRUCTURE_SPEC['sectionCharMax']))
    per_section_recommended = length_spec.get('per_section_recommended', int(STRUCTURE_SPEC['sectionCharTarget']))
    material_uniqueness_guard = build_material_uniqueness_guard(
        context_analysis,
        body_sections=body_section_count,
    )

    intro_line_1 = '<p>1문단: 입장문/페이스북 글의 핵심 주장으로 바로 시작하고 자기소개는 1문장 이내로 제한</p>'
    intro_line_2 = '<p>2문단: 입장문 핵심 주장(원문 요지)을 재작성하여 글의 목적을 명확히 제시</p>'
    intro_line_3 = '<p>3문단: 본론에서 다룰 해결 방향/행동 제안을 예고</p>'
    intro_stance_rules = f"""
  <intro_stance_binding priority="critical">
    <rule id="intro_must_anchor_stance">서론 2문단 이내에 입장문 핵심 주장 또는 문제의식을 반드시 재진술할 것.</rule>
    <rule id="intro_first_sentence_from_stance">서론 첫 문장은 stance_seed를 바탕으로 재구성하고, 일반 인삿말로 시작하지 말 것.</rule>
    <rule id="intro_no_generic_opening">맥락 없는 일반 인삿말/상투적 도입으로 시작하지 말 것.</rule>
    <rule id="intro_paraphrase_required">입장문 문장을 그대로 복붙하지 말고 의미는 유지한 채 재작성할 것.</rule>
    <rule id="intro_profile_cap">서론 전체에서 경력/이력 나열은 최대 2문장으로 제한할 것.</rule>
    <rule id="intro_to_body_bridge">서론 마지막 문장에서 본론 주제로 자연스럽게 연결할 것.</rule>
    <stance_seed>{intro_seed or '(입장문 요지 없음)'}</stance_seed>
    <stance_anchor_topic>{intro_anchor_topic or '(미지정)'}</stance_anchor_topic>
  </intro_stance_binding>
"""
    event_mode_rules = ''
    if is_event_announcement:
        intro_line_1 = '<p>1문단: 화자 실명 + 행사 목적을 2문장 이내로 명확히 제시</p>'
        intro_line_2 = '<p>2문단: 행사 핵심정보(일시/장소/참여방법/문의)를 한 문단으로 압축 제시</p>'
        intro_line_3 = '<p>3문단: 입장문의 문제의식/핵심 메시지가 행사에서 어떻게 다뤄지는지 제시</p>'
        event_mode_rules = f"""
  <event_mode intent="event_announcement" priority="critical">
    <facts>
      <event_date>{event_date_hint or '(미상)'}</event_date>
      <event_location>{event_location_hint or '(미상)'}</event_location>
      <event_contact>{event_contact_hint or '(미상)'}</event_contact>
      <event_cta>{event_cta_hint or '(없음)'}</event_cta>
    </facts>
    <rule id="event_info_first">도입부 2문단 이내에 행사 일시/장소/참여 방법을 모두 제시할 것.</rule>
    <rule id="speaker_name_required">첫 문단 첫 2문장 안에 화자 실명을 반드시 포함할 것.</rule>
    <rule id="bio_limit_before_event">행사 핵심정보 제시 전, 화자 경력/서사 서술은 최대 2문장으로 제한할 것.</rule>
    <rule id="no_invite_redundancy">"직접 만나", "진솔한 소통" 류 문구 반복 금지. 원고 전체 최대 2회.</rule>
    <rule id="event_fact_repeat_limit">행사 일시/장소/참여 안내 문구는 도입 1회 + 결론 1회까지만 허용할 것.</rule>
    <rule id="event_fact_variation">동일한 일시+장소 결합 구문을 본문 섹션마다 반복하지 말 것. 중간 섹션에서는 "이번 행사 현장", "행사 자리"처럼 변형해 연결할 것.</rule>
    <rule id="event_datetime_ngram_cap">"3월 1일(일) 오후 2시, 서면..."처럼 일시+장소 결합 5단어 이상 구문은 원고 전체 최대 2회. 3회째부터는 "행사 당일", "당일 현장" 등 변형 표현으로만 작성할 것.</rule>
    <rule id="event_seed_priority">서론 1~2문단에서 입장문 핵심 시드(stance_seed)의 의미를 반드시 재진술할 것.</rule>
    <rule id="no_orphan_location_line">장소 키워드("서면 영광도서/부산 영광도서")는 단순 안내 단문으로 분리하지 말고, 해당 단락의 행사 맥락(참여 정보/대화 주제/독자 효익)과 결합한 문장으로 작성할 것.</rule>
    <rule id="no_recap_echo">각 섹션 끝의 요약 단문 반복 금지. 특히 "이 만남은 ~", "이 자리는 ~", "이 뜻깊은 자리는 ~", "이번 만남은 ~" 패턴은 원고 전체 1회만 허용.</rule>
    <rule id="cta_once">결론부 CTA는 1회만 작성하고, 행동 동사+구체 장소를 함께 제시할 것. 예: "주저 말고 서면 영광도서를 찾아 주십시오."</rule>
    <rule id="audience_intent">행사 안내문 독자가 즉시 행동할 수 있도록 정보 우선, 자기서사 과잉 금지.</rule>
    <rule id="event_intro_with_stance">행사 정보 제시 후, 입장문 핵심 메시지를 서론에서 바로 연결할 것.</rule>
  </event_mode>
"""

    # 동적 본론 구조 문자열 생성
    body_structure_lines = []
    for i in range(1, body_section_count + 1):
        body_structure_lines.append(
            f"<body_section order=\"{i+1}\" name=\"본론 {i}\" paragraphs=\"{STRUCTURE_SPEC['paragraphsPerSection']}\" chars=\"{per_section_min}~{per_section_max}\" heading=\"h2 필수\"/>"
        )
    body_structure_str = "\n    ".join(body_structure_lines)

    # 지역 정보 추출
    region_metro = user_profile.get('regionMetro', '')
    region_district = user_profile.get('regionDistrict', '')
    user_region = f"{region_metro} {region_district}".strip()
    if not user_region:
        user_region = "지역 사회"

    output_format_rule = "템플릿에서 지시한 XML 태그(title, content, hashtags)만 출력. output 래퍼나 마크다운 코드블록 금지."
    if output_mode == 'json':
        output_format_rule = (
            "최종 출력은 JSON 객체 1개만 반환하고, XML 태그/코드블록/설명문을 추가하지 마십시오. "
            "필수 키: title, intro, body, conclusion."
        )

    structure_enforcement = f"""
<structure_guide mode="strict">
  <strategy>E-A-T (전문성-권위-신뢰) 전략으로 작성</strategy>

  <volume warning="위반 시 시스템 오류">
    <per_section min="{per_section_min}" max="{per_section_max}" recommended="{per_section_recommended}"/>
    <paragraphs_per_section>{STRUCTURE_SPEC['paragraphsPerSection']}개 문단, 문단당 {STRUCTURE_SPEC['paragraphCharMin']}~{STRUCTURE_SPEC['paragraphCharMax']}자</paragraphs_per_section>
    <total sections="{total_section_count}" min="{min_total_chars}" max="{max_total_chars}"/>
    <caution>총 분량 상한을 넘기지 않도록 중복 문장과 장황한 수식어를 제거하고, 근거 중심으로 간결하게 작성하십시오.</caution>
  </volume>

  <expansion_guide name="섹션별 작성 4단계">
    각 본론 섹션을 아래 흐름으로 밀도 있게 전개하십시오.
    <step name="Why" sentences="1~2">시민들이 겪는 실제 불편함과 현장의 고충을 구체적으로 진단</step>
    <step name="How+Expertise" sentences="2">실현 가능한 해결책 제시 및 본인의 Bio(경력)를 인용하여 전문성 강조</step>
    <step name="Authority" sentences="1">과거 성과나 네트워크를 바탕으로 실행 능력을 증명</step>
    <step name="Effect+Trust" sentences="1~2">변화될 {user_region}의 미래 청사진을 명확히 제시</step>
  </expansion_guide>

  <sections total="{total_section_count}">
    <intro paragraphs="{STRUCTURE_SPEC['paragraphsPerSection']}" chars="{per_section_recommended}" heading="없음">
      {intro_line_1}
      {intro_line_2}
      {intro_line_3}
    </intro>
    {body_structure_str}
    <conclusion order="{total_section_count}" paragraphs="{STRUCTURE_SPEC['paragraphsPerSection']}" chars="{per_section_recommended}" heading="h2 필수"/>
  </sections>

  <h2_strategy name="소제목 작성 전략 (AEO+SEO)">
    <length min="12" max="30" optimal="15~22"/>
    <types>
      <type name="질문형" strength="AEO 최강" ratio="40% 이상 권장">
        <good>청년 기본소득, 신청 방법은?</good>
        <good>전세 사기 피해, 어떻게 보상받나요?</good>
        <bad>이것을 꼭 알아야 합니다</bad>
      </type>
      <type name="명사형" strength="SEO 기본">
        <good>분당구 정자동 주차장 신설 위치</good>
        <bad>정책 안내</bad>
      </type>
      <type name="데이터" strength="신뢰성">
        <good>청년 일자리 274명 창출 방법</good>
        <bad>좋은 성과를 냈습니다</bad>
      </type>
      <type name="절차" strength="실용성">
        <good>청년 기본소득 신청 3단계 절차</good>
        <bad>신청하는 방법</bad>
      </type>
      <type name="비교" strength="차별화">
        <good>기존 정책 대비 개선된 3가지</good>
        <bad>비교해 보겠습니다</bad>
      </type>
    </types>
    <banned>추상적 표현("노력", "열전", "마음"), 모호한 지시어("이것", "그것", "관련 내용"), 과장 표현("최고", "혁명적", "놀라운"), 서술어 포함("~에 대한 설명", "~을 알려드립니다"), 키워드 없는 짧은 제목("정책", "방법", "소개")</banned>
    <aeo_rule>H2 바로 아래 첫 문장(40~60자)은 해당 질문/주제에 대한 직접 답변으로 작성할 것.</aeo_rule>
  </h2_strategy>

{build_h2_examples()}

  <mandatory_rules>
    <rule id="html_tags">소제목은 &lt;h2&gt;, 문단은 &lt;p&gt; 태그만 사용 (마크다운 문법 금지)</rule>
    <rule id="defer_output_addons" severity="critical">슬로건/후원 안내(계좌·예금주·연락처·영수증 안내)는 본문에 쓰지 말 것. 해당 정보는 최종 출력 직전에 시스템이 자동 부착.</rule>
    <rule id="no_slogan_repeat" severity="critical">입장문의 맺음말/슬로건을 각 섹션 끝마다 반복 금지. 모든 호소와 다짐은 맨 마지막 결론부에만.</rule>
    <rule id="sentence_completion">문장은 올바른 종결 어미(~입니다, ~합니다, ~시오)로 끝내야 함. 고의적 오타/잘린 문장 금지.</rule>
    <rule id="keyword_per_section">각 섹션마다 키워드 {KEYWORD_SPEC['perSectionMin']}개 이상 포함</rule>
    <rule id="separate_pledges">각 본론 섹션은 서로 다른 주제/공약을 다룰 것</rule>
    <rule id="verb_diversity" severity="critical">같은 동사(예: "던지면서")를 원고 전체에서 {int(QUALITY_SPEC['verbRepeatMax']) + 1}회 이상 사용 금지. 동의어 교체: 제시하며, 약속하며, 열며, 보여드리며 등.</rule>
    <rule id="slogan_once">캐치프레이즈("청년이 돌아오는 부산")나 비유("아시아의 싱가포르")는 결론부 {QUALITY_SPEC['sloganMax']}회만. 다른 섹션에서는 변형 사용.</rule>
    <rule id="natural_keyword">키워드는 정보 문장이 아니라 맥락 문장으로 삽입. 키워드 문장에는 최소 1개 이상 포함: 행사 정보(일시/장소/참여 방법), 대화 주제, 시민 행동 제안. 해당 문단의 주장/근거와 결합해 쓰고, 키워드만으로 된 장식/단독 문장 금지.</rule>
    <rule id="no_single_sentence_echo">같은 구조의 단문 문장을 섹션 말미마다 반복 금지. 특히 "이 만남은 ~", "이 자리는 ~", "이 뜻깊은 자리는 ~", "이번 만남은 ~" 패턴은 한 번만 사용.</rule>
    <rule id="no_datetime_location_ngram_repeat">일시+장소가 함께 들어간 구문(예: "3월 1일(일) 오후 2시, 서면...")은 같은 어순으로 3회 이상 반복 금지. 2회를 넘으면 어순/표현을 반드시 변형할 것.</rule>
    <rule id="no_meta_prompt_leak">프롬프트/규칙 설명 문장을 본문에 복사하지 말 것. "문제는~점검" 같은 규칙성 메타 문장 생성 금지.</rule>
    <rule id="paragraph_min_sentences">원칙적으로 각 <p>는 최소 2문장으로 구성. 예외는 결론의 마지막 CTA 문단 1개만 허용.</rule>
    <rule id="causal_clarity">성과 언급 시 본인의 구체적 역할/직책 명시. "40% 득표율을 이끌어냈다" → "시당위원장으로서 지역 조직을 총괄하며 40% 득표율 달성에 기여했습니다"</rule>
  </mandatory_rules>
{material_uniqueness_guard}
{event_mode_rules}
{intro_stance_rules}

  <constraints warning="위반 시 자동 반려">
    <max_chars>{max_total_chars}</max_chars>
    <min_chars>{min_total_chars}</min_chars>
    <no_repeat>같은 문장, 같은 표현 반복 금지 (특히 "~바랍니다" 반복 금지)</no_repeat>
    <html>문단은 &lt;p&gt;...&lt;/p&gt;, 소제목은 &lt;h2&gt;...&lt;/h2&gt;만 사용</html>
    <separate_pledges>서로 다른 공약/정책은 하나의 본론에 합치지 말 것</separate_pledges>
  </constraints>

  <output_format>{_xml_text(output_format_rule)}</output_format>
</structure_guide>
"""

    # SEO 지침 생성
    seo_instruction = build_seo_instruction({
        'keywords': params.get('userKeywords', []),
        'targetWordCount': params.get('targetWordCount', int(STRUCTURE_SPEC['idealTotalMin']))
    })

    # 선거법 준수 지침 생성
    user_status = user_profile.get('status', '준비')
    election_instruction = get_prompt_instruction(user_status)

    party_stance_guide = params.get('partyStanceGuide') or ''
    context_injection_xml = ""
    if context_injection.strip():
        context_injection_xml = f"<context_injection>\n{context_injection.strip()}\n</context_injection>"

    natural_tone_guide = build_natural_tone_prompt({'severity': 'standard'})

    return f"""
<structure_agent_prompt version="xml-v1">
  <template_prompt>{_xml_cdata(template_prompt)}</template_prompt>
  <party_stance_guide>{_xml_cdata(party_stance_guide)}</party_stance_guide>
  <seo_instruction>{_xml_cdata(seo_instruction)}</seo_instruction>
  <election_instruction>{_xml_cdata(election_instruction)}</election_instruction>
  {ref_section}
  {context_injection_xml}
  {bio_warning}
  {structure_enforcement}
  {natural_tone_guide}
</structure_agent_prompt>
""".strip()
