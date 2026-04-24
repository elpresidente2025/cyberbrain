import json
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
import time

# Local Imports
from ..templates.daily_communication import build_daily_communication_prompt
from ..templates.policy_proposal import build_policy_proposal_prompt
from ..templates.activity_report import build_activity_report_prompt
from ..templates.bipartisan_cooperation import build_bipartisan_cooperation_prompt
from ..templates.current_affairs import build_critical_writing_prompt, build_diagnosis_writing_prompt
from ..templates.local_issues import build_local_issues_prompt
from ..templates.offline_engagement import build_offline_engagement_prompt

from ..common.theminjoo import get_party_stance
from ..common.election_rules import get_election_stage, resolve_election_context
from ..common.style_analyzer import extract_style_from_text
from ..common.stance_filters import (
    looks_like_hashtag_bullet_line,
    normalize_stance_text as normalize_stance_text_common,
)
from ..common.warnings import generate_non_lawmaker_warning, generate_family_status_warning
from ..common.constants import resolve_writing_method
from ..common.xml_builder import (
    build_context_analysis_section,
    build_scope_warning_section,
    build_tone_warning_section,
    build_style_guide_section,
    build_writing_rules_section,
    build_reference_section,
    build_sandwich_reminder_section,
    build_output_protocol_section,
    build_retry_section
)
from ..common.xml_parser import parse_ai_response

logger = logging.getLogger(__name__)

# Template Builders Mapping
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

STANCE_META_SOURCE_CUE_PATTERN = re.compile(
    r"(?:\b(?:KBS|MBC|SBS|JTBC|TV조선|채널A|YTN|KNN|연합뉴스|뉴시스|뉴스1)\b|뉴스)",
    re.IGNORECASE,
)
STANCE_META_TIME_CUE_PATTERN = re.compile(
    r"(?:\d{4}[./-]\d{1,2}[./-]\d{1,2}|\d{1,2}월\s*\d{1,2}일|\d{1,2}시(?:\s*\d{1,2}분)?|\d{1,2}:\d{2})"
)
STANCE_META_LABEL_CUE_PATTERN = re.compile(
    r"(?:방송분|기사|보도|앵커|기자|CG|촬영|편집|입력|수정)",
    re.IGNORECASE,
)
STANCE_BRANDING_CERTAINTY_PATTERN = re.compile(
    r"(?:충분히|반드시|끝내|기필코|확실히).*(?:이깁니다|승리합니다|해냅니다|해낼\s*수\s*있습니다|됩니다)"
)
STANCE_BRANDING_RECOGNITION_PATTERN = re.compile(
    r"(?:조금씩|점점|확실히|분명히).*(?:알려지고|주목받고|인지도가)"
)


def _build_dynamic_tone_matrix(author_name: str) -> str:
    """JS prompts.js의 Dynamic Tone Matrix (Type A/B/C/D) 이식.

    상대방의 '행위'에 따라 4가지 톤 중 하나를 선택하도록 LLM에 지시하는 프롬프트 섹션.
    """
    return f"""<dynamic-tone-matrix priority="high">
  <title>Dynamic Tone Matrix — 동적 대응 매뉴얼</title>
  <rule>상대방이 누구냐보다, **"무엇을 했느냐(행위)"**에 따라 아래 A~D 4가지 톤 중 하나를 반드시 선택하여 적용하십시오.</rule>

  <type id="A" name="사필귀정">
    <trigger>상대방의 헌정 파괴, 중범죄, 사법 리스크 (사형 구형, 계엄, 탄핵 등)</trigger>
    <stance>"범죄(원인)는 비판하되, 처벌(결과)은 환영한다"</stance>
    <tone>냉철, 엄중, 정의로움</tone>
    <keywords>사필귀정, 엄중한 심판, 법치주의 실현, 당연한 결과</keywords>
    <forbidden>"사형 구형 소식에 마음이 무겁다", "안타깝다", "헌정이 흔들린다" — 범죄자를 옹호하는 뉘앙스 절대 금지</forbidden>
    <required-logic>헌정 질서를 파괴한 것은 그들의 범죄(원인)이며, 이번 구형은 이를 바로잡는 정의(결과)다.</required-logic>
  </type>

  <type id="B" name="절제된 인정">
    <trigger>상대방의 소신 발언, 내부 비판, 원칙 준수 (쓴소리, 용기 있는 행동)</trigger>
    <stance>"1~2문장만 인정 후, 즉시 자기PR로 복귀"</stance>
    <tone>절제된 인정</tone>
    <keywords>높이 평가한다, 주목할 만하다</keywords>
    <limit>칭찬은 1~2문장으로 끝내고 반드시 {author_name} 자신의 PR로 복귀</limit>
    <forbidden>"~의 정신을 이어받아", "~에게 배워야", "~의 뜻을 받들어", "깊은 울림", "용기에 박수", "배울 점"</forbidden>
  </type>

  <type id="C" name="정책 견제">
    <trigger>일반적인 정쟁, 정책 차이, 단순 행보</trigger>
    <stance>"정중하지만 날선 비판과 대안 제시"</stance>
    <tone>논리적 비판, 견제</tone>
    <keywords>유감입니다, 재고해야 합니다, 의문입니다, 건강한 경쟁</keywords>
  </type>

  <type id="D" name="인류애">
    <trigger>재난, 사고, 사망, 국가적 비극</trigger>
    <stance>"정쟁 중단, 무조건적 위로"</stance>
    <tone>애도, 슬픔, 위로</tone>
    <keywords>참담한 심정, 깊은 애도, 명복을 빕니다</keywords>
  </type>
</dynamic-tone-matrix>"""


