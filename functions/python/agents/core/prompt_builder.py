"""StructureAgent 프롬프트 조립 로직 분리 모듈.

모든 함수는 stateless 순수 함수로, StructureAgent에서 추출되었다.
"""

import logging
from typing import Any, Dict, List

from ..common.warnings import generate_role_warning_bundle
from ..common.seo import build_seo_instruction
from ..common.h2_guide import build_h2_rules
from ..common.election_rules import get_prompt_instruction
from ..common.natural_tone import build_natural_tone_prompt
from ..common.editorial import QUALITY_SPEC, STRUCTURE_SPEC
from ..common.section_contract import build_shared_contract_rules
from ..common.stance_filters import looks_like_hashtag_bullet_line
from ..common.aeo_config import uses_aeo_answer_first

from ..templates.activity_report import build_activity_report_prompt
from ..templates.bipartisan_cooperation import build_bipartisan_cooperation_prompt
from ..templates.current_affairs import build_critical_writing_prompt, build_diagnosis_writing_prompt
from ..templates.daily_communication import build_daily_communication_prompt
from ..templates.local_issues import build_local_issues_prompt
from ..templates.offline_engagement import build_offline_engagement_prompt
from ..templates.policy_proposal import build_policy_proposal_prompt

from .prompt_guards import (
    _build_style_generation_guard,
    build_material_uniqueness_guard,
    build_poll_focus_bundle_section,
    build_retry_directive,
)
from .structure_utils import _xml_cdata, _xml_text, normalize_context_text, split_into_context_items
from .style_guide_builder import build_style_role_priority_summary
from ..common.writing_principles import build_writing_principles_xml
from ..common.leadership import build_leadership_philosophy_xml

logger = logging.getLogger(__name__)

# ── 중앙 상투어 대체어 사전 캐시 ──
_global_alt_cache: Dict[str, list] | None = None
_global_alt_cache_time: float = 0
_GLOBAL_ALT_CACHE_TTL: float = 3600  # 1시간


def _load_global_alternatives() -> Dict[str, list]:
    """확정 상투어 대체어 사전을 Firestore 에서 로드 (인스턴스당 1시간 캐시)."""
    global _global_alt_cache, _global_alt_cache_time
    import time

    now = time.time()
    if _global_alt_cache is not None and (now - _global_alt_cache_time) < _GLOBAL_ALT_CACHE_TTL:
        return _global_alt_cache

    try:
        from firebase_admin import firestore
        db = firestore.client()
        from services.cliche_dictionary.dictionary_manager import load_cliche_dictionary
        result = load_cliche_dictionary(db)
    except Exception as e:
        logger.debug("[prompt_builder] cliche dictionary load skipped: %s", e)
        if _global_alt_cache is not None:
            return _global_alt_cache
        return {}

    _global_alt_cache = result
    _global_alt_cache_time = now
    return result


TEMPLATE_BUILDERS = {
    'emotional_writing': build_daily_communication_prompt,
    'logical_writing': build_policy_proposal_prompt,
    'direct_writing': build_activity_report_prompt,
    'critical_writing': build_critical_writing_prompt,
    'diagnostic_writing': build_diagnosis_writing_prompt,
    'analytical_writing': build_local_issues_prompt,
    'bipartisan_writing': build_bipartisan_cooperation_prompt,
    'offline_writing': build_offline_engagement_prompt,
}

def is_current_lawmaker(user_profile: Dict) -> bool:
    """현직 국회의원 여부를 판별한다.

    profile 저장 시 `_canonical_position`이 직책을
    국회의원/광역의원/기초의원/광역자치단체장/기초자치단체장으로 정규화하므로
    캐노니컬 값 완전 일치만 본다. "의원" 부분 문자열 매칭은
    구의원/기초의원을 잘못 국회의원으로 분류하는 버그가 있어 제거됨.
    """
    if not user_profile or not isinstance(user_profile, dict):
        return False
    position = str(user_profile.get('position') or '').strip()
    return position == '국회의원'


