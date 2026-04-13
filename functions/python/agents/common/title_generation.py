"""?? ?? ?? API? ???????."""

import re
from typing import Any, Dict, List

from .title_common import (
    TITLE_LENGTH_HARD_MAX,
    TITLE_LENGTH_HARD_MIN,
    TITLE_LENGTH_OPTIMAL_MAX,
    TITLE_LENGTH_OPTIMAL_MIN,
    are_keywords_similar,
    build_structured_title_candidates,
    extract_numbers_from_content,
    get_election_compliance_instruction,
    logger,
    normalize_title_surface,
    resolve_title_family,
    select_title_family,
    _filter_required_title_keywords,
)
from .title_keywords import (
    _extract_topic_person_names,
    extract_topic_keywords,
    validate_theme_and_content,
)
from .title_metadata import (
    _detect_event_label,
    _extract_book_title,
    _extract_date_hint,
    _normalize_generated_title,
    _normalize_generated_title_without_fit,
    resolve_title_purpose,
)
from .title_prompt_parts import (
    TITLE_TYPES,
    build_common_title_anti_pattern_instruction,
    build_competitor_intent_title_instruction,
    build_event_title_policy_instruction,
    build_poll_focus_title_instruction,
    build_title_skeleton_protocol,
    build_user_provided_few_shot_instruction,
    get_keyword_strategy_instruction,
    _render_narrative_principle_xml,
)
from .title_repairers import (
    _build_argument_tail_candidates,
    _extract_argument_title_cues,
    _repair_title_for_missing_keywords,
    _repair_title_for_role_keyword_policy,
    _resolve_competitor_intent_title_keyword,
)
from .title_scoring import (
    _assess_initial_title_length_discipline,
    _compute_similarity_penalty,
    calculate_title_quality_score,
)

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
    secondary_keyword = str(user_keywords[1]).strip() if len(user_keywords) > 1 else ''
    require_secondary_keyword = bool(
        primary_keyword and secondary_keyword and not are_keywords_similar(primary_keyword, secondary_keyword)
    )
    event_date = str(must_preserve.get('eventDate') or '').strip()
    date_hint = _extract_date_hint(event_date) or _extract_date_hint(topic)
    event_location = str(must_preserve.get('eventLocation') or '').strip() or primary_keyword
    event_label = _detect_event_label(topic)
    event_label_display = event_label or '(명시적 행사명 없음)'
    event_label_rule = (
        f'"{event_label}" 또는 "안내/초대/개최/행사" 포함.'
        if event_label
        else '"안내/초대/개최" 중 하나를 포함하고, 실제 행사명이 없으면 임의의 행사명을 만들지 마세요.'
    )
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
  <event_label>{event_label_display}</event_label>
  <content_preview>{content_preview[:content_preview_limit]}</content_preview>
</input>

<hard_rules>
  <rule>제목은 기본적으로 {TITLE_LENGTH_OPTIMAL_MIN}-{TITLE_LENGTH_OPTIMAL_MAX}자로 작성.</rule>
  <rule>검증 허용 범위는 {TITLE_LENGTH_HARD_MIN}-{TITLE_LENGTH_HARD_MAX}자(예외 구간 포함).</rule>
  <rule>출력 직전에 제목 글자 수를 직접 세고 {TITLE_LENGTH_OPTIMAL_MIN}-{TITLE_LENGTH_OPTIMAL_MAX}자가 아니면 내부에서 다시 고친 뒤 1개만 출력.</rule>
  <rule>{TITLE_LENGTH_OPTIMAL_MAX}자를 넘으면 자르지 말고, 정보 요소를 줄여 더 짧은 새 제목으로 다시 작성.</rule>
  <rule>물음표(?)와 추측/논쟁형 어투 금지.</rule>
  <rule>안내 목적이 즉시 드러나도록 {event_label_rule}</rule>
  <rule>후킹 단어 1개 이상 포함: {hook_words}.</rule>
  <rule>1순위 검색어가 있으면 반드시 포함: "{primary_keyword or '(없음)'}".</rule>
  {f'<rule>독립 검색어 2개면 둘 다 포함: "{primary_keyword}", "{secondary_keyword}".</rule>' if require_secondary_keyword else ''}
  <rule>날짜 힌트가 있으면 반드시 포함: "{date_hint or '(없음)'}".</rule>
  <rule>인물명이 있으면 반드시 포함: "{full_name or '(없음)'}".</rule>
  <rule>도서 행사({is_book_event})이고 도서명이 있으면 도서명 단서를 포함: "{book_title or '(없음)'}".</rule>
  <rule>장소 힌트가 있으면 가능한 한 포함: "{event_location or '(없음)'}".</rule>