def _normalize_stance_text(value: Any) -> str:
    return normalize_stance_text_common(value)


def _compact_stance_text(value: Any) -> str:
    return re.sub(r'[^0-9A-Za-z가-힣]', '', _normalize_stance_text(value))


def _normalize_person_hint(value: Any) -> str:
    return re.sub(r'\s+', '', re.sub(r'[^0-9A-Za-z가-힣\s]', '', str(value or ''))).strip()


def _looks_like_stance_meta_line(candidate: Any) -> bool:
    normalized = _normalize_stance_text(candidate)
    if not normalized:
        return False

    stripped = normalized.lstrip('*-• ').strip()
    if re.fullmatch(r'(?:앵커|기자|CG)\s*[가-힣A-Za-z]{2,12}', stripped, re.IGNORECASE):
        return True

    has_source = bool(STANCE_META_SOURCE_CUE_PATTERN.search(stripped))
    has_time = bool(STANCE_META_TIME_CUE_PATTERN.search(stripped))
    has_label = bool(STANCE_META_LABEL_CUE_PATTERN.search(stripped))
    if stripped != normalized and (has_source or has_time or has_label):
        return True
    if has_source and (has_time or has_label):
        return True
    if re.fullmatch(r'(?:입력|수정)\s*:?\s*.+', stripped) and has_time:
        return True
    return False


def _looks_like_branding_stance_line(candidate: Any, author_name: Any = "") -> bool:
    normalized = _normalize_stance_text(candidate)
    compact = _compact_stance_text(normalized)
    author = _normalize_person_hint(author_name)
    if not compact or not author:
        return False
    if author not in compact:
        return False
    if '는' in compact and compact.endswith(f'{author}입니다'):
        return True
    if STANCE_BRANDING_CERTAINTY_PATTERN.search(normalized):
        return True
    if STANCE_BRANDING_RECOGNITION_PATTERN.search(normalized):
        return True
    return False


def _should_keep_must_include_stance(candidate: Any, author_name: Any = "") -> bool:
    normalized = _normalize_stance_text(candidate)
    if len(normalized) < 8:
        return False
    if normalized.startswith(('⚠️', '우선순위:', '예시 패턴:', '→ 실제')):
        return False
    if looks_like_hashtag_bullet_line(normalized):
        return False
    if _looks_like_stance_meta_line(normalized):
        return False
    if _looks_like_branding_stance_line(normalized, author_name):
        return False
    return True


