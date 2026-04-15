"""?? ?? ?? API? ???????."""

import re
from typing import Any, Dict, List

from .title_common import (
    TITLE_LENGTH_HARD_MAX,
    TITLE_LENGTH_HARD_MIN,
    TITLE_LENGTH_OPTIMAL_MAX,
    TITLE_LENGTH_OPTIMAL_MIN,
    are_keywords_similar,
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
    compute_required_topic_keywords,
    extract_topic_keywords,
    validate_theme_and_content,
)
from .title_hook_quality import (
    compute_slot_preferences,
    extract_slot_opportunities,
    render_hook_rubric_block,
    render_slot_opportunities_block,
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
    # 채점기(validate_theme_and_content) 와 동일한 함수로 required
    # topic keywords 를 계산해 LLM 에게도 보여 준다. 두 경로가 같은
    # 목록을 공유하므로 "생성은 막연히 쓰고 → 채점이 별도 키워드로 감점"
    # 루프를 원천 차단한다. user_keywords 가 있으면 엄격(required), 없으면
    # 권고(advisory) 로 문구만 바꾼다.
    required_topic_keywords_list = compute_required_topic_keywords(
        topic, params, content=content_preview
    )
    required_topic_keywords_mode = 'required' if user_keywords else 'advisory'
    if required_topic_keywords_list:
        required_topic_keywords_items = "\n".join(
            f'    <keyword>{kw}</keyword>'
            for kw in required_topic_keywords_list
            if str(kw).strip()
        )
        if required_topic_keywords_mode == 'required':
            mode_note = (
                '사용자가 지정한 검색어 또는 채점기가 추출한 주제 핵심어 목록이다. '
                '제목에 최소 1~2개 이상 포함해야 채점에서 감점되지 않는다.'
            )
        else:
            mode_note = (
                '사용자가 별도 검색어를 지정하지 않아 scorer 가 주제 텍스트에서 '
                '자동 추출한 참고용 핵심어다. 전부 포함할 필요는 없으며, 이 중 '
                '0~2개만 자연스럽게 반영하면 된다. 구체 슬롯([지역명]·[정책명]·'
                '[수치]) 을 채우는 것이 이 목록을 채우는 것보다 우선이다.'
            )
        required_topic_keywords_xml = (
            f'<required_topic_keywords mode="{required_topic_keywords_mode}">\n'
            f'  <note>{mode_note}</note>\n'
            f'  <list>\n{required_topic_keywords_items}\n  </list>\n'
            f'</required_topic_keywords>\n'
        )
    else:
        required_topic_keywords_xml = ''

    # 🔑 scorer(title_hook_quality.assess_title_hook_quality) 와 동일한
    # 함수로 본문·토픽에서 "쓸 수 있는 구체 재료" 를 뽑아 LLM 에게 직접
    # 보여 준다. 이 블록 덕분에 LLM 은 "어떤 지역/수치/기관/정책명을
    # 제목에 넣으면 점수가 올라가는지" 사전에 알 수 있다. hook_rubric
    # 블록도 동시에 주입해 scorer 가 볼 기준을 LLM 이 그대로 본다.
    slot_opportunities_map = extract_slot_opportunities(topic, content_preview, params)
    slot_preferences_map = compute_slot_preferences(
        slot_opportunities_map,
        topic=topic,
        content=content_preview,
        params=params,
    )
    slot_opportunities_xml = render_slot_opportunities_block(
        slot_opportunities_map, require_min=1, preferences=slot_preferences_map
    )
    hook_rubric_xml = render_hook_rubric_block() if not prompt_lite else ''

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

    # few-shot good 예시마다 scorer 와 동일한 함수로 "어떤 hook 차원을
    # 채웠는지" 를 주석 달아 준다. LLM 은 이 annotation 을 보고 "이 제목이
    # 왜 좋은지" 를 차원 단위로 이해한다 (예: info_gap+concrete_slot 이
    # 동시에 채워진 제목이 몇 점이다). topic=ex.title 으로 평가하면 제목
    # 자신의 슬롯이 있는 그대로 잡힌다.
    from .title_hook_quality import assess_title_hook_quality as _assess_hq
    good_lines = []
    for i, ex in enumerate(good_examples_source):
        ex_title = str(ex.get('title') or '')
        ex_hq = _assess_hq(ex_title, topic=ex_title, content=ex_title, params={})
        ex_features = ','.join(ex_hq.get('features') or []) or 'flat'
        ex_hook_score = int(ex_hq.get('score') or 0)
        good_lines.append(
            f'  <example index="{i + 1}" chars="{int(ex.get("chars", 0) or 0)}">'
            f'<title>{ex_title}</title>'
            f'<analysis>{ex.get("analysis", "")}</analysis>'
            f'<hook score="{ex_hook_score}/{ex_hq.get("max", 0)}" dimensions="{ex_features}"/>'
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
    <bad reason="평서체 종결 — 경어체 아님">이재성이 경제 0.7%를 바꾼다</bad>
    <bad reason="문장 불완전">이재성 부산 AI 3대 강국?</bad>
    <good reason="팩트+미해결질문">부산 경제 0.7%, 왜 이 남자가 뛰어들었나</good>
    <good reason="경어체 문장형">이재성, 부산 경제 0.7%를 바꿉니다</good>
  </examples>
  <banned_styles>
    <item>지루한 공무원 스타일("~개최", "~참석", "~발표")</item>
    <item>평서체 종결("~바꾼다", "~이끈다", "~완성한다", "~지킨다") — 문장형으로 닫을 때는 경어체 필수("~바꿉니다", "~이끕니다", "~완성합니다", "~지킵니다")</item>
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
  <content_preview priority="Highest" role="title_material_source">{(content_preview or '')[:content_limit]}</content_preview>
  <stance_summary priority="guidance" role="author_intent">{stance_text[:stance_limit] if stance_text else '(없음) - 입장문이 없으면 본문(content_preview) 재료로 제목 구성'}</stance_summary>
  <background>{background_text[:background_limit] if background_text else '(없음)'}</background>
</input>

{required_topic_keywords_xml}

{slot_opportunities_xml}
{hook_rubric_xml}
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
  <rule id="no_greeting">인사말("안녕하세요"), 자기소개형 copula("저는 ~입니다") 금지. 단, 문장형 제목의 경어체 종결("~합니다", "~됩니다", "~지킵니다")은 허용.</rule>
  <rule id="sentence_form_honorific" priority="critical">문장형(서술형 종결)으로 제목을 쓰는 경우, 종결 어미는 반드시 경어체(-ㅂ니다/-습니다)를 사용한다. 평서체 종결("~다", "~ㄴ다", "~바꾼다", "~지킨다", "~이끈다", "~한다", "~된다")은 제목에서 금지하고, 대응하는 경어체("~바꿉니다", "~지킵니다", "~이끕니다", "~합니다", "~됩니다")로 변환한다. 명사형 마무리, 질문형, 미완결 종결은 이 규칙의 대상이 아니다.</rule>
  <rule id="style_ban">{style_ban_rule}</rule>
  <rule id="narrative_tension">읽은 뒤 "그래서?" "왜?"가 떠오르는 제목이 좋다. 기법을 억지로 넣지 말고 자연스러운 호기심을 만들어라. 정보 요소 3개 이하. 문장형으로 닫아야 한다면 평서체가 아니라 경어체로 끝낼 것.</rule>
  <rule id="info_density">제목에 담는 정보 요소는 최대 3개. SEO 키워드는 1개로 카운트. 요소: SEO키워드, 인명, 수치, 정책명, 수식어. "부산 지방선거, 왜 이 남자가 뛰어들었나" = 2개 OK. "부산 지방선거 이재명 2호 이재성 원칙 선택" = 5개 NG.</rule>
  <rule id="no_topic_copy">주제(topic) 텍스트를 그대로 또는 거의 그대로 제목으로 사용 금지. 주제의 핵심 방향만 따르되, 표현·어순·구성은 반드시 새롭게 작성할 것.</rule>
  <rule id="no_content_phrase_fragment">본문(content_preview)의 구문 조각을 이름에 직접 붙여 제목을 만들지 말 것. 예: 본문에 "네거티브 없는 정책 경선"이 있어도 "[인물명] 없는 정책"처럼 축약해 쓰지 말 것. 본문은 맥락 파악용이지 어구 복사 재료가 아니다.</rule>
  <rule id="title_from_body_not_stance" priority="critical">제목의 구체 재료는 반드시 &lt;content_preview&gt;(생성된 본문)에서 가져와라. &lt;stance_summary&gt;는 사용자가 "어느 각도로 쓰고 싶다"는 의도 힌트일 뿐이고, 거기 있는 구절을 제목에 옮기면 그건 제목 생성이 아니라 사용자 입력 되돌려주기다. 올바른 흐름은 다음 4단계다:
    1. content_preview 를 읽고 &lt;slot_opportunities&gt;(지역·수치·기관·연도·정책명)를 확인한다.
    2. 그 재료로 제목의 뼈대를 새로 조립한다 — stance 문장을 틀로 삼지 말 것.
    3. stance_summary 의 방향성만 어조·각도에 반영한다 (어미·대상·포커스 조정).
    4. stance_summary 에서 공백 제거 연속 8자 이상 구간을 그대로 옮기면 no_topic_copy 위반으로 탈락된다. 단어 단위(3~4자) 참고는 허용.
    사용자는 주제를 최소한으로만 적었을 수 있다. 그 경우에도 본문이 이미 완성돼 있으니, 본문의 구체 재료로 제목을 만들어라 — stance 를 늘이거나 다듬는 방식이 아니다.</rule>
  <rule id="use_slot_opportunities" priority="critical">위 &lt;slot_opportunities&gt; 블록이 비어 있지 않다면, 제목은 그 중 최소 1개 카테고리에서 한 토큰 이상을 그대로 인용해야 한다. "공동체/책임/약속/미래/희망" 같은 추상어로 채우고 구체 재료(지역·수치·기관·연도·정책명)를 통째로 빼면 평탄한 선언형이 되어 채점에서 FAIL 된다. few-shot good 예시들이 왜 좋은지 보라 — 전부 구체 슬롯 2개 이상을 가지고 있다.</rule>
  <rule id="prefer_specific_slot_token" priority="high">&lt;slot_opportunities&gt; 의 각 카테고리에 preferred="true" 가 달린 토큰이 있으면 그 토큰을 우선 인용하라. preferred 는 "이 글의 진짜 스코프(본문 빈도)" 와 "화자의 직책 정책(기초/광역)" 을 반영해 자동 계산된 결과다. 같은 카테고리 안의 더 넓거나 덜 구체적인 대안(preferred 가 아닌 형제 토큰) 은 preferred 가 제목 흐름(길이·율동·자연스러움)과 정면충돌할 때에만 대체재로 쓴다. 예: region 카테고리에 더 좁은 행정구역(구/군/동) 이 preferred 이면 상위 광역명(시/도/광역시) 대신 preferred 토큰을 쓰는 것이 기본이다.</rule>
  <rule id="no_hollow_question_tail" priority="critical">제목 끝을 **"[추상명사][은/는]?"** 형태로 닫지 말 것. 예: "책임은?", "선택은?", "미래는?", "해답은?", "비결은?", "답은?", "방향은?", "뜻은?". 이것은 형식만 질문이고 내용이 공허한 안티패턴이다 — 독자가 "본인이겠지/당연하지"로 즉시 닫아버려 info_gap 이 발생하지 않는다. 반드시 다음 중 하나로 대체한다:
    - **의문사 기반 실질 질문**: "왜 ~인가", "어떻게 ~할까", "얼마까지", "무엇이 달라졌나", "어디서 시작됐나" — 질문 뒤에 구체 재료가 붙어 있어야 함
    - **도발적 평서문**: "[인물/사건]이 [의외 결과]를 만든 [이유/과정]"
    - **서사 아크 평서문**: "[상태 A]에서 [상태 B]로", "[과거 사건]→[현재 과제]"
    few-shot anti-example "후보의 존중하는 정책" / "~의 선택은?" 와 같은 계열이니 절대 금지.</rule>
  <rule id="hook_must_have_tension" priority="critical">&lt;hook_quality_rubric&gt; 4 차원 중 concrete_slot + specificity 조합만으로는 "턱걸이" 다 — 재료만 나열한 평탄체가 된다. 반드시 info_gap 또는 narrative_arc 중 최소 하나를 추가로 채워라.
    - info_gap 달성 방법: 물음표는 필수가 아니다. "왜 ~인가", "어떻게 ~할 것인가", "얼마나/얼마까지", "무엇이 달라졌나" 같은 **의문사 기반 실질 질문**이 기본이다. 질문 자체가 구체 재료를 물고 있어야 한다.
    - narrative_arc 달성 방법(구조만 서술 — 예시 문구 금지): 두 상반 개념의 대치, 과거→현재→미래 변화 서사, 수치 A→수치 B 이동, "에서 ~까지" 스팬 구도, 수량 한정 부사(오직/단/처음), 부정+긍정 이중 축. 선언형 평서문("~으로 ~를 합니다") 은 이 차원을 못 채운다 — 평서체 안에서도 위 구조 중 하나를 집어 넣어야 한다.
    - **중요: stance_summary 에 이미 등장한 대비/변화 구절은 복사하지 말 것**. narrative_arc 는 LLM 이 본문 재료(&lt;slot_opportunities&gt;)로 **새로** 만든 구조여야 한다. stance 구절을 제목 길이로 트림하면 새 구조가 아니라 복붙이다.
    이 룰을 어기면 재료만 나열한 평탄체, 또는 stance 를 복붙한 가짜 tension 중 하나로 떨어진다.</rule>
  <rule id="prefer_concrete_policy_over_abstract_honorific" priority="critical">본문에 정책 고유명(조례명/사업명/시설명/법안명) 이나 구체 수치(퍼센트/개수/금액/비율) 가 존재하면, 제목은 그 중 최소 1개를 직접 인용해야 한다. 다음과 같은 **정책 추상 대체어**로 구체 재료를 덮어쓰면 AEO 매칭이 실패한다:
    - 금지 대체어: "숙원 사업", "4년 숙원", "최대 현안", "핵심 과제", "주요 쟁점", "중점 과제", "대과제", "활성화", "완성", "도약", "혁신" (단독 사용 시)
    - 왜 금지인가: 답변 엔진은 "숙원 사업 완성할까?" 를 어떤 실사용자 쿼리에도 매칭시킬 수 없다. 반면 "취득세 25% 추가 감면", "광역교통망 박촌역 직결", "17개 시도 중 유일" 같은 구체 앵커는 그 자체가 쿼리이자 답이다.
    - 올바른 방법: &lt;slot_opportunities&gt; 의 policy/institution/numeric 카테고리 중 가장 뾰족한 토큰을 골라 제목 본체로 삼고, 추상어는 수식어로만 쓰거나 아예 버려라. 예시 구조: `[지명] [정책명] [수치/상태]`, `[지명] [쟁점], [선택지 A]·[선택지 B] 중 어디로`, `[지명] [사업명], [상위 기준] 수준 도약 [N]가지 조건`.
    이 룰을 어기면 aeo_hollow 로 태깅되어 family fit 점수가 10 → 5 로 강등된다.</rule>
  <rule id="aeo_answerable_query_form" priority="critical">제목은 "실사용자가 답변 엔진·검색창에 칠 법한 쿼리" 형태여야 한다. 기자·주민·기업 담당자가 실제로 입력하는 쿼리는 다음 세 가지 패턴으로 수렴한다:
    1. **사실 조회형**: `[지명] [정책명] [수치/상태]` — 예: `[지명] 취득세 25% 감면, 17개 시도 중 유일 공백 해소`
    2. **선택지 질문형**: `[지명] [쟁점], [고유명 A]·[고유명 B] 중 [의문사]` — 예: `[지명] 광역교통망, [역명 A] 직결·[역명 B] 연결 중 어디로?`
    3. **답변 예고 리스트형**: `[지명] [사업명], [기준] 수준 도약 [N]가지 조건` — 예: `[지명] 테크노밸리, 판교 수준 도약 [N]가지 조건`
    - 금지 유형: 감상형 반어 질문 (`완성할까?`, `가능할까?`, `이뤄낼 수 있을까?`, `해낼 수 있을까?`) — 답이 "아마도/모른다" 류라 답변 엔진이 매칭 못한다.
    - 금지 유형: 인명 중심 쿼리 (`[인물명]의 N년 숙원 사업`) — 사용자는 "누가 했는지"가 아니라 "무엇이 어떻게 되는지"를 검색한다. 인명은 보조 요소로만.
    - 허용 인명 용법: 인명은 주어가 아니라 "출처/권위" 로만 써라. 예: `... 문세종 의원이 발의한 취득세 감면 조례` 처럼 정책명이 본체이고 인명이 수식.
    제목이 위 세 패턴 중 하나에 맞지 않고 &lt;slot_opportunities&gt; 의 정책/수치 카테고리가 비어 있지 않다면, 이 룰에 의해 FAIL 된다.</rule>
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


def _build_previous_attempt_hook_feedback(
    previous_title: str,
    params: Dict[str, Any],
) -> str:
    """직전 제목을 hook rubric 으로 재평가해 "어느 차원이 0점이었는지" 를
    LLM 에게 돌려준다. scorer 에는 손대지 않고 생성 경로에서만 독립적으로
    rubric 을 돌린다. 이렇게 하면 scorer 의 합격 기준은 그대로 두면서도
    재시도 프롬프트가 hook 차원 단위 피드백을 가질 수 있다."""
    from .title_hook_quality import assess_title_hook_quality

    clean_title = str(previous_title or '').strip()
    if not clean_title:
        return ''

    topic = str(params.get('topic') or '') if isinstance(params, dict) else ''
    content = str(params.get('contentPreview') or '') if isinstance(params, dict) else ''
    hook = assess_title_hook_quality(
        clean_title, topic=topic, content=content, params=params or {}
    )
    status = str(hook.get('status') or '').strip()
    hook_score = int(hook.get('score') or 0)
    hook_max = int(hook.get('max') or 0)
    dims = hook.get('dimensions') if isinstance(hook.get('dimensions'), dict) else {}
    missed = hook.get('missed_opportunities') or []

    # flat 이거나 총점이 max 의 1/3 미만일 때만 피드백을 넣는다
    if status != 'flat' and hook_score >= max(1, hook_max // 3):
        return ''

    zero_dims: List[str] = []
    for dim_id, dim_data in dims.items():
        if not isinstance(dim_data, dict):
            continue
        if int(dim_data.get('score') or 0) == 0:
            zero_dims.append(str(dim_id))

    parts: List[str] = []
    if zero_dims:
        parts.append(f'hook 차원 중 0점: {", ".join(zero_dims)}')
    if missed:
        sample_missed = ', '.join(str(m) for m in list(missed)[:3])
        parts.append(f'쓸 수 있었던 재료: {sample_missed}')

    if not parts:
        return ''

    return (
        '<item>직전 제목은 hook 품질이 "평탄(flat)"이었습니다. '
        + ' / '.join(parts)
        + '. 재시도 시 hook_quality_rubric 에서 info_gap(왜/어떻게/미완결) 이나 '
        'narrative_arc(수치+변화/→/에서~까지) 중 하나를 반드시 추가하고, '
        'slot_opportunities 의 재료를 1개 이상 직접 인용하세요.</item>'
    )


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
            hook_feedback = _build_previous_attempt_hook_feedback(previous_title, params)
            if hook_feedback:
                suggestion_items += f"\n    {hook_feedback}"
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
                params=params,
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

    best_suggestions = best_result.get('suggestions', []) if isinstance(best_result, dict) else []
    suggestion_text = ', '.join(best_suggestions) if best_suggestions else '없음'
    raise RuntimeError(
        f"[TitleGen] 제목 생성 실패: {max_attempts}회 재시도 모두 최소 점수 {min_score}점 미달 "
        f"(최고 {best_score}점, 제목: \"{best_title}\", suggestions: {suggestion_text})"
    )

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
    '_compute_similarity_penalty',
    '_extract_book_title',
    '_extract_topic_person_names',
    '_repair_title_for_missing_keywords',
    '_resolve_competitor_intent_title_keyword',
]