</hard_rules>

{number_validation.get('instruction', '')}

</event_title_prompt>"""

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
    poll_focus_title_policy = build_poll_focus_title_instruction(params)
    competitor_intent_title_policy = build_competitor_intent_title_instruction(params)
    title_constraint_text = str(params.get('titleConstraintText') or '').strip()
    
    avoid_local_in_title = bool(title_scope and title_scope.get('avoidLocalInTitle'))
    family_meta = select_title_family(params)
    detected_type_id = forced_type if forced_type and forced_type in TITLE_TYPES else resolve_title_family(params)
    if avoid_local_in_title and detected_type_id == 'LOCAL_FOCUSED' and not forced_type:
        detected_type_id = 'ISSUE_ANALYSIS'

    primary_type = TITLE_TYPES.get(detected_type_id) or TITLE_TYPES['DATA_BASED']
    
    number_validation = extract_numbers_from_content(content_preview)
    election_compliance = get_election_compliance_instruction(status)
    keyword_strategy = get_keyword_strategy_instruction(
        user_keywords,
        keywords,
        role_keyword_policy,
    )
    user_few_shot = build_user_provided_few_shot_instruction(primary_type['id'], params)
    skeleton_protocol = build_title_skeleton_protocol(primary_type['id'], params)
    common_anti_patterns = build_common_title_anti_pattern_instruction()
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
    family_reasons = family_meta.get('reasons') if isinstance(family_meta.get('reasons'), dict) else {}
    selected_family_reasons = family_reasons.get(detected_type_id) if isinstance(family_reasons, dict) else []
    family_reason_lines = "\n".join(
        f"  <reason>{str(reason).strip()}</reason>"
        for reason in list(selected_family_reasons or [])[:4]
        if str(reason).strip()
    ) or "  <reason>no explicit selector reason</reason>"
    family_score_lines = "\n".join(
        f'    <family id="{family_id}" score="{int(score or 0)}" />'
        for family_id, score in sorted(
            (family_meta.get('scores') or {}).items(),
            key=lambda item: int(item[1] or 0),
            reverse=True,
        )[:4]
    )
    family_selection_xml = f"""
<title_family_selection selected="{detected_type_id}" prior="{str(family_meta.get('prior') or '').strip() or 'none'}">
{family_reason_lines}
  <top_candidates>
{family_score_lines or '    <family id="none" score="0" />'}
  </top_candidates>
</title_family_selection>
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
    name_dedup_rule = ""
    if primary_kw_str and full_name and primary_kw_str == full_name:
        name_dedup_rule = (
            f'<rule id="no_duplicate_author_keyword">검색어 "{primary_kw_str}"와 author "{full_name}"가 같으면 '
            '같은 이름을 제목에 두 번 쓰지 말고 한 번만 자연스럽게 배치할 것.</rule>'
        )
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
{family_selection_xml}

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
{common_anti_patterns}