def _build_opening_hook_policy_block() -> str:
    """정치 안전형 첫 문단 후킹 정책 XML 블록.

    main template 앞에 주입해서 LLM 이 "이 제약 안에서 템플릿을 실행한다"는
    상위 원칙으로 읽도록 한다. 지역명·인물명 하드코드 없음.
    """
    return (
        '<opening-hook-policy priority="high">\n'
        '  <principle>첫 문단은 과장·폭로·공포가 아니라 주민 생활과 연결되는 문제의식으로 시작한다.</principle>\n'
        '  <banned>충격, 경악, 망합니다, 진실, 비밀, 아무도 말하지 않는, 상대가 숨기는</banned>\n'
        '  <track type="aeo_first" when="본문에 정책명·수치·비교 재료가 있을 때">\n'
        '    <example>[정책명]이 주민 생활에 어떤 변화를 가져오는지 차분히 설명드립니다.</example>\n'
        '    <example>이번 사안은 [이슈]와 직접 연결되어 있어 구체적으로 살펴볼 필요가 있습니다.</example>\n'
        '  </track>\n'
        '  <track type="engagement_first" when="현장·서사·주민 불편 중심일 때">\n'
        '    <example>주민 여러분이 반복해서 말씀하신 불편부터 살펴보겠습니다.</example>\n'
        '    <example>현장의 목소리를 바탕으로 개선 방향을 정리했습니다.</example>\n'
        '  </track>\n'
        '</opening-hook-policy>'
    )


