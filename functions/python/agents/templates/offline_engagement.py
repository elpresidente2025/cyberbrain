from dataclasses import dataclass


@dataclass
class PromptOption:
    id: str
    name: str
    instruction: str = ""


OFFLINE_MODES = {
    "HOSTED_EVENT": PromptOption(
        id="hosted_event",
        name="행사 주최/초대",
        instruction=(
            "행사의 핵심 정보(일시/장소/참여 방법)를 도입부에서 명확히 제시하고, "
            "행사의 취지와 참가자가 얻을 효익을 구체적으로 설명합니다."
        ),
    ),
    "ATTENDANCE_NOTE": PromptOption(
        id="attendance_note",
        name="행사 참석/방문 후기",
        instruction=(
            "언제/어디서/무엇을 했는지 사실 중심으로 정리하고, "
            "현장에서 확인한 핵심 메시지와 후속 실행 계획을 제시합니다."
        ),
    ),
    "BRIEF_NOTICE": PromptOption(
        id="brief_notice",
        name="단순 일정 공지",
        instruction=(
            "일정 고지를 최우선으로 하되, 독자가 즉시 행동할 수 있도록 "
            "필수 정보와 한 줄 행동 안내를 간결하게 제공합니다."
        ),
    ),
}

ABSTRACT_RHETORIC_TERMS = (
    "뜻깊은 시간",
    "의미 있는 자리",
    "뜨거운 열기",
    "큰 감동",
    "소중한 시간",
    "큰 울림",
    "희망을 안겨",
    "큰 관심",
    "뜻깊은 발걸음",
    "따뜻한 소통의 장",
)

REPLACEMENT_AXES = (
    "사실형(누가/언제/어디서/무엇을)",
    "행동형(다음 단계/실행 계획)",
    "성과형(변화/수치/결과)",
    "현장형(실제 장면/발언/반응)",
    "독자효익형(독자가 얻게 될 도움)",
)


MODE_ALIAS_TO_KEY = {
    "hosted_event": "HOSTED_EVENT",
    "hosted": "HOSTED_EVENT",
    "event_hosted": "HOSTED_EVENT",
    "invite": "HOSTED_EVENT",
    "event_announcement": "HOSTED_EVENT",
    "attendance_note": "ATTENDANCE_NOTE",
    "attendance": "ATTENDANCE_NOTE",
    "attended": "ATTENDANCE_NOTE",
    "visit_note": "ATTENDANCE_NOTE",
    "event_attendance": "ATTENDANCE_NOTE",
    "event_participation": "ATTENDANCE_NOTE",
    "brief_notice": "BRIEF_NOTICE",
    "brief": "BRIEF_NOTICE",
    "notice": "BRIEF_NOTICE",
    "schedule_notice": "BRIEF_NOTICE",
}

ATTENDANCE_HINTS = (
    "참석",
    "방문",
    "다녀왔",
    "후기",
    "간담회에 참여",
    "현장에서 확인",
)

HOSTED_HINTS = (
    "개최",
    "출판기념회",
    "초청",
    "초대",
    "참여 부탁",
    "함께해",
    "모시고",
    "오시는 길",
)