<rules priority="critical">
  <rule id="length_target">제목은 기본적으로 {TITLE_LENGTH_OPTIMAL_MIN}-{TITLE_LENGTH_OPTIMAL_MAX}자로 작성 (최우선 목표).</rule>
  <rule id="length_max">{TITLE_LENGTH_HARD_MAX}자 이내 (네이버 검색결과 잘림 방지) - 절대 초과 금지.</rule>
  <rule id="length_floor">{TITLE_LENGTH_HARD_MIN}자 미만 금지. {TITLE_LENGTH_HARD_MIN}-14자와 31-{TITLE_LENGTH_HARD_MAX}자는 예외 구간이므로 가급적 피할 것.</rule>
  <rule id="length_self_check">출력 직전에 제목 글자 수를 직접 세고, {TITLE_LENGTH_OPTIMAL_MIN}-{TITLE_LENGTH_OPTIMAL_MAX}자가 아니면 내부에서 다시 써서 맞춘 뒤 최종 1개만 출력.</rule>
  <rule id="no_length_repair_dependency">길이가 길다고 느껴지면 뒤를 자르지 말고, 정보 요소를 줄여 더 짧은 새 문장으로 다시 작성. 31-35자 예외 통과에 기대지 말 것.</rule>
  <rule id="no_slot_placeholder">슬롯 플레이스홀더([행사명], [지역명], [정책명] 등)를 제목에 그대로 출력하지 마세요.</rule>
  <rule id="no_ellipsis">말줄임표("...") 절대 금지</rule>
  <rule id="no_first_person_title">메인 제목에는 1인칭(저는/제가/저의/제 정책/나의/내가) 금지. 화자 이름·정책명·수치 중심의 기사형 제목으로 작성.</rule>
  {f'<rule id="name_repeat_limit">{title_constraint_text}</rule>' if title_constraint_text else ''}
  {name_dedup_rule}
  <rule id="keyword_position">{keyword_position_rule}</rule>
  <rule id="no_greeting">인사말("안녕하세요"), 서술형 어미("~입니다") 절대 금지</rule>
  <rule id="style_ban">{style_ban_rule}</rule>
  <rule id="narrative_tension">읽은 뒤 "그래서?" "왜?"가 떠오르는 제목이 좋다. 기법을 억지로 넣지 말고 자연스러운 호기심을 만들어라. 선언형 종결("~바꾼다") 금지. 정보 요소 3개 이하.</rule>
  <rule id="info_density">제목에 담는 정보 요소는 최대 3개. SEO 키워드는 1개로 카운트. 요소: SEO키워드, 인명, 수치, 정책명, 수식어. "부산 지방선거, 왜 이 남자가 뛰어들었나" = 2개 OK. "부산 지방선거 이재명 2호 이재성 원칙 선택" = 5개 NG.</rule>
  <rule id="no_topic_copy">주제(topic) 텍스트를 그대로 또는 거의 그대로 제목으로 사용 금지. 주제의 핵심 방향만 따르되, 표현·어순·구성은 반드시 새롭게 작성할 것.</rule>
  <rule id="no_content_phrase_fragment">본문(content_preview)의 구문 조각을 이름에 직접 붙여 제목을 만들지 말 것. 예: 본문에 "네거티브 없는 정책 경선"이 있어도 "[인물명] 없는 정책"처럼 축약해 쓰지 말 것. 본문은 맥락 파악용이지 어구 복사 재료가 아니다.</rule>
</rules>

{skeleton_protocol}

{event_title_policy}
{poll_focus_title_policy}
{competitor_intent_title_policy}
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


_RETRYABLE_TITLE_SURFACE_KEYS = (
    'ellipsis',
    'truncatedTitle',
    'malformedSurface',
)


def _get_surface_retry_limit(issue_key: str) -> int:
    normalized = str(issue_key or '').strip()
    if normalized in {'ellipsis', 'truncatedTitle'}:
        return 2
    if normalized == 'malformedSurface':
        return 1
    return 0


def _extract_retryable_surface_issue(score_result: Dict[str, Any]) -> Dict[str, str]:
    breakdown = score_result.get('breakdown') if isinstance(score_result, dict) else {}
    if not isinstance(breakdown, dict):
        return {}

    for key in _RETRYABLE_TITLE_SURFACE_KEYS:
        detail = breakdown.get(key)
        if not isinstance(detail, dict):
            continue
        reason = str(detail.get('reason') or '').strip()
        if reason:
            return {'key': key, 'reason': reason}
    return {}


def _build_surface_retry_prompt(
    base_prompt: str,
    failed_title: str,
    issue_key: str,
    issue_reason: str,
) -> str:
    blocked_title = str(failed_title or '').strip()
    reason = str(issue_reason or '').strip() or '제목 표면 규칙 위반'
    issue_specific_rule = ''
    if issue_key == 'ellipsis':
        issue_specific_rule = '<rule>말줄임표("...", "…")를 절대 쓰지 말고, 내용을 자르지 않은 완결형 제목만 출력할 것.</rule>'
    elif issue_key == 'truncatedTitle':
        issue_specific_rule = '<rule>중간에 끊긴 표현, 꼬리가 잘린 질문형, 미완결 제목을 금지하고 완결된 의미 단위로 끝낼 것.</rule>'
    elif issue_key == 'malformedSurface':
        issue_specific_rule = '<rule>조사 중복, 빠진 조사, 비문형 결합을 금지하고 자연스러운 한국어 제목으로 다시 쓸 것.</rule>'

    return f"""{base_prompt}

<surface_retry priority="critical">
  <failed_title>{blocked_title or '(없음)'}</failed_title>
  <reason>{reason}</reason>
  <rule>위 실패 제목과 같은 구조, 같은 어미, 같은 문장 뼈대를 반복하지 말 것.</rule>
  <rule>이번에는 검토를 끝낸 최종 제목 1개만 출력할 것.</rule>
  {issue_specific_rule}
</surface_retry>
"""