class WriterAgent:
    def __init__(self):
        from ..common.gemini_client import get_client, DEFAULT_MODEL
        self.model_name = DEFAULT_MODEL
        self._client = get_client()

    def get_required_context(self) -> List[str]:
        return ['topic', 'category', 'userProfile']

    def _material_key(self, text: Any) -> str:
        raw = re.sub(r'<[^>]*>', ' ', str(text or ''))
        raw = re.sub(r'\s+', ' ', raw).strip().lower()
        raw = re.sub(r'["\'`“”‘’\[\]\(\)<>]', '', raw)
        raw = re.sub(r'[\s\.,!?;:·~\-_\\/]+', '', raw)
        return raw

    def _dedupe_material_lists(
        self,
        facts: List[str],
        stances: List[str],
        quotes: List[str],
    ) -> Tuple[List[str], List[str], List[str]]:
        def dedupe(values: List[str], blocked: Optional[set[str]] = None, max_items: int = 8) -> Tuple[List[str], set[str]]:
            blocked_keys = blocked or set()
            results: List[str] = []
            keys: set[str] = set()
            for item in values:
                text = re.sub(r'\s+', ' ', str(item or '')).strip()
                if len(text) < 8:
                    continue
                key = self._material_key(text)
                if not key or key in blocked_keys or key in keys:
                    continue
                keys.add(key)
                results.append(text)
                if len(results) >= max_items:
                    break
            return results, keys

        stance_list, stance_keys = dedupe(stances, max_items=6)
        fact_list, fact_keys = dedupe(facts, blocked=stance_keys, max_items=8)
        quote_list, _quote_keys = dedupe(quotes, blocked=stance_keys.union(fact_keys), max_items=8)
        return fact_list, stance_list, quote_list

    def _build_material_uniqueness_section(
        self,
        stances: List[str],
        facts: List[str],
        quotes: List[str],
    ) -> str:
        cards: List[Tuple[str, str]] = []
        seen: set[str] = set()

        def add_card(card_type: str, text: str) -> None:
            normalized = re.sub(r'\s+', ' ', str(text or '')).strip()
            if len(normalized) < 8:
                return
            key = self._material_key(normalized)
            if not key or key in seen:
                return
            seen.add(key)
            cards.append((card_type, normalized))

        for item in stances:
            add_card('stance', item)
        for item in facts:
            add_card('fact', item)
        for item in quotes:
            add_card('quote', item)

        if not cards:
            return ''

        lines: List[str] = []
        for idx, (card_type, text) in enumerate(cards[:8]):
            lines.append(f'  <material id="M{idx + 1}" type="{card_type}">{text}</material>')
        material_lines = '\n'.join(lines)

        return f"""<material-uniqueness priority="critical">
  <rule>같은 소재(인용문/일화/근거)를 두 번 이상 반복하지 마세요.</rule>
  <rule>본론 각 섹션은 서로 다른 소재 카드를 사용하세요.</rule>
  <rule>각 소재 카드는 원고 전체에서 1회만 사용하세요.</rule>
{material_lines}
</material-uniqueness>"""

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        # Unpack context
        topic = context.get('topic')
        category = context.get('category')
        sub_category = context.get('subCategory', '')
        user_profile = context.get('userProfile', {})
        memory_context = context.get('memoryContext', '')
        instructions = context.get('instructions', '')
        news_context = context.get('newsContext', '')
        target_word_count = context.get('targetWordCount', 2000)
        user_keywords = context.get('userKeywords', [])
        previous_results = context.get('previousResults', {})
        
        if not self._client:
            raise ValueError("Gemini API Key missing")

        logger.info(f"🔍 [WriterAgent] Input: instructions_len={len(instructions)}, news_len={len(news_context)}")

        # 1. Keyword Result (from Context)
        keyword_result = previous_results.get('KeywordAgent')
        context_keywords = []
        if keyword_result and 'data' in keyword_result:
            context_keywords = keyword_result['data'].get('keywords', [])
        elif kwargs_context_keywords := context.get('contextKeywords'): # Fallback if passed directly
             context_keywords = kwargs_context_keywords
             
        # Extract keyword strings
        context_keyword_strings = []
        for k in context_keywords[:5]:
             if isinstance(k, dict):
                 context_keyword_strings.append(k.get('keyword', ''))
             else:
                 context_keyword_strings.append(str(k))
        
        # 2. Style Analysis
        style_prompt = ''
        style_profile = user_profile.get('styleProfile')
        if not style_profile and user_profile.get('bio'):
            try:
                logger.info("ℹ️ [WriterAgent] Doing real-time style analysis")
                style_profile = await extract_style_from_text(user_profile['bio'])
            except Exception as e:
                logger.warning(f"❌ Style analysis failed: {e}")
        
        if style_profile:
            metrics = style_profile.get('metrics', {})
            sentence_len = metrics.get('sentence_length', {})
            ending_patterns = metrics.get('ending_patterns', {})
            
            style_prompt = f"""
- **어조 및 태도**: {style_profile.get('tone_manner', '정보 없음')} (기계적인 문체가 아닌, 작성자의 고유한 톤을 모방하십시오.)
- **시그니처 키워드**: [{', '.join(style_profile.get('signature_keywords', []))}] - 이 단어들을 적재적소에 사용하여 작성자의 정체성을 드러내십시오.
- **문장 호흡**: 평균 {sentence_len.get('avg', 40)}자 내외의 {sentence_len.get('distinct', '문장')} 사용.
- **종결 어미**: 주로 {', '.join(ending_patterns.get('ratios', {}).keys())} 사용.
- **금지 문체**: {style_profile.get('forbidden_style', '어색한 번역투')} 사용 금지.
"""

        # 3. Writing Method
        writing_method = resolve_writing_method(category, sub_category)
        
        # 4. Author Bio
        author_bio = self.build_author_bio(user_profile)
        author_name = user_profile.get('name', '')
        
        # 5. Template Builder
        template_builder = TEMPLATE_BUILDERS.get(writing_method, build_daily_communication_prompt)
        
        prompt_kwargs = {
            'topic': topic,
            'authorBio': author_bio,
            'authorName': author_name,
            'instructions': instructions,
            'keywords': context_keyword_strings,
            'targetWordCount': target_word_count,
            'personalizedHints': memory_context,
            'newsContext': news_context,
            'isCurrentLawmaker': self.is_current_lawmaker(user_profile),
            'politicalExperience': user_profile.get('politicalExperience', '정치 신인'),
            'familyStatus': user_profile.get('familyStatus', ''),
            'negativePersona': previous_results.get('WriterAgent', {}).get('_opponentName') or context.get('_opponentName'),
            # For specific templates
            'validTargetCount': target_word_count, # Alias
            'relevantExample': news_context if writing_method == 'critical_writing' else '', # Hack for critical writing arg
        }
        
        # Check template signature to pass supported args only? 
        # Python keyword args handle this gracefully if we pass **kwargs, but we need to match function signatures.
        # My python port uses specific named arguments. 
        # I'll pass relevant ones. The templates I ported accept specific args.
        # I will build a common dict and let them unpack or handle it.
        # Actually in Python `build_X(options)` where options is a dict/object is how I ported it?
        # Checking `daily_communication.py`: `def build_daily_communication_prompt(options: Dict[str, Any]) -> str:`
        # Yes, they all take `options` dict.
        
        prompt = template_builder(prompt_kwargs)
        
        # 5.5 Party Stance
        party_stance_guide = None
        try:
            party_stance_guide = await get_party_stance(topic)
        except Exception as e:
            logger.warning(f"⚠️ Party stance lookup failed: {e}")
            
        # 5.6 Election Compliance — 동적 스테이지 결정 + 프롬프트 사전 주입
        status = context.get('status') or user_profile.get('status', 'active')
        election_ctx = resolve_election_context(status, user_profile)
        context['_electionContext'] = election_ctx  # ComplianceAgent 등 후속 노드에서 재사용
        logger.info(
            f"📋 [WriterAgent] Election context: stage={election_ctx['stage_name']}, "
            f"phase={election_ctx['phase']}, D-{election_ctx.get('days_until_election', '?')}, "
            f"campaign_unlocked={election_ctx['campaign_unlocked']}, blocked={election_ctx['blocked']}"
        )

        # 6. Assemble Prompt Sections
        prompt_sections = []
        must_include_for_sandwich = ''
        material_uniqueness_section = ''

        # 6.0 Election compliance instruction (프롬프트 최상단 주입)
        election_instruction = election_ctx.get('prompt_instruction', '')
        if election_instruction:
            prompt_sections.append(election_instruction)
        
        # 6.1 Context Analyzer
        use_context_analyzer = True
        context_analysis = {}
        
        if (instructions or news_context) and use_context_analyzer:
            source_text = '\n'.join(filter(None, [instructions, news_context]))
            if len(source_text) >= 100:
                try:
                    logger.info('🔍 [WriterAgent] ContextAnalyzer start...')
                    context_analysis = await self.run_context_analyzer(source_text, author_name)
                    
                    if context_analysis and (context_analysis.get('mainEvent') or context_analysis.get('authorStance')):
                         # Process results
                         facts = context_analysis.get('mustIncludeFacts') or []

                         raw_stance = context_analysis.get('mustIncludeFromStance') or []
                         # Filter logic from JS (+ dict 호환)
                         filtered_stance: List[str] = []
                         for item in raw_stance:
                             candidate = ""
                             if isinstance(item, dict):
                                 candidate = str(item.get('topic') or '').strip()
                             elif isinstance(item, str):
                                 candidate = item.strip()

                             normalized_candidate = _normalize_stance_text(candidate)
                             if _should_keep_must_include_stance(normalized_candidate, author_name):
                                 filtered_stance.append(normalized_candidate)

                         news_quotes = context_analysis.get('newsQuotes') or []
                         facts, filtered_stance, news_quotes = self._dedupe_material_lists(
                             facts,
                             filtered_stance,
                             news_quotes,
                         )
                         context_analysis['mustIncludeFacts'] = facts
                         context_analysis['mustIncludeFromStance'] = filtered_stance
                         context_analysis['newsQuotes'] = news_quotes
                         must_include_text = '\n'.join([f"{i+1}. {f}" for i, f in enumerate(facts)])
                         must_include_stance_text = '\n'.join([f'{i+1}. "{f}"' for i, f in enumerate(filtered_stance)])
                         news_quotes_text = '\n'.join([f"{i+1}. {q}" for i, q in enumerate(news_quotes)])

                         # Save to context for validaiton
                         context['_extractedKeyPhrases'] = filtered_stance
                         context['_responsibilityTarget'] = context_analysis.get('responsibilityTarget')
                         context['_expectedTone'] = context_analysis.get('expectedTone')
                         context['_opponentName'] = context_analysis.get('opponentName')

                         material_uniqueness_section = self._build_material_uniqueness_section(
                             filtered_stance,
                             facts,
                             news_quotes,
                         )

                         must_include_for_sandwich = f"""[✅ 입장문 핵심 문구]
{must_include_stance_text}

[✅ 뉴스 핵심 팩트]
{must_include_text}

[✅ 뉴스 주요 발언]
{news_quotes_text}""".strip()

                         prompt_sections.append(build_context_analysis_section(context_analysis, author_name))
                         
                         scope_xml = build_scope_warning_section(context_analysis)
                         if scope_xml: prompt_sections.append(scope_xml)
                         
                         tone_xml = build_tone_warning_section(context_analysis)
                         if tone_xml: prompt_sections.append(tone_xml)
                         if material_uniqueness_section:
                             prompt_sections.append(material_uniqueness_section)
                         
                         logger.info("✅ [WriterAgent] ContextAnalyzer success")
                    else:
                         logger.warning("⚠️ [WriterAgent] ContextAnalyzer returned insufficient data")
                except Exception as e:
                    logger.error(f"❌ [WriterAgent] ContextAnalyzer error: {e}")
        
        # 6.7 Warnings
        warnings = self.build_warnings(user_profile, author_bio)
        if warnings:
            prompt_sections.append(warnings)
            
        if party_stance_guide:
            prompt_sections.append(party_stance_guide)
            
        # 6.7.6 References & Guides
        if instructions or news_context:
            prompt_sections.append(build_reference_section(instructions, news_context))
            prompt_sections.append(build_style_guide_section(style_prompt, author_name, target_word_count))
            prompt_sections.append(build_writing_rules_section(author_name, target_word_count))

        # 6.7.7 Opening Hook Policy (정치 안전형 첫 문단 가이드 — main template 앞에 두어 상위 원칙으로 작동)
        prompt_sections.append(_build_opening_hook_policy_block())

        # Main Prompt
        prompt_sections.append(prompt)
        
        # Sandwich
        if must_include_for_sandwich:
             sandwich_xml = build_sandwich_reminder_section(must_include_for_sandwich)
             if sandwich_xml: prompt_sections.append(sandwich_xml)
             
        # Dynamic Tone Matrix
        tone_matrix = _build_dynamic_tone_matrix(author_name)
        prompt_sections.append(tone_matrix)

        # Identity Lock
        opponent_name = str(context.get('_opponentName') or '').strip()
        opponent_guard = ""
        if opponent_name:
            opponent_guard = f'\n    절대 금지: "저는 {opponent_name} 후보/시장/의원..." 식으로 경쟁자를 1인칭 화자로 쓰지 마십시오.'

        identity_lock = f"""
<identity-lock priority="override">
  <status>FINAL_CHECK</status>
  <who-am-i>{author_name} ({user_profile.get('position', '정치인')})</who-am-i>
  <who-is-opponent>{opponent_name or '참고자료의 인물들'}</who-is-opponent>
  <instruction>
    직전의 참고자료에 몰입하지 마십시오. 당신은 비판하는 주체이지, 비판 대상이 아닙니다.
    반드시 "저는 {author_name}입니다"라는 자각을 유지하며 글을 마무리하십시오.
    {opponent_guard}
  </instruction>
</identity-lock>
"""
        prompt_sections.append(identity_lock)
        
        # Protocol Override
        prompt_sections.append(build_output_protocol_section())
        
        final_prompt = '\n\n'.join(prompt_sections)
        logger.info(f"📝 [WriterAgent] Prompt generated ({len(final_prompt)} chars)")
        
        # Execute Generation Loop
        from ..common.gemini_client import generate_content_async
        min_char_count = max(1200, int(target_word_count * 0.85))
        max_attempts = 3
        attempt_count = 0
        content = None
        title = None
        last_response_text = ''

        while attempt_count < max_attempts:
            attempt_count += 1
            is_retry = attempt_count > 1

            current_prompt_text = final_prompt
            if is_retry:
                missing_keywords = [k for k in user_keywords if content and k not in content]
                current_len = len(content.replace('<[^>]*>', '')) if content else 0

                retry_xml = build_retry_section(
                    attempt_count, max_attempts, current_len, min_char_count, missing_keywords
                )
                current_prompt_text = retry_xml + '\n\n' + final_prompt

            try:
                temperature = 0.45 if is_retry else 0.4
                print(f"🔄 [WriterAgent] Attempt {attempt_count}/{max_attempts}")

                last_response_text = await generate_content_async(
                    current_prompt_text,
                    model_name=self.model_name,
                    temperature=temperature,
                    max_output_tokens=8192
                )

                parsed = parse_ai_response(last_response_text, f"{topic} 관련")
                content = parsed.get('content') or ''
                title = parsed.get('title') or f"{topic} 관련"

                char_count = len(content.replace('<[^>]*>', ''))
                print(f"📊 [WriterAgent] Result len: {char_count}")

                if char_count >= min_char_count:
                    print("✅ [WriterAgent] Length requirement met")
                    break
                else:
                    print("⚠️ [WriterAgent] Length insufficient")

            except Exception as e:
                logger.error(f"❌ [WriterAgent] Attempt {attempt_count} error: {e}")
                
        if not content and last_response_text:
             logger.warning("⚠️ [WriterAgent] Final fallback parsing")
             fallback = parse_ai_response(last_response_text, f"{topic} 관련")
             content = fallback.get('content') or f"<p>{topic}에 대한 원고입니다.</p>"
             title = fallback.get('title')
             
        final_char_count_val = len(content.replace('<[^>]*>', '')) if content else 0
        
        if final_char_count_val < min_char_count:
             # Warning only in Python version? JS throws error.
             # I'll log warning but return what we have to be safe.
             logger.error(f"WriterAgent length insufficient: {final_char_count_val}/{min_char_count}")
        
        return {
            'content': content,
            'title': title,
            'wordCount': final_char_count_val,
            'writingMethod': writing_method,
            'contextKeywords': context_keyword_strings,
            'searchTerms': user_keywords,
            'appliedStrategy': {'id': None, 'name': 'default'},
            'extractedKeyPhrases': context.get('_extractedKeyPhrases', [])
        }

    async def run_context_analyzer(self, source_text: str, author_name: str) -> Dict[str, Any]:
        from ..common.gemini_client import generate_content_async

        prompt = f"""당신은 정치 뉴스 분석 전문가입니다. 아래 참고자료를 읽고 상황을 정확히 파악하세요.

⚠️ **[중요] 참고자료 구조 안내**:
- **첫 번째 자료**: 글 작성자({author_name or '화자'})가 직접 작성한 **페이스북 글 또는 입장문**입니다. 이것이 글의 핵심 논조와 주장입니다.
- **두 번째 이후 자료**: 뉴스 기사, 데이터 등 **배경 정보와 근거 자료**입니다.

따라서:
1. 첫 번째 자료에서 **글쓴이({author_name or '화자'})의 입장과 논조**를 추출하세요.
2. 두 번째 이후에서 **사실관계, 인용할 발언, 법안명 등 팩트**를 추출하세요.
3. 글쓴이는 첫 번째 자료의 입장을 **더 정교하고 풍부하게 확장**하는 글을 원합니다.

[참고자료]
{source_text[:4000]}

[글 작성자 이름]
{author_name or '(미상)'}

다음 JSON 형식으로만 응답하세요 (각 필드는 반드시 한국어로 작성):
{{
  "issueScope": "이슈의 범위 판단: 'CENTRAL_ISSUE' (중앙 정치/국가 이슈), 'LOCAL_ISSUE' (지역 현안), 'CENTRAL_ISSUE_WITH_LOCAL_IMPACT' (중앙 이슈이나 지역 인사가 연루됨) 중 택1",
  "localConflictPoint": "지역적 쟁점 요약 (예: '박형준 시장의 신공안 통치 발언 논란'). 중앙 이슈일 경우 '없음'",
  "responsibilityTarget": "비판이나 요구의 대상이 되는 핵심 주체/기관 (예: '대통령실', '국회', '부산시장', '시의회'). 행정적 책임 주체를 명확히 할 것",
  "writingFrame": "이 글이 지향해야 할 핵심 논리 프레임 1줄 요약",
  "authorStance": "첫 번째 자료(입장문)에서 추출한 글쓴이의 핵심 주장 1줄 요약",
  "mainEvent": "두 번째 이후 자료(뉴스)에서 추출한 핵심 사건 1줄 요약",
  "keyPlayers": [
    {{ "name": "인물명", "action": "이 사람이 한 행동/주장", "stance": "찬성/반대/중립" }}
  ],
  "authorRole": "글 작성자({author_name or '화자'})가 이 상황에서 취해야 할 입장과 역할",
  "expectedTone": "이 글의 예상 논조 (반박/지지/분석/비판/호소 중 택1)",
  "opponentName": "글쓴이가 비판하거나 대립각을 세우는 대상의 이름. 없다면 null",
  "mustIncludeFacts": ["뉴스에서 추출한 반드시 언급해야 할 구체적 팩트 5개"],
  "newsQuotes": ["뉴스에 등장하는 핵심 인물들의 발언을 '참고용'으로 추출 (3개 이상)"],
  "mustIncludeFromStance": ["입장문의 핵심 공약/정책/주장 (15자 이상 완전한 문장, 최대 5개)"],
  "contextWarning": "맥락 오해 방지를 위한 주의사항"
}}"""

        response_text = await generate_content_async(
            prompt,
            model_name=self.model_name,
            temperature=0.1,
            max_output_tokens=2000,
            response_mime_type='application/json'
        )

        try:
            return json.loads(response_text)
        except:
            # Fallback cleanup
            text = re.sub(r'```json|```', '', response_text).strip()
            return json.loads(text)

    def build_author_bio(self, user_profile: Dict[str, Any]) -> str:
        name = user_profile.get('name', '사용자')
        party_name = user_profile.get('partyName', '')
        current_title = user_profile.get('customTitle') or user_profile.get('position', '')
        
        basic_bio = ' '.join(filter(None, [party_name, current_title, name]))
        
        additional_info = []
        career = user_profile.get('careerSummary') or user_profile.get('bio', '')
        if career:
            if isinstance(career, list):
                additional_info.append(f"[주요 경력] {', '.join(career[:3])}")
            else:
                trunc = career[:150] + '...' if len(career) > 150 else career
                additional_info.append(f"[주요 경력] {trunc}")
                
        # 슬로건/후원 안내는 생성 단계에서 제외하고, 최종 출력 직전에만 부착한다.

        if user_profile.get('coreValues'):
            vals = user_profile['coreValues']
            if isinstance(vals, list):
                vals = ', '.join(vals)
            additional_info.append(f"[핵심 가치] {vals}")
            
        if additional_info:
            return f"{basic_bio}\n" + "\n".join(additional_info)
            
        return basic_bio

    def is_current_lawmaker(self, user_profile: Dict[str, Any]) -> bool:
        experience = user_profile.get('politicalExperience', '')
        return experience in ['초선', '재선', '3선이상']

    def build_warnings(self, user_profile: Dict[str, Any], author_bio: str) -> str:
        warnings = []
        
        nm_warning = generate_non_lawmaker_warning(
            user_profile.get('position'),
            user_profile.get('status'),
            user_profile.get('politicalExperience'),
            author_bio,
        )
        if nm_warning: warnings.append(nm_warning.strip())
        
        fam_warning = generate_family_status_warning({
            'familyStatus': user_profile.get('familyStatus')
        })
        if fam_warning: warnings.append(fam_warning.strip())
        
        warnings.append("""🚨 [CRITICAL] 사실 관계 왜곡 금지 (본인 vs 가족 구분):
- 작성자 프로필(Bio)에 언급된 "가족의 직업/이력"을 "나(화자)의 직업/이력"으로 쓰지 마십시오.
- 예: "아버지가 부두 노동자" -> "저는 부두 노동자 출신입니다" (❌ 절대 금지: 아버지가 노동자이지 내가 아님)
- 예: "아버지가 부두 노동자" -> "부두 노동자였던 아버지의 등을 보며 자랐습니다" (✅ 올바른 표현)""")
        
        target_election = user_profile.get('targetElection', {})
        position = target_election.get('position') or user_profile.get('position', '')
        is_metro = any(x in position for x in ['시장', '도지사', '교육감'])
        is_gugun = any(x in position for x in ['구청장', '군수', '기초의원'])
        if is_metro and not is_gugun:
             warnings.append(f"""🚨 [CRITICAL] 지역 범위 설정 (광역 자치단체장급):
- 당신은 지금 기초지자체(구/군)가 아닌 **"광역 자치단체({user_profile.get('regionMetro', '시/도')} 전체"**를 대표하는 후보자입니다.
- 특정 구/군에만 국한된 공약이나 비전을 메인으로 내세우지 마십시오.
- 반드시 **"{user_profile.get('regionMetro', '부산')} 전체의 균형 발전"**이나 **"시정 전체의 쇄신"**과 연결 지어 거시적인 관점에서 서술하십시오.""")

        if author_bio and '"' in author_bio:
             warnings.append("""🚨 [CRITICAL] Bio 인용구 보존 법칙:
- 작성자 정보(Bio)에 있는 **큰따옴표(" ")로 묶인 문장**은 사용자의 핵심 서사(Narrative)이므로, 금지어나 민감한 단어(예: 국회의원)가 포함되어 있더라도 **절대 수정/삭제/검열하지 말고 원문 그대로 인용**하십시오.""")
             
        return '\n\n'.join(warnings) if warnings else ''