BRIEF_HINTS = (
    "공지",
    "안내",
    "알림",
    "일정",
    "시간",
    "장소",
)


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _xml_escape(value: object) -> str:
    text = str(value or "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _xml_cdata(value: object) -> str:
    text = str(value or "")
    safe_text = text.replace("]]>", "]]]]><![CDATA[>")
    return f"<![CDATA[{safe_text}]]>"


def _normalize_mode_key(raw_value: object) -> str:
    normalized = str(raw_value or "").strip().lower()
    return MODE_ALIAS_TO_KEY.get(normalized, "")


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(token in lowered for token in hints)


def _select_offline_mode(
    options: dict,
    context_analysis: dict,
    topic: str,
    instructions: str,
    target_word_count: int,
) -> PromptOption:
    explicit_mode = _normalize_mode_key(
        options.get("offlineMode")
        or options.get("modeHint")
        or options.get("promptMode")
        or options.get("offlineModeId")
    )
    if explicit_mode:
        return OFFLINE_MODES[explicit_mode]

    context_mode = _normalize_mode_key((context_analysis or {}).get("offlineMode"))
    if context_mode:
        return OFFLINE_MODES[context_mode]

    intent = str((context_analysis or {}).get("intent") or "").strip().lower()
    if intent in {"event_participation", "event_attendance"}:
        return OFFLINE_MODES["ATTENDANCE_NOTE"]
    if intent == "event_announcement":
        return OFFLINE_MODES["HOSTED_EVENT"]
    if intent in {"brief_notice", "schedule_notice"}:
        return OFFLINE_MODES["BRIEF_NOTICE"]

    heuristic_text = "\n".join((str(topic or ""), str(instructions or "")))
    has_attendance_hint = _contains_any(heuristic_text, ATTENDANCE_HINTS)
    has_hosted_hint = _contains_any(heuristic_text, HOSTED_HINTS)
    has_brief_hint = _contains_any(heuristic_text, BRIEF_HINTS)

    if has_attendance_hint:
        return OFFLINE_MODES["ATTENDANCE_NOTE"]
    if has_brief_hint and target_word_count <= 900 and not has_hosted_hint:
        return OFFLINE_MODES["BRIEF_NOTICE"]
    if has_hosted_hint:
        return OFFLINE_MODES["HOSTED_EVENT"]
    if has_brief_hint:
        return OFFLINE_MODES["BRIEF_NOTICE"]
    return OFFLINE_MODES["HOSTED_EVENT"]


def build_offline_engagement_prompt(options: dict) -> str:
    topic = options.get("topic", "")
    author_bio = options.get("authorBio", "")
    author_name = options.get("authorName", "")
    instructions = options.get("instructions", "")
    keywords = options.get("keywords", [])
    target_word_count = _safe_int(options.get("targetWordCount", 2000), 2000)
    personalized_hints = options.get("personalizedHints", "")
    profile_support_context = options.get("profileSupportContext", "")
    profile_substitute_context = options.get("profileSubstituteContext", "")
    news_source_mode = str(options.get("newsSourceMode") or "news").strip().lower()
    context_analysis = options.get("contextAnalysis") or {}
    must_preserve = context_analysis.get("mustPreserve") if isinstance(context_analysis, dict) else {}
    event_date = str((must_preserve or {}).get("eventDate") or "").strip()
    event_location = str((must_preserve or {}).get("eventLocation") or "").strip()
    event_contact = str((must_preserve or {}).get("contactNumber") or "").strip()
    event_cta = str((must_preserve or {}).get("ctaPhrase") or "").strip()

    mode = _select_offline_mode(
        options=options,
        context_analysis=context_analysis,
        topic=str(topic or ""),
        instructions=str(instructions or ""),
        target_word_count=target_word_count,
    )
    safe_author_bio = _xml_escape(author_bio)
    safe_author_name = _xml_escape(author_name)
    safe_topic = _xml_escape(topic)
    safe_instructions = _xml_cdata(instructions)

    keywords_section = ""
    if keywords:
        keywords_text = ", ".join(str(item).strip() for item in keywords if str(item).strip())
        if keywords_text:
            keywords_section = f"""
<context_keywords usage="참고용 - 기계적 반복 금지">
{_xml_escape(keywords_text)}
키워드는 문맥 안에서 자연스럽게 사용하고, 단독 장식 문장으로 분리하지 마십시오.
</context_keywords>
"""

    hints_section = ""
    if personalized_hints:
        hints_section = f"""
<personalization_guide>
{_xml_cdata(personalized_hints)}
</personalization_guide>
"""

    profile_material = ""
    if profile_substitute_context:
        profile_material = str(profile_substitute_context).strip()
    elif profile_support_context:
        profile_material = str(profile_support_context).strip()
    elif personalized_hints:
        profile_material = str(personalized_hints).strip()
    elif author_bio:
        profile_material = str(author_bio).strip()

    self_pr_section = ""
    if profile_material:
        source_label = "프로필 대체자료(법안/정책/성과 우선)" if news_source_mode == "profile_fallback" else "작성자 프로필"
        self_pr_section = f"""
<self_pr_assets source="{source_label}">
  <life_journey>{safe_author_bio}</life_journey>
  <policy_achievement_materials>
{_xml_cdata(profile_material)}
  </policy_achievement_materials>
  <usage_rule>
    삶의 여정(배경/경험)과 법안·정책·성과를 행사 맥락(왜 지금 이 활동이 필요한가)과 연결해 서술하십시오.
    단순 나열형 자기소개는 금지하고, 독자 효익과 연결된 근거 문장으로 제시하십시오.
  </usage_rule>
</self_pr_assets>
"""

    mode_guide = f"""
<offline_mode selected="{mode.id}">
  <selection_rule>
    입력 자료에 미래 일정 + 참여 유도가 중심이면 hosted_event,
    참석/방문 사실 + 관찰/후속 계획이 중심이면 attendance_note,
    사실 전달 중심 단문 공지면 brief_notice를 따릅니다.
  </selection_rule>
  <current_mode_instruction>{mode.instruction}</current_mode_instruction>
</offline_mode>
"""

    event_fact_section = ""
    if any((event_date, event_location, event_contact, event_cta)):
        event_fact_section = f"""
<event_fact_anchor priority="critical">
  <event_date>{_xml_escape(event_date or "(미상)")}</event_date>
  <event_location>{_xml_escape(event_location or "(미상)")}</event_location>
  <event_contact>{_xml_escape(event_contact or "(없음)")}</event_contact>
  <event_cta>{_xml_escape(event_cta or "(없음)")}</event_cta>
  <usage_rule>event_fact_anchor에 있는 날짜/시간/장소/연락처/CTA 문구는 표기와 의미를 유지하여 사용하십시오.</usage_rule>
</event_fact_anchor>
"""

    self_pr_mode_rule = ""
    if mode.id == "brief_notice":
        self_pr_mode_rule = "단순 공지형에서는 자기PR을 1문장 이내로 제한하고, 공지 정보 전달을 우선합니다."
    elif mode.id == "attendance_note":
        self_pr_mode_rule = "참석형에서는 현장 관찰 1개 + 본인 정책/성과 1개를 연결해 후속 실행 계획을 제시합니다."
    else:
        self_pr_mode_rule = "주최/초대형에서는 참가 독자 효익과 연결해 본인 정책/성과 근거를 1~2개 제시합니다."

    mode_agenda_rule = ""
    mode_ux_rule = ""
    mode_scene_rule = ""
    mode_summary_rule = ""
    reader_benefit_rule = ""
    if mode.id == "brief_notice":
        mode_agenda_rule = (
            "단순 공지형은 일정·장소·대상·참여 방법을 우선하고, "
            "정책 아젠다는 1문장 이내 참고 수준으로만 제시합니다."
        )
        mode_ux_rule = "첫 문단은 1~2문장 요약 공지로 작성하고, 필요 시 h2 1~2개 이내로만 구성합니다."
        mode_summary_rule = "첫 번째 p 문단은 1~2문장 요약 공지(일시/장소/참여 방법)로 작성합니다."
        mode_scene_rule = "공지형에서는 분위기 묘사보다 정보 정확성을 우선합니다."
        reader_benefit_rule = "공지형에서도 독자가 즉시 행동할 수 있도록 준비물/참여 방법/문의 동선을 1~2문장으로 안내합니다."
    elif mode.id == "attendance_note":
        mode_agenda_rule = (
            "참석형은 현장에서 드러난 핵심 사회 문제 1~2개를 제시하고, "
            "각 문제에 대해 본인의 정책/법안/예산/제도개선 해법을 최소 1개 이상 연결합니다."
        )
        mode_ux_rule = (
            "첫 문단 2~3문장 브리핑 후, h2 2~3개(예: 행사 한눈에 보기 / 현장에서 확인한 핵심 / "
            "후속 실행 계획)로 구조화합니다."
        )
        mode_summary_rule = "첫 번째 p 문단은 2~3문장 브리핑(무엇을 봤는지 + 핵심 메시지)으로 작성합니다."
        mode_scene_rule = (
            "현장감은 source_material에 근거가 있는 장면/발언/반응만 사용합니다. "
            "근거 없는 감각 묘사(소리/표정/구호) 창작은 금지합니다."
        )
        reader_benefit_rule = "행사에 오지 못한 독자를 위해 현장에서 확인한 사실과 후속 실행 계획을 2~3문장으로 요약합니다."
    else:
        mode_agenda_rule = (
            "주최/초대형은 이번 행사에서 다룰 핵심 문제 1~2개와 정책적 해법(법안·예산·제도 개선) "
            "최소 1개를 짝지어 제시합니다."
        )
        mode_ux_rule = (
            "첫 문단 2~3문장 브리핑 후, h2 2~3개(예: 행사 한눈에 보기 / 왜 지금 중요한가 / "
            "참여 방법과 기대 효과)로 구조화합니다."
        )
        mode_summary_rule = "첫 번째 p 문단은 2~3문장 브리핑(행사 핵심 정보 + 참여 효익)으로 작성합니다."
        mode_scene_rule = (
            "현장감 표현은 행사 정보와 참여 효익을 보강하는 범위에서만 사용하고, "
            "과장된 분위기 묘사는 지양합니다."
        )
        reader_benefit_rule = "행사에 오지 못한 독자도 핵심을 파악할 수 있도록 알게 될 것/도움이 될 것을 2~3문장으로 요약합니다."

    abstract_terms_text = ", ".join(ABSTRACT_RHETORIC_TERMS)
    replacement_axes_text = ", ".join(REPLACEMENT_AXES)
    mode_failure_pattern_rule = ""
    if mode.id == "brief_notice":
        mode_failure_pattern_rule = "공지형에서는 배경 서사(경력/이력) 전개를 1문장 이내로 제한하고, 일정/장소/참여 동선을 누락하지 않습니다."
    elif mode.id == "attendance_note":
        mode_failure_pattern_rule = "참석형에서는 초대·홍보형 문구를 반복하지 말고, 관찰 사실과 후속 실행 계획을 우선합니다."
    else:
        mode_failure_pattern_rule = "초대형에서는 경력 소개를 길게 늘이지 말고, 도입 2문단 이내에 행사 핵심 정보(일시/장소/참여 방법)를 반드시 제시합니다."

    prompt = f"""
<task type="오프라인 접점 콘텐츠" system="전자비서관">

<basic_info>
  <author>{safe_author_bio}</author>
  <author_name>{safe_author_name}</author_name>
  <topic>{safe_topic}</topic>
  <target_length unit="자(공백 제외)">{target_word_count or 2000}</target_length>
</basic_info>

<source_material>
{safe_instructions}
</source_material>

{keywords_section}{hints_section}
{self_pr_section}
{mode_guide}
{event_fact_section}

<writing_rules priority="critical">
  <rule id="fact_first">오프라인 활동의 사실 정보(일시/장소/활동 성격)를 먼저 제시합니다.</rule>
  <rule id="fact_preservation">source_material과 event_fact_anchor에 있는 날짜/시간/장소/수치는 표기와 의미를 유지합니다.</rule>
  <rule id="no_fact_fabrication">source_material에 없는 인물·수치·발언·성과를 창작하지 않습니다.</rule>
  <rule id="missing_info_strategy">근거가 약한 부분은 과장된 수사로 채우지 말고, 확인 가능한 사실과 실행 계획 중심으로 압축 서술합니다.</rule>
  <rule id="self_pr_connection">자기PR은 반드시 오프라인 활동 맥락과 연결합니다. "삶의 여정 → 정책/성과 → 이번 활동의 의미" 흐름을 유지하십시오.</rule>
  <rule id="self_pr_evidence">법안/정책/성과 중 최소 1개를 근거로 제시하고, 독자에게 어떤 변화가 있는지 함께 설명합니다.</rule>
  <rule id="self_pr_mode">{self_pr_mode_rule}</rule>
  <rule id="agenda_pairing">{mode_agenda_rule}</rule>
  <rule id="reader_benefit_block">{reader_benefit_rule}</rule>
  <rule id="scene_evidence">{mode_scene_rule}</rule>
  <rule id="contextual_keyword_only">장소 키워드는 해당 문단의 핵심 주장/정보와 결합해 사용합니다.</rule>
  <rule id="no_orphan_keyword_sentence">"한편/아울러/또한" 접속사로 시작하는 키워드 장식 문장 반복 금지.</rule>
  <rule id="abstract_rhetoric_control">추상 수사어({abstract_terms_text})를 사용할 때는 같은 문단에 근거가 되는 장면/발언/수치/결과를 함께 제시합니다.</rule>
  <rule id="abstract_rewrite_hint">추상 표현은 {replacement_axes_text} 축으로 재작성해 정보 밀도를 높입니다.</rule>
  <rule id="no_tail_duplication">후원 안내/슬로건은 본문에서 반복 작성하지 않고 시스템 부착에 맡깁니다.</rule>
  <rule id="end_once">마무리 문단은 1회만 작성하고, 마무리 뒤에 본문을 덧붙이지 않습니다.</rule>
  <rule id="attendance_balance">참석형일 경우 현장 사실(무엇을 봤는지)과 의미(왜 중요한지)를 함께 제시합니다.</rule>
  <rule id="invite_balance">초대형일 경우 참여 방법과 참석 효익을 분리해 명확히 안내합니다.</rule>
  <rule id="self_pr_density_cap">자기PR·경력 서술은 본문 전체의 30%를 넘기지 말고, 나머지는 행사 정보/독자 효익/행동 안내로 구성합니다.</rule>
  <rule id="failure_pattern_guard">{mode_failure_pattern_rule}</rule>
</writing_rules>

<output_format_rules>
  <rule id="html">본문은 HTML 태그만 사용: p, h2, strong, ul, ol</rule>
  <rule id="tone">1인칭 화자 일관 유지. 문장 종결은 정중체로 통일.</rule>
  <rule id="clarity">중복 문장/상투 문구를 줄이고 정보 밀도를 높입니다.</rule>
  <rule id="blog_summary">{mode_summary_rule}</rule>
  <rule id="blog_h2_structure">{mode_ux_rule}</rule>
</output_format_rules>

<quality_verification>
  <rule id="sentence_completeness">모든 문장을 완결형으로 작성하고 조사 누락을 금지합니다.</rule>
  <rule id="date_time_integrity">입력에 있는 날짜/시간/장소/고유명사는 축약하거나 임의 변경하지 않습니다.</rule>
  <rule id="event_info_presence">도입 2문단 이내에 일시/장소/활동 성격(또는 참여 방식) 중 최소 2개 이상을 제시합니다.</rule>
  <rule id="cta_placement">CTA는 결론부에서 1회만 제시하고, 동일 의미 문구 반복을 금지합니다.</rule>
  <rule id="no_placeholder">"(예시)", "(구체적 사례)" 같은 자리표시자 문구를 남기지 않습니다.</rule>
  <rule id="single_closing">마무리/결론 문단은 1회만 작성하고, 마무리 뒤에 본문을 재개하지 않습니다.</rule>
  <rule id="mode_consistency">선택된 모드({mode.id})의 목적에서 벗어나는 전개(과도한 자기서사/정보 누락)를 금지합니다.</rule>
</quality_verification>

<output_format>
출력은 반드시 아래 XML 태그 형식만 사용:

<title>
[제목 - 35자 이내]
</title>

<content>
[HTML 본문]
</content>

<hashtags>
[해시태그 3~5개]
</hashtags>
</output_format>

</task>
"""
    return prompt.strip()