def _build_previous_attempt_surface_feedback(last_attempt: Dict[str, Any]) -> str:
    if not isinstance(last_attempt, dict):
        return ''

    breakdown = last_attempt.get('breakdown')
    if not isinstance(breakdown, dict):
        return ''

    for key in _RETRYABLE_TITLE_SURFACE_KEYS:
        detail = breakdown.get(key)
        if not isinstance(detail, dict):
            continue
        reason = str(detail.get('reason') or '').strip()
        previous_title = str(last_attempt.get('title') or '').strip()
        return f"""
<surface_retry_feedback attempt="{last_attempt.get('attempt', 0)}">
  <previous_title>{previous_title}</previous_title>
  <issue>{reason or '제목 표면 규칙 위반'}</issue>
  <rule>직전 실패 제목의 표면 구조를 반복하지 말고, 같은 위반을 고친 새 제목만 출력할 것.</rule>
</surface_retry_feedback>
"""
    return ''


_POSSESSIVE_MODIFIER_PATTERN = re.compile(
    r'^\S{2,12}의\s+\S*(?:되는|하는|된|적|스러운|같은|있는|없는|새로운|좋은|나쁜|존중하는)\s+\S+',
)
_NAME_NEGATION_PATTERN = re.compile(
    r'^(?P<name>\S{2,6})(?:[,，]\s+(?P=name))?\s+없는\s+\S+',
)
_NAME_DUPLICATE_PATTERN = re.compile(
    r'^(?P<name>\S{2,6})[,，\s]+(?P=name)(?:\s|[,，]|$)',
)
_NAME_DUPLICATE_POSSESSIVE_PATTERN = re.compile(
    r'^(?P<name>\S{2,12})[,，]\s+(?P=name)의\s+\S+',
)
_MISSING_DELIMITER_AFTER_VS_EVENT_RE = re.compile(
    r'\bvs\s+\S{2,12}\s+(?:\d{1,2}월|\d{1,2}일|KNN|MBC|SBS|YTN|토론|방송|안내|행사|생중계)',
    re.IGNORECASE,
)


def _detect_possessive_modifier_pattern(title: str) -> bool:
    """'이름+의+형용사형수식어+명사' 구조 감지. LLM 피드백 생성에만 사용."""
    return bool(_POSSESSIVE_MODIFIER_PATTERN.match(title or ''))


def _detect_title_structural_defect(title: str) -> str:
    """제목 구조 결함 감지. 빈 문자열이면 정상, 아니면 결함 설명."""
    normalized = str(title or '').strip()
    if not normalized:
        return ''
    if _NAME_DUPLICATE_POSSESSIVE_PATTERN.match(normalized):
        return '이름 반복 뒤에 "이름의 ..." 구조가 붙어 의미가 무너집니다.'
    if _NAME_NEGATION_PATTERN.match(normalized):
        return '"이름 없는 정책"류 구조 - 부정어가 이름에 붙어 의미가 반전되거나 불완전해짐'
    if _NAME_DUPLICATE_PATTERN.match(normalized):
        return '이름 중복 - 동일 인물명이 제목에 2회 이상 등장'
    if _detect_possessive_modifier_pattern(normalized):
        return '"이름의 되는/하는/있는 ..." 구조 - 본문 구절 조각이 이름 뒤에 붙어 의미가 끊김'
    if _MISSING_DELIMITER_AFTER_VS_EVENT_RE.search(normalized):
        return '"A vs B C" 구조에 구분자 누락 - "A vs B, C" 형식으로 분리해야 함'
    return ''