def build_structure_prompt(params: Dict[str, Any]) -> str:
    """StructureAgent용 XML 프롬프트를 조립한다.

    params에는 process()가 미리 계산한 값들이 포함된다:
    - lengthSpec: _build_length_spec() 결과 (필수)
    - contextAnalysis: 이미 정규화된 context analysis dict
    - 기타 topic, authorBio, userKeywords 등
    """
    # Extract params
    writing_method = params.get('writingMethod')
    category = str(params.get('category') or '').strip().lower()
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
    style_guide = normalize_context_text(params.get('styleGuide'), sep="\n")
    style_fingerprint = params.get('styleFingerprint') if isinstance(params.get('styleFingerprint'), dict) else {}
    generation_profile = params.get('generationProfile') if isinstance(params.get('generationProfile'), dict) else {}

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
        # 화자 정체성 XML 블록(speaker_identity) 을 7 개 템플릿이 모두 같은
        # helper(agents/common/speaker_identity) 로 만들도록 user_profile 을
        # 템플릿에 전달한다. 템플릿은 build_speaker_identity_xml(user_profile=...)
        # 로 구조화 직책 앵커 + ally 룰을 한 번에 받는다.
        'userProfile': user_profile,
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
    if news_context_text:
        logger.info(
            "[prompt_builder] newsContext preview (first 200 chars): %s",
            news_context_text[:200],
        )
    source_blocks = [instructions_text]
    if news_context_text:
        source_blocks.append(news_context_text)
    if rag_context_text:
        source_blocks.append(f"[사용자 프로필 기반 맥락]\n{rag_context_text}")
    bio_source_line = ""
    bio_source_rule = "보조 자료: 사용자 프로필(Bio)은 화자 정체성과 어조 참고용이며, 분량이 부족할 때만 활용하세요."
    if news_source_mode == 'profile_fallback' and profile_substitute_context:
        source_blocks.append(
            "[화자 실적·활동 보조자료]\n"
            "⚠️ 본론의 주제는 반드시 입장문(위 참고자료 1)에서 가져오십시오. "
            "아래는 화자의 다른 활동·실적이며, 본론의 별도 섹션 주제로 삼지 말고 "
            "화자의 역량·신뢰를 보여주는 보조 근거로만 활용하십시오.\n"
            f"{profile_substitute_context}"
        )
        bio_source_line = "- 보조 자료: 사용자 추가정보(공약/법안/성과) 무작위 3개 + Bio 보강"
        bio_source_rule = (
            "보조자료 활용: 뉴스/데이터가 비어 있으므로 사용자 추가정보를 화자의 역량·신뢰 보강 소재로 활용하되, "
            "본론의 주제는 입장문에 집중하세요. 추가정보 항목을 별도 본론 섹션의 주제로 확장하지 마세요."
        )
    elif profile_support_context:
        source_blocks.append(f"[작성자 BIO 보강 맥락]\n{profile_support_context}")
        bio_source_line = "- 보강 자료: 사용자 Bio (경력/이력/가치)"
        if news_context_text:
            bio_source_rule = (
                "Bio 활용: 본론의 주제는 입장문과 뉴스에서 가져오고, "
                "Bio는 화자의 역량·경력·가치를 보여주는 뒷받침 소재로만 활용하세요. "
                "Bio 항목을 별도 본론 섹션 주제로 확장하지 마세요. "
                "문단 안에서 '저는 이런 경험이 있어 이 정책이 필요하다고 확신합니다' 식으로 "
                "화자 신뢰를 보강하는 1~2문장 뒷받침으로 활용하세요."
            )
        else:
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
    <rule order="1">정보 추출: 참고자료에서는 핵심 팩트, 수치, 논점만 추출해 사용</rule>
    <rule order="2">문장 이식 금지: 참고자료 문장 자체를 원고에 옮기지 않음. 문장은 버리고 사실 정보만 남겨 새 문장으로 다시 씀</rule>
    <rule order="3">보도체 금지: 3인칭 보도 서술("형성되었습니다", "강조하고 있습니다", "나섰습니다", "선정했습니다")은 원고에 사용하지 않음</rule>
    <rule order="4">화자 고정: 화자는 항상 '저'인 1인칭이며, 본인의 이미지·전략·포지셔닝을 외부 시선으로 서술하지 않음("이미지를 구축하며", "이미지를 확고히 구축하며", "당심 잡기에 나서고 있습니다", "민심과 당심을 사로잡기 위해 나섰습니다" 금지)</rule>
    <rule order="5">초안 검토: 초안을 쓴 뒤 기자가 쓴 것처럼 들리는 문장(기관·제3자 주어 + 관찰 동사, "알려져 있습니다", "강조하고 있습니다", "나섰습니다")이 남아 있으면 모두 1인칭 화자 문장으로 다시 쓸 것</rule>
    <rule order="6">구어체를 문어체로 변환</rule>
    <rule order="7">창작 금지: 참고자료에 없는 팩트/수치 생성 금지</rule>
    <rule order="8">주제 유지: 참고자료 핵심 주제 이탈 금지</rule>
    <rule order="9">{_xml_text(bio_source_rule)}</rule>
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
        raw_stance_list = context_analysis.get('mustIncludeFromStance', [])
        stance_list = []
        for item in raw_stance_list if isinstance(raw_stance_list, list) else []:
            if isinstance(item, dict):
                if looks_like_hashtag_bullet_line(item.get('topic')):
                    continue
                stance_list.append(item)
                continue
            if looks_like_hashtag_bullet_line(item):
                continue
            stance_list.append(item)

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
    <instruction order="3">How 단계에서는 필요할 때만 Bio(경력) 한 항목을 근거로 연결하고, 동일한 직함·경력 리스트를 다른 섹션에 다시 나열하지 말 것</instruction>
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

        answer_type = str(context_analysis.get('answer_type') or '').strip()
        central_claim = normalize_context_text(context_analysis.get('central_claim'))
        source_contract = context_analysis.get('source_contract')
        if not isinstance(source_contract, dict):
            source_contract = {}
        contract_answer_type = normalize_context_text(source_contract.get('answer_type'))
        primary_keyword = normalize_context_text(source_contract.get('primary_keyword'))
        if contract_answer_type and not answer_type:
            answer_type = contract_answer_type
        if not central_claim:
            central_claim = normalize_context_text(source_contract.get('central_claim'))
        raw_execution_items = context_analysis.get('execution_items')
        execution_items = [
            normalize_context_text(item)
            for item in raw_execution_items
            if normalize_context_text(item)
        ] if isinstance(raw_execution_items, list) else []
        contract_execution_items = [
            normalize_context_text(item)
            for item in source_contract.get('execution_items', [])
            if normalize_context_text(item)
        ] if isinstance(source_contract.get('execution_items'), list) else []
        for item in contract_execution_items:
            if item not in execution_items:
                execution_items.append(item)
        required_source_facts = [
            normalize_context_text(item)
            for item in source_contract.get('required_source_facts', [])
            if normalize_context_text(item)
        ] if isinstance(source_contract.get('required_source_facts'), list) else []
        forbidden_inferred_actions = [
            normalize_context_text(item)
            for item in source_contract.get('forbidden_inferred_actions', [])
            if normalize_context_text(item)
        ] if isinstance(source_contract.get('forbidden_inferred_actions'), list) else []
        source_sequence_items = [
            normalize_context_text(item)
            for item in source_contract.get('source_sequence_items', [])
            if normalize_context_text(item)
        ] if isinstance(source_contract.get('source_sequence_items'), list) else []
        if answer_type == 'implementation_plan' or execution_items:
            item_lines = "\n".join(
                f'    <item priority="{i + 1}">{_xml_text(item)}</item>'
                for i, item in enumerate(execution_items[:8])
            )
            required_fact_lines = "\n".join(
                f'    <fact priority="{i + 1}">{_xml_text(item)}</fact>'
                for i, item in enumerate(required_source_facts[:10])
            )
            forbidden_lines = "\n".join(
                f'    <item>{_xml_text(item)}</item>'
                for item in forbidden_inferred_actions[:16]
            )
            sequence_lines = "\n".join(
                f'    <item order="{i + 1}">{_xml_text(item)}</item>'
                for i, item in enumerate(source_sequence_items[:10])
            )
            context_injection += f"""
<execution_plan mandatory="true">
  <answer_type>{_xml_text(answer_type or 'implementation_plan')}</answer_type>
  <primary_keyword>{_xml_text(primary_keyword)}</primary_keyword>
  <central_claim>{_xml_text(central_claim)}</central_claim>
  <required_source_facts>
{required_fact_lines or '    <fact>(추출 실패)</fact>'}
  </required_source_facts>
  <execution_items>
{item_lines or '    <item>(추출 실패)</item>'}
  </execution_items>
  <source_sequence_items>
{sequence_lines or '    <item>(추출 실패)</item>'}
  </source_sequence_items>
  <forbidden_inferred_actions>
{forbidden_lines or '    <item>(없음)</item>'}
  </forbidden_inferred_actions>
  <rules>
    <rule priority="critical">이 글은 정책 일반론이 아니라 위 실행 항목을 답하는 실행안입니다.</rule>
    <rule priority="critical">required_source_facts는 사용자 입력 텍스트의 재료입니다. 누락하지 말고 본론에 모두 반영하십시오.</rule>
    <rule priority="critical">source_sequence_items는 원문 실행 순서입니다. 본론 섹션마다 서로 다른 항목 묶음을 배정하고 같은 항목을 여러 섹션에서 반복하지 마십시오.</rule>
    <rule priority="critical">본문의 절반 이상을 execution_items의 실행 항목 설명에 배정하십시오.</rule>
    <rule priority="critical">forbidden_inferred_actions에 있는 수치·조직·사업 방식은 사용자 입력에 없으므로 새 공약처럼 쓰지 마십시오.</rule>
    <rule priority="critical">leadership.py의 상위 원칙은 허용되지만, 같은 문단 안에서 required_source_facts나 execution_items의 구체 실행수단과 직접 연결될 때만 사용하십시오. 상위 원칙만 독립 문단으로 늘어놓지 마십시오.</rule>
    <rule priority="critical">결론은 central_claim과 execution_items 중 최소 3개를 다시 묶어 닫으십시오.</rule>
  </rules>
</execution_plan>
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
    role_warning = generate_role_warning_bundle(
        user_profile=user_profile,
        author_bio=params.get('authorBio', ''),
    )
    if role_warning:
        warning_blocks.append(role_warning)

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
    poll_focus_bundle_section = build_poll_focus_bundle_section(
        params.get('pollFocusBundle') if isinstance(params.get('pollFocusBundle'), dict) else {}
    )

    author_name = str(params.get('authorName') or '').strip()
    author_position = str(user_profile.get('position') or '').strip()
    if author_name and author_position:
        greeting_example = f'예: "안녕하세요, {author_position} {author_name}입니다."'
    elif author_name:
        greeting_example = f'예: "안녕하세요, {author_name}입니다."'
    else:
        greeting_example = '예: "안녕하세요, [직함] [이름]입니다."'

    if uses_aeo_answer_first(writing_method):
        intro_line_1 = (
            f'<p>1문단: 화자 직함+실명 자기소개(1문장 이내, {greeting_example}) 직후, '
            '이 글의 핵심 결론·주장·답변을 같은 문단에서 바로 선언. '
            'AI 답변 엔진이 첫 문단만 추출해도 독자 질문에 답이 되어야 한다</p>'
        )
        intro_line_2 = '<p>2문단: 핵심 결론을 뒷받침하는 근거 1~2개를 압축 제시, 본론 전개 방향 예고</p>'
        intro_line_3 = '<p>3문단: 필수. 구체 근거·행동 보완과 본론 예고를 완결 문단으로 작성</p>'
    else:
        intro_line_1 = '<p>1문단: 입장문/페이스북 글의 핵심 주장으로 바로 시작하고 자기소개는 1문장 이내로 제한</p>'
        intro_line_2 = '<p>2문단: 입장문 핵심 주장(원문 요지)과 본론에서 다룰 해결 방향을 자연스럽게 연결</p>'
        intro_line_3 = '<p>3문단: 필수. 앞 문단과 이어지는 구체 근거·행동과 본론 예고를 완결 문단으로 작성</p>'

    aeo_answer_first_rule = ''
    if uses_aeo_answer_first(writing_method):
        aeo_answer_first_rule = '    <rule id="aeo_answer_first">서론 첫 문단은 화자 실명+직함 자기소개(1문장) + 핵심 결론(1~2문장)을 한 문단으로 구성할 것. 질문/배경/맥락으로 시작하지 말 것.</rule>\n'

    if uses_aeo_answer_first(writing_method):
        intro_stance_rules = f"""
  <intro_stance_binding priority="critical">
    <rule id="intro_greeting_then_stance">서론 첫 문장은 화자 직함+실명 자기소개(1문장 이내, {greeting_example})로 시작하고, 같은 문단 안에서 바로 핵심 결론·주장을 선언할 것. 호격("여러분")만으로는 인삿말이 아니다 — 반드시 직함과 이름을 밝혀야 한다.</rule>
    <rule id="intro_must_anchor_stance">서론 2문단 이내에 입장문 핵심 주장 또는 문제의식을 반드시 재진술할 것.</rule>
    {aeo_answer_first_rule}<rule id="intro_paraphrase_required">입장문 문장을 그대로 복붙하지 말고 의미는 유지한 채 재작성할 것.</rule>
    <rule id="intro_profile_cap">서론 전체에서 경력/이력 나열은 최대 2문장으로 제한할 것.</rule>
    <rule id="career_list_once_only">같은 직함·경력 리스트는 원고 전체에서 한 번만 쓰고, 이후 섹션에서는 그 경험을 바탕으로 한 판단·행동·성과만 이어갈 것.</rule>
    <rule id="intro_to_body_bridge">서론 마지막 문장에서 본론 주제로 자연스럽게 연결할 것.</rule>
    <stance_seed>{intro_seed or '(입장문 요지 없음)'}</stance_seed>
    <stance_anchor_topic>{intro_anchor_topic or '(미지정)'}</stance_anchor_topic>
  </intro_stance_binding>