def _build_previous_attempt_pattern_feedback(title: str) -> str:
    structural_defect = _detect_title_structural_defect(title)
    if structural_defect:
        return (
            f'<item>직전 제목 구조 결함: {structural_defect}. '
            '이름을 반복하거나 이름에 부정어를 직접 붙이지 말고, 팩트+서사 구조로 완전히 재작성하세요. '
            '예: "지방선거 경선 확정, 원칙이 가른 판세"</item>'
        )
    if not _detect_possessive_modifier_pattern(title):
        return ''
    return (
        '<item>직전 제목이 "이름+의+형용사형어구" 구조입니다. '
        '"이름의 [수식어] [명사]" 형태 대신 팩트+서사 구조로 재작성하세요. '
        '예: "지방선거 경선 확정, 원칙이 가른 판세"</item>'
    )


def _build_final_repair_prompt(
    params: Dict[str, Any],
    best_result: Dict[str, Any],
    *,
    min_score: int,
) -> str:
    base_prompt = build_title_prompt({**params, 'titlePromptLite': False})
    best_title = str(best_result.get('title') or '').strip()
    best_score = int(best_result.get('score', 0) or 0)
    suggestion_items = ''.join(
        f"\n    <item>{str(item or '').strip()}</item>"
        for item in list(best_result.get('suggestions') or [])
        if str(item or '').strip()
    )
    if not suggestion_items:
        suggestion_items = "\n    <item>직전 제목의 문제를 실제로 고친 최종 제목 1개를 다시 작성하세요.</item>"

    title_purpose = resolve_title_purpose(str(params.get('topic') or ''), params)
    purpose_rule = ''
    if title_purpose == 'event_announcement':
        purpose_rule = (
            '<rule>행사 안내형 제목이면 날짜, 행사 성격, 인물명 중 2개 이상이 자연스럽게 드러나고 '
            '안내 목적이 즉시 보이게 작성할 것.</rule>'
        )

    return f"""{base_prompt}

<final_title_repair priority="critical">
  <failed_title>{best_title or '(없음)'}</failed_title>
  <current_score>{best_score}</current_score>
  <target_score>{min_score}</target_score>
  <instruction>개선 힌트를 설명으로 출력하지 말고, 문제를 실제로 고친 최종 제목 1개만 다시 작성하세요.</instruction>
  <issues>{suggestion_items}
  </issues>
  <rules>
    <rule>직전 제목의 팩트와 주제는 유지하되, 점수를 깎인 원인만 실제로 수정할 것.</rule>
    <rule>직전 실패 제목을 거의 그대로 반복하지 말고, 구체적인 수정 결과를 반영할 것.</rule>
    <rule>설명, 해설, JSON 없이 최종 제목 1개만 출력할 것.</rule>
    {purpose_rule}
  </rules>
</final_title_repair>
"""


async def _attempt_final_title_repair(
    generate_fn,
    params: Dict[str, Any],
    *,
    min_score: int,
    best_result: Dict[str, Any],
    recent_titles: List[str],
    history: List[Dict[str, Any]],
    similarity_threshold: float,
    max_similarity_penalty: int,
) -> Dict[str, Any]:
    repair_seed = dict(best_result or {})
    best_failed_title = str(best_result.get('title') or '').strip()
    best_failed_score = int(best_result.get('score', 0) or 0)

    for repair_attempt in range(1, 4):
        repair_prompt = _build_final_repair_prompt(params, repair_seed, min_score=min_score)
        raw_generated_title = str(await generate_fn(repair_prompt) or '').strip().strip('"\'')
        initial_generated_title = _normalize_generated_title_without_fit(raw_generated_title, params)
        if not initial_generated_title:
            raise RuntimeError('[TitleGen] 최종 수선 단계에서 빈 제목이 반환되었습니다.')

        score_result = calculate_title_quality_score(
            initial_generated_title,
            params,
            {'autoFitLength': False},
        )
        candidate_title = initial_generated_title
        repaired_title = str(score_result.get('repairedTitle') or '').strip()
        if repaired_title and repaired_title != candidate_title:
            repaired_score_result = calculate_title_quality_score(
                repaired_title,
                params,
                {'autoFitLength': False},
            )
            if int(repaired_score_result.get('score', 0) or 0) >= int(score_result.get('score', 0) or 0):
                candidate_title = repaired_title
                score_result = repaired_score_result

        disallow_titles = list(recent_titles)
        disallow_titles.extend(
            str(item.get('title') or '').strip()
            for item in history
            if isinstance(item, dict) and str(item.get('title') or '').strip()
        )
        similarity_meta = _compute_similarity_penalty(
            candidate_title,
            disallow_titles,
            threshold=similarity_threshold,
            max_penalty=max_similarity_penalty,
        )
        initial_length_meta = _assess_initial_title_length_discipline(candidate_title)
        adjusted_score = max(
            0,
            int(score_result.get('score', 0))
            - int(similarity_meta.get('penalty', 0))
            - int(initial_length_meta.get('penalty', 0)),
        )
        if adjusted_score >= min_score:
            repair_history = {
                'attempt': len(history) + 1,
                'title': candidate_title,
                'score': adjusted_score,
                'baseScore': int(score_result.get('score', 0) or 0),
                'candidateCount': 1,
                'selectedCandidate': 1,
                'similarityPenalty': int(similarity_meta.get('penalty', 0)),
                'similarity': similarity_meta.get('maxSimilarity', 0),
                'initialLengthPenalty': int(initial_length_meta.get('penalty', 0) or 0),
                'initialTitleLength': int(initial_length_meta.get('length', 0) or 0),
                'suggestions': list(score_result.get('suggestions') or [])[:4],
                'breakdown': dict(score_result.get('breakdown', {}) or {}),
                'source': 'final_repair',
                'repairAttempt': repair_attempt,
            }
            if raw_generated_title != candidate_title:
                repair_history['rawTitle'] = raw_generated_title
            history.append(repair_history)

            return {
                'title': candidate_title,
                'score': adjusted_score,
                'baseScore': int(score_result.get('score', 0) or 0),
                'similarityPenalty': int(similarity_meta.get('penalty', 0)),
                'initialLengthPenalty': int(initial_length_meta.get('penalty', 0) or 0),
                'attempts': len(history),
                'passed': True,
                'history': history,
                'breakdown': dict(score_result.get('breakdown', {}) or {}),
                'source': 'final_repair',
            }

        if adjusted_score > best_failed_score:
            best_failed_score = adjusted_score
            best_failed_title = candidate_title

        repair_seed = {
            'title': candidate_title,
            'score': adjusted_score,
            'suggestions': list(score_result.get('suggestions') or []),
            'breakdown': dict(score_result.get('breakdown', {}) or {}),
        }

    raise RuntimeError(
        f"[TitleGen] 최종 수선 제목도 최소 점수 {min_score}점 미달 "
        f"(최고 {best_failed_score}점, 제목: \"{best_failed_title}\")"
    )


def _attempt_structured_title_rescue(
    params: Dict[str, Any],
    *,
    min_score: int,
    recent_titles: List[str],
    history: List[Dict[str, Any]],
    similarity_threshold: float,
    max_similarity_penalty: int,
) -> Dict[str, Any]:
    title_purpose = resolve_title_purpose(str(params.get('topic') or ''), params)
    if title_purpose != 'event_announcement':
        return {}

    candidate_titles = build_structured_title_candidates(
        params,
        title_purpose=title_purpose,
        limit=8,
    )
    if not candidate_titles:
        return {}

    disallow_titles = list(recent_titles)
    disallow_titles.extend(
        str(item.get('title') or '').strip()
        for item in history
        if isinstance(item, dict) and str(item.get('title') or '').strip()
    )

    best_candidate: Dict[str, Any] = {}
    best_score = -1
    for idx, candidate_title in enumerate(candidate_titles, start=1):
        initial_length_meta = _assess_initial_title_length_discipline(candidate_title)
        score_result = calculate_title_quality_score(
            candidate_title,
            params,
            {'autoFitLength': False},
        )
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
        if adjusted_score > best_score:
            best_score = adjusted_score
            best_candidate = {
                'attempt': len(history) + 1,
                'title': candidate_title,
                'score': adjusted_score,
                'baseScore': int(score_result.get('score', 0) or 0),
                'candidateCount': len(candidate_titles),
                'selectedCandidate': idx,
                'similarityPenalty': int(similarity_meta.get('penalty', 0)),
                'similarity': similarity_meta.get('maxSimilarity', 0),
                'initialLengthPenalty': int(initial_length_meta.get('penalty', 0) or 0),
                'initialTitleLength': int(initial_length_meta.get('length', 0) or 0),
                'suggestions': list(score_result.get('suggestions') or [])[:4],
                'breakdown': dict(score_result.get('breakdown', {}) or {}),
                'source': 'structured_rescue',
            }

    if not best_candidate or int(best_candidate.get('score', 0) or 0) < min_score:
        return {}

    history.append(best_candidate)
    return {
        'title': str(best_candidate.get('title') or ''),
        'score': int(best_candidate.get('score', 0) or 0),
        'baseScore': int(best_candidate.get('baseScore', 0) or 0),
        'similarityPenalty': int(best_candidate.get('similarityPenalty', 0) or 0),
        'initialLengthPenalty': int(best_candidate.get('initialLengthPenalty', 0) or 0),
        'attempts': len(history),
        'passed': True,
        'history': history,
        'breakdown': dict(best_candidate.get('breakdown', {}) or {}),
        'source': 'structured_rescue',
    }


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