"""
    else:
        intro_stance_rules = f"""
  <intro_stance_binding priority="critical">
    <rule id="intro_must_anchor_stance">서론 2문단 이내에 입장문 핵심 주장 또는 문제의식을 반드시 재진술할 것.</rule>
    <rule id="intro_first_sentence_from_stance">서론 첫 문장은 stance_seed를 바탕으로 재구성하고, 일반 인삿말로 시작하지 말 것.</rule>
    <rule id="intro_no_generic_opening">맥락 없는 일반 인삿말/상투적 도입으로 시작하지 말 것.</rule>
    <rule id="intro_paraphrase_required">입장문 문장을 그대로 복붙하지 말고 의미는 유지한 채 재작성할 것.</rule>
    <rule id="intro_profile_cap">서론 전체에서 경력/이력 나열은 최대 2문장으로 제한할 것.</rule>
    <rule id="career_list_once_only">같은 직함·경력 리스트는 원고 전체에서 한 번만 쓰고, 이후 섹션에서는 그 경험을 바탕으로 한 판단·행동·성과만 이어갈 것.</rule>
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

    shared_contract_rule_lines = "\n".join(
        f'    <rule order="{idx + 3}">{_xml_text(rule)}</rule>'
        for idx, rule in enumerate(build_shared_contract_rules())
    )
    genre_contract = f"""
  <genre_contract name="정치인 블로그 글 기본 규칙">
    <identity>정치인이 직접 쓰는 블로그 글이다.</identity>
    <rule order="1">경험과 사실을 말하고, 그 의미에 대한 최종 판단은 독자에게 맡길 것.</rule>
    <rule order="2">독자 반응을 대신 해석하거나 화자의 역량을 스스로 인증하지 말고, 확인 가능한 사실과 행동을 우선 쓸 것.</rule>
{shared_contract_rule_lines}
  </genre_contract>
""".strip()

    section_lane_rules = ""
    if category in {"activity-report", "policy-proposal"}:
        section_lane_rules = """
  <section_lane_rules priority="high">
    <rule id="section_lane_achievement_only">입법·조례·예산·성과 섹션에는 이미 수행한 성과와 그 효과만 쓰고, "하겠습니다/추진하겠습니다/완성하겠습니다"류 미래 과제 문장은 넣지 말 것.</rule>
    <rule id="section_lane_future_only">미래·비전·과제·방향 섹션에서만 앞으로의 실행 과제와 약속을 집중적으로 설명할 것.</rule>
    <rule id="section_lane_no_mix">같은 섹션 안에 과거 성과 설명과 앞으로의 신규 과제를 장문으로 섞지 말고, 미래 과제는 별도 섹션으로 분리할 것.</rule>
  </section_lane_rules>
""".strip()

    if uses_aeo_answer_first(writing_method):
        expansion_guide = f"""<expansion_guide name="섹션별 두괄식 4단계 (AEO)" priority="high">
    각 본론 섹션의 첫 문장에서 해당 섹션의 핵심 주장·해법·결론을 바로 선언하십시오.
    <step name="Answer" sentences="1~2">이 섹션이 전달할 핵심 주장·해법·결론을 첫 문장에서 직접 밝힌다</step>
    <step name="Evidence" sentences="2">주장을 뒷받침하는 데이터·사례·과거 성과를 제시</step>
    <step name="Context" sentences="1">배경·현황·시민 체감 상황을 간결히 보충</step>
    <step name="Effect+Trust" sentences="1">변화될 {user_region}의 미래 청사진을 명확히 제시</step>
  </expansion_guide>"""
    else:
        expansion_guide = f"""<expansion_guide name="섹션별 작성 4단계">
    각 본론 섹션을 아래 흐름으로 밀도 있게 전개하십시오.
    <step name="Why" sentences="1~2">시민들이 겪는 실제 불편함과 현장의 고충을 구체적으로 진단</step>
    <step name="How+Expertise" sentences="2">실현 가능한 해결책 제시 및 본인의 Bio(경력)는 한 번만 근거로 연결하고, 동일한 경력 리스트 재나열 없이 전문성의 의미만 이어 설명</step>
    <step name="Authority" sentences="1">과거 성과나 네트워크를 바탕으로 실행 능력을 증명</step>
    <step name="Effect+Trust" sentences="1~2">변화될 {user_region}의 미래 청사진을 명확히 제시</step>
  </expansion_guide>"""

    structure_enforcement = f"""
<structure_guide mode="strict">
  <strategy>E-A-T (전문성-권위-신뢰) 전략으로 작성</strategy>

  <volume warning="위반 시 시스템 오류">
    <per_section min="{per_section_min}" max="{per_section_max}" recommended="{per_section_recommended}"/>
    <paragraphs_per_section>{STRUCTURE_SPEC['paragraphsPerSection']}개 문단, 문단당 {STRUCTURE_SPEC['paragraphCharMin']}~{STRUCTURE_SPEC['paragraphCharMax']}자</paragraphs_per_section>
    <total sections="{total_section_count}" min="{min_total_chars}" max="{max_total_chars}"/>
    <caution>총 분량 상한을 넘기지 않도록 중복 문장과 장황한 수식어를 제거하고, 근거 중심으로 간결하게 작성하십시오.</caution>
  </volume>

  <paragraph_structure priority="critical">
    모든 섹션(서론·본론·결론)은 반드시 3개 문단으로 구성하십시오. 각 문단은 110~140자(2~3문장), 한 섹션 전체는 330~420자입니다.
    본론 각 섹션 3문단: (1) 주장 선언 (110~140자) (2) 구체 근거·수치·사례 + 인과관계 서술 (110~140자) (3) 의미 부여 — '그래서 왜 중요한가'에 답하는 마감 (110~140자).
    서론 3문단: (1) 화자 소개+핵심 결론 (110~140자) (2) 배경·맥락 (110~140자) (3) 본론 예고 (110~140자).
    결론 3문단: (1) 핵심 결론 재확인 (110~140자) (2) 다짐·시사점·행동계획 (110~140자) (3) 지지 호소 + 인삿말 (110~140자).
    사실만 나열하고 끝나는 문단, 한두 문장으로 끝나는 문단, 2문단 이하로 끝나는 섹션은 불합격입니다.
    각 섹션의 첫 문장(= 첫 번째 문단의 첫 문장)을 접속사('또한/아울러/나아가/한편/더불어')나 지시 대명사('이·그·저' 계열: 이는, 이것은, 이러한, 이와 같은, 이를 통해 등)로 시작하지 마십시오. 각 섹션은 해당 섹션의 핵심 주어·주제어로 독립적으로 시작하십시오.
    2·3번째 문단의 첫 문장에서도 '이는/이러한/이것은' 등 지시 대명사 대신 구체적 주어(정책명·제도명·지역명 등)를 사용하십시오. 예: "이는 사회 전체의 투자입니다" → "지역화폐 정책은 사회 전체의 투자입니다". 구체적 주어로 시작하면 문장이 독립적으로 의미를 전달하고 분량 확장에도 도움이 됩니다.
  </paragraph_structure>

  {expansion_guide}

  {section_lane_rules}

  <sections total="{total_section_count}">
    <intro paragraphs="3" chars="{per_section_recommended}" heading="없음">
      {intro_line_1}
      {intro_line_2}
      {intro_line_3}
    </intro>
    {body_structure_str}
    <conclusion order="{total_section_count}" paragraphs="{STRUCTURE_SPEC['paragraphsPerSection']}" chars="{per_section_recommended}" heading="h2 필수"/>
  </sections>

  {build_h2_rules('aeo')}

  {genre_contract}

  <mandatory_rules>
    <rule id="html_tags">소제목은 &lt;h2&gt;, 문단은 &lt;p&gt; 태그만 사용 (마크다운 문법 금지)</rule>
    <rule id="defer_output_addons" severity="critical">슬로건/후원 안내(계좌·예금주·연락처·영수증 안내)는 본문에 쓰지 말 것. 해당 정보는 최종 출력 직전에 시스템이 자동 부착.</rule>
    <rule id="no_slogan_repeat" severity="critical">입장문의 맺음말/슬로건을 각 섹션 끝마다 반복 금지. 모든 호소와 다짐은 맨 마지막 결론부에만.</rule>
    <rule id="sentence_completion">문장은 올바른 종결 어미(~입니다, ~합니다, ~시오)로 끝내야 함. 고의적 오타/잘린 문장 금지.</rule>
    <rule id="keyword_per_section">키워드는 내용과 관련된 섹션에만 자연스럽게 배치. 무관한 섹션에 억지로 삽입하여 문법을 깨뜨리지 말 것. 총 횟수만 충족하면 됨.</rule>
    <rule id="separate_pledges">각 본론 섹션은 서로 다른 주제/공약을 다룰 것</rule>
    <rule id="verb_diversity" severity="critical">같은 동사(예: "던지면서")를 원고 전체에서 {int(QUALITY_SPEC['verbRepeatMax']) + 1}회 이상 사용 금지. 동의어 교체: 제시하며, 약속하며, 열며, 보여드리며 등.</rule>
    <rule id="slogan_once">캐치프레이즈("청년이 돌아오는 부산")나 비유("아시아의 싱가포르")는 결론부 {QUALITY_SPEC['sloganMax']}회만. 다른 섹션에서는 변형 사용.</rule>
    <rule id="natural_keyword">키워드는 정보 문장이 아니라 맥락 문장으로 삽입. 키워드 문장에는 최소 1개 이상 포함: 행사 정보(일시/장소/참여 방법), 대화 주제, 시민 행동 제안. 해당 문단의 주장/근거와 결합해 쓰고, 키워드만으로 된 장식/단독 문장 금지.</rule>
    <rule id="no_single_sentence_echo">같은 구조의 단문 문장을 섹션 말미마다 반복 금지. 특히 "이 만남은 ~", "이 자리는 ~", "이 뜻깊은 자리는 ~", "이번 만남은 ~" 패턴은 한 번만 사용.</rule>
    <rule id="no_datetime_location_ngram_repeat">일시+장소가 함께 들어간 구문(예: "3월 1일(일) 오후 2시, 서면...")은 같은 어순으로 3회 이상 반복 금지. 2회를 넘으면 어순/표현을 반드시 변형할 것.</rule>
    <rule id="no_meta_prompt_leak">프롬프트/규칙 설명 문장을 본문에 복사하지 말 것. "문제는~점검" 같은 규칙성 메타 문장 생성 금지.</rule>
    <rule id="paragraph_min_sentences">원칙적으로 각 &lt;p&gt;는 최소 2문장으로 구성. 예외는 결론의 마지막 CTA 문단 1개만 허용.</rule>
    <rule id="intro_fragment_guard">서론은 반드시 3문단으로 쓰되, 1문장짜리 짧은 문단 3개로 쪼개지 말 것. "특히", "앞으로도", "또한", "이와 함께"로 시작하는 문단은 앞 문단과 의미가 자연스럽게 이어지더라도 독립된 완결 문단으로 작성할 것.</rule>
    <rule id="causal_clarity">성과 언급 시 본인의 구체적 역할/직책 명시. "40% 득표율을 이끌어냈다" → "시당위원장으로서 지역 조직을 총괄하며 40% 득표율 달성에 기여했습니다"</rule>
    <rule id="h2_semantic_uniqueness">같은 의미를 다른 말로 반복하지 말 것. 같은 주제를 둘로 쪼개지 말고, 각 본론 H2는 서로 다른 질문과 직접 답을 가져야 한다.</rule>
    <rule id="no_self_certification_claim">근거 문장 없이 '유일한 후보', '최고의 후보', '인정한 결과', '인정받은 결과', '완벽하게 준비되어 있습니다' 같은 자기 단정 표현을 쓰지 말 것. 자평이 필요하면 반드시 앞 문장의 사실 근거를 먼저 제시할 것.</rule>
    <rule id="section_continuity">새 섹션 첫 문장은 직전 섹션의 흐름과 자연스럽게 이어질 것. "이는", "이러한", "이것은"으로 시작하려면 직전 섹션에 지시 대상이 실제로 있어야 하며, 없으면 명시적 주어로 다시 쓸 것.</rule>
    <rule id="observer_voice_final_check">초안 완성 후 전체 원고를 다시 읽고 기관·제3자 주어로 대상을 관찰하는 보도체 문장은 모두 1인칭 화자 문장으로 재작성할 것.</rule>
  </mandatory_rules>
{material_uniqueness_guard}
{poll_focus_bundle_section}
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
    # 중앙 상투어 대체어 사전 로드
    global_alt = _load_global_alternatives()

    style_generation_guard = _build_style_generation_guard(
        style_fingerprint=style_fingerprint,
        style_guide=style_guide,
        user_profile=user_profile,
        generation_profile=generation_profile,
        global_alternatives=global_alt,
    )

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
    writing_principles = build_writing_principles_xml()
    leadership_philosophy = build_leadership_philosophy_xml()

    return f"""
<structure_agent_prompt version="xml-v1">
  <template_prompt>{_xml_cdata(template_prompt)}</template_prompt>
  <party_stance_guide>{_xml_cdata(party_stance_guide)}</party_stance_guide>
  <seo_instruction>{_xml_cdata(seo_instruction)}</seo_instruction>
  <election_instruction>{_xml_cdata(election_instruction)}</election_instruction>
  {bio_warning}
  {ref_section}
  {context_injection_xml}
  {structure_enforcement}
  {leadership_philosophy}
  {style_generation_guard}
  {writing_principles}
  {natural_tone_guide}
</structure_agent_prompt>
""".strip()


__all__ = [
    'TEMPLATE_BUILDERS',
    'build_retry_directive',
    'build_structure_prompt',
    'build_style_role_priority_summary',
    'is_current_lawmaker',
]