async def generate_and_validate_title(generate_fn, params: Dict[str, Any], options: Dict[str, Any] = {}) -> Dict[str, Any]:
    min_score = int(options.get('minScore', 70))
    max_attempts = int(options.get('maxAttempts', 3))
    candidate_count = max(1, int(options.get('candidateCount', 5)))
    allow_auto_repair = bool(options.get('allowAutoRepair', True))
    similarity_threshold = float(options.get('similarityThreshold', 0.78))
    similarity_threshold = min(max(similarity_threshold, 0.50), 0.95)
    max_similarity_penalty = max(0, int(options.get('maxSimilarityPenalty', 18)))
    on_progress = options.get('onProgress')
    role_keyword_policy = params.get('roleKeywordPolicy') if isinstance(params.get('roleKeywordPolicy'), dict) else {}
    user_keywords = _filter_required_title_keywords(
        params.get('userKeywords') if isinstance(params.get('userKeywords'), list) else [],
        role_keyword_policy,
    )

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
    if title_purpose == 'event_announcement':
        recent_titles = []
        max_similarity_penalty = 0
        similarity_threshold = 0.99
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
            previous_title = str(last_attempt.get('title') or '').strip()
            suggestion_items = ''
            for suggestion in last_attempt.get('suggestions', []):
                suggestion_text = str(suggestion or '').strip()
                if suggestion_text:
                    suggestion_items += f"\n    <item>{suggestion_text}</item>"
            pattern_feedback = _build_previous_attempt_pattern_feedback(previous_title)
            if pattern_feedback:
                suggestion_items += f"\n    {pattern_feedback}"
            if not suggestion_items:
                suggestion_items = "\n    <item>이전 문제를 보완해 새 제목을 생성하세요.</item>"
            feedback_prompt = f"""
<previous_attempt_feedback attempt="{attempt - 1}" score="{last_attempt.get('score', 0)}">
  <previous_title>{previous_title}</previous_title>
  <issues>{suggestion_items}
  </issues>
  <instruction>위 문제를 해결한 새로운 제목을 작성하세요.</instruction>
</previous_attempt_feedback>
"""
            prompt = feedback_prompt + _build_previous_attempt_surface_feedback(last_attempt) + build_title_prompt(params)

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
            candidate_prompt = candidate_prompts[idx - 1]
            if isinstance(response, Exception):
                err = str(response)
                generation_errors.append(err)
                logger.warning("[TitleGen] 후보 %s 생성 실패 (attempt=%s): %s", idx, attempt, err)
                continue

            raw_generated_title = str(response or '').strip().strip('"\'')
            surface_retry_count = 0
            while True:
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
                    break

                initial_length_meta = _assess_initial_title_length_discipline(initial_generated_title)
                length_feedback = _build_initial_length_discipline_feedback(initial_length_meta)
                score_result = calculate_title_quality_score(
                    initial_generated_title,
                    params,
                    {'autoFitLength': False},
                )
                surface_issue = _extract_retryable_surface_issue(score_result)
                surface_issue_key = str(surface_issue.get('key') or '')
                surface_retry_limit = _get_surface_retry_limit(surface_issue_key)
                if surface_issue and surface_retry_count < surface_retry_limit:
                    surface_retry_count += 1
                    retry_prompt = _build_surface_retry_prompt(
                        candidate_prompt,
                        initial_generated_title,
                        surface_issue_key,
                        str(surface_issue.get('reason') or ''),
                    )
                    logger.info(
                        "[TitleGen] 후보 %s 하드 표면 위반 재시도(%s/%s): key=%s reason=%s title=%s",
                        idx,
                        surface_retry_count,
                        surface_retry_limit,
                        surface_issue_key,
                        surface_issue.get('reason'),
                        initial_generated_title,
                    )
                    try:
                        raw_generated_title = str(await generate_fn(retry_prompt) or '').strip().strip('"\'')
                        candidate_prompt = retry_prompt
                        continue
                    except Exception as error:
                        err = str(error)
                        generation_errors.append(err)
                        logger.warning(
                            "[TitleGen] 후보 %s 하드 표면 위반 재시도 실패 (attempt=%s): %s",
                            idx,
                            attempt,
                            err,
                        )
                break

            if not initial_generated_title:
                continue
            if allow_auto_repair:
                role_repaired_title = _repair_title_for_role_keyword_policy(
                    initial_generated_title,
                    role_keyword_policy,
                    user_keywords,
                    recent_titles,
                )
                if role_repaired_title and role_repaired_title != initial_generated_title:
                    repaired_score_result = calculate_title_quality_score(
                        role_repaired_title,
                        params,
                        {'autoFitLength': False},
                    )
                    if (
                        repaired_score_result.get('passed')
                        or int(repaired_score_result.get('score', 0)) > int(score_result.get('score', 0))
                    ):
                        logger.info(
                            "[TitleGen] role policy repair 적용(후보 %s): \"%s\" -> \"%s\"",
                            idx,
                            initial_generated_title,
                            role_repaired_title,
                        )
                        score_result = repaired_score_result
                        initial_generated_title = role_repaired_title
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

    if best_title.strip():
        try:
            logger.info(
                "[TitleGen] 근소 미달 제목 최종 수선 시도: score=%s min=%s title=%s",
                best_score,
                min_score,
                best_title,
            )
            return await _attempt_final_title_repair(
                generate_fn,
                params,
                min_score=min_score,
                best_result=best_result if isinstance(best_result, dict) else {},
                recent_titles=recent_titles,
                history=history,
                similarity_threshold=similarity_threshold,
                max_similarity_penalty=max_similarity_penalty,
            )
        except Exception as repair_error:
            logger.warning("[TitleGen] 최종 수선 실패: %s", repair_error)

    structured_rescue_result = _attempt_structured_title_rescue(
        params,
        min_score=min_score,
        recent_titles=recent_titles,
        history=history,
        similarity_threshold=similarity_threshold,
        max_similarity_penalty=max_similarity_penalty,
    )
    if structured_rescue_result:
        logger.info(
            "[TitleGen] 구조화 제목 재구제 성공: score=%s title=%s",
            structured_rescue_result.get('score'),
            structured_rescue_result.get('title'),
        )
        return structured_rescue_result

    best_suggestions = best_result.get('suggestions', []) if isinstance(best_result, dict) else []
    suggestion_text = ', '.join(best_suggestions) if best_suggestions else '없음'
    logger.warning(
        "[TitleGen] 모든 재시도/수선 실패 — 최고점 제목으로 soft-accept: "
        "score=%s min=%s title=%s suggestions=%s",
        best_score,
        min_score,
        best_title,
        suggestion_text,
    )
    best_breakdown = best_result.get('breakdown', {}) if isinstance(best_result, dict) else {}
    return {
        'title': best_title,
        'score': best_score,
        'baseScore': int(best_result.get('baseScore', best_score) or 0) if isinstance(best_result, dict) else best_score,
        'similarityPenalty': int(best_result.get('similarityPenalty', 0) or 0) if isinstance(best_result, dict) else 0,
        'initialLengthPenalty': int(best_result.get('initialLengthPenalty', 0) or 0) if isinstance(best_result, dict) else 0,
        'attempts': len(history),
        'passed': False,
        'softAccepted': True,
        'history': history,
        'breakdown': dict(best_breakdown or {}),
        'source': 'soft_accept_best_score',
    }

__all__ = [
    'TITLE_TYPES',
    'are_keywords_similar',
    'build_title_prompt',
    'calculate_title_quality_score',
    'detect_content_type',
    'extract_numbers_from_content',
    'extract_topic_keywords',
    'generate_and_validate_title',
    'get_election_compliance_instruction',
    'get_keyword_strategy_instruction',
    'normalize_title_surface',
    'resolve_title_purpose',
    'validate_theme_and_content',
    '_assess_initial_title_length_discipline',
    '_build_argument_tail_candidates',
    '_compute_similarity_penalty',
    '_extract_argument_title_cues',
    '_extract_book_title',
    '_extract_topic_person_names',
    '_repair_title_for_missing_keywords',
    '_resolve_competitor_intent_title_keyword',
]
