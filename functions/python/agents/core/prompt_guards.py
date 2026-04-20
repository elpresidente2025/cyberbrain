"""StructureAgent ???? ??? ??? ???."""

import re
from typing import Any, Dict, List, Optional

from ..common.editorial import STRUCTURE_SPEC, QUALITY_SPEC
from ..common.h2_guide import H2_MIN_LENGTH, H2_MAX_LENGTH, H2_OPTIMAL_MIN, H2_OPTIMAL_MAX
from ..common.stance_filters import looks_like_hashtag_bullet_line

from .structure_utils import strip_html, normalize_context_text, _xml_text, _xml_cdata, material_key
from .style_guide_builder import _build_style_role_guide_xml

def _is_identity_signature_phrase(text: str) -> bool:
    normalized = normalize_context_text(text)
    if not normalized:
        return False
    return any(
        token in normalized
        for token in ("뼛속까지", "입니다", "저 ", "저는", "이재성!", "저 이재성")
    )

def _build_generation_profile_xml(gen_profile: Optional[Dict[str, Any]]) -> str:
    """GenerationProfile → 초안 생성 제약 XML 블록.

    결정론적 피처 기반 목표치(문장 길이 범위, CV, 선호 종결 어미 등)를
    프롬프트에 주입하여 모델이 실측 문체 통계에 맞춰 쓰도록 유도한다.
    """
    if not isinstance(gen_profile, dict) or not gen_profile:
        return ""

    parts: List[str] = ['<generation_profile priority="high">']
    parts.append("  <overview>아래 수치는 사용자의 실제 문체 통계에서 산출됐다. 초안 생성 시 이 제약을 우선 따른다.</overview>")

    target_len = gen_profile.get("target_sentence_length")
    if isinstance(target_len, (list, tuple)) and len(target_len) == 2:
        try:
            lo = int(target_len[0])
            hi = int(target_len[1])
            if lo > 0 and hi > lo:
                parts.append(
                    f'  <rule id="sentence_length">문장 길이는 평균 {lo}~{hi}자 범위에 맞출 것. 너무 짧거나 너무 긴 문장은 지양.</rule>'
                )
        except (TypeError, ValueError):
            pass

    try:
        target_cv = float(gen_profile.get("target_cv") or 0)
    except (TypeError, ValueError):
        target_cv = 0.0
    if target_cv > 0:
        if target_cv < 0.25:
            cv_hint = "문장 길이를 고르게 유지할 것(변동 최소)."
        elif target_cv < 0.45:
            cv_hint = "문장 길이에 자연스러운 리듬 변화를 줄 것(중간 수준 변동)."
        else:
            cv_hint = "짧은 문장과 긴 문장을 적극 섞을 것(리듬 변동 큼)."
        parts.append(f'  <rule id="sentence_rhythm">{_xml_text(cv_hint)}</rule>')

    try:
        formality = float(gen_profile.get("formality") or 0)
    except (TypeError, ValueError):
        formality = 0.0
    if formality >= 0.75:
        parts.append('  <rule id="formality">격식체(-습니다/-입니다)를 일관되게 유지할 것.</rule>')
    elif formality and formality <= 0.35:
        parts.append('  <rule id="formality">딱딱한 공문서 어투 대신 친근한 존대(-어요/-네요 혼용)를 허용.</rule>')

    preferred_endings = gen_profile.get("preferred_endings") or []
    if isinstance(preferred_endings, list):
        endings = [str(e).strip() for e in preferred_endings if str(e).strip()][:6]
        if endings:
            endings_xml = "".join(f"<item>{_xml_text(e)}</item>" for e in endings)
            parts.append(f"  <preferred_endings>{endings_xml}</preferred_endings>")

    forbidden_patterns = gen_profile.get("forbidden_patterns") or []
    if isinstance(forbidden_patterns, list):
        patterns = [str(p).strip() for p in forbidden_patterns if str(p).strip()][:6]
        if patterns:
            patterns_xml = "".join(f"<item>{_xml_text(p)}</item>" for p in patterns)
            parts.append(f"  <forbidden_patterns>{patterns_xml}</forbidden_patterns>")

    signature_phrases = gen_profile.get("signature_phrases") or []
    if isinstance(signature_phrases, list):
        signatures = [str(s).strip() for s in signature_phrases if str(s).strip()][:6]
        if signatures:
            signatures_xml = "".join(f"<item>{_xml_text(s)}</item>" for s in signatures)
            parts.append(
                f"  <signature_phrases>{signatures_xml}</signature_phrases>"
            )

    style_summary = str(gen_profile.get("style_summary") or "").strip()
    if style_summary:
        parts.append(f"  <style_summary>{_xml_text(style_summary[:300])}</style_summary>")

    parts.append("</generation_profile>")
    return "\n".join(parts)


def _build_style_generation_guard(
    style_fingerprint: Optional[Dict[str, Any]] = None,
    style_guide: str = "",
    user_profile: Optional[Dict[str, Any]] = None,
    generation_profile: Optional[Dict[str, Any]] = None,
    global_alternatives: Optional[Dict[str, List[str]]] = None,
) -> str:
    fingerprint = style_fingerprint if isinstance(style_fingerprint, dict) else {}
    profile = user_profile if isinstance(user_profile, dict) else {}
    gen_profile = generation_profile if isinstance(generation_profile, dict) else {}
    normalized_guide = normalize_context_text(style_guide, sep="\n")
    metadata = fingerprint.get("analysisMetadata") or {}
    try:
        confidence = float(metadata.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0

    max_forbidden_phrases = 40

    static_forbidden = [
        "진정성",
        "울림",
        "획기적으로",
        "명실상부한",
        "주목할 만한",
        "혁신적이고 체계적인",
        "도모하",
        "기하겠",
        "제고하",
        "인사이트",
        "임팩트",
        "시너지",
        "라고 할 수 있습니다",
        "것은 사실입니다",
        "풍부한 경험을 바탕으로",
        "궁극적인 목표",
        "새로운 역사를 써 내려",
        "열정과 헌신",
        "더 나은 미래",
        "더 나은 내일",
        "더 나은 방향",
        "단순한 구호",
        "단순한 구호에 그치지 않고",
        "단순한 숫자",
        "저의 이러한 진정성",
        "마음을 움직이고",
        "강력한 힘이 됩니다",
        "공감과 희망을 줍니다",
        "우선순위를 명확히 하고",
        "일정을 현실적으로 맞추겠습니다",
        "오늘 이 자리에서",
        "소홀히 하지 않았습니다",
    ]
    pattern_forbidden_phrases = [
        "단순한 X가 아니라",
        "단순히 X가 아닌",
        "단순한 X를 넘어",
        "단순히 X에 그치지 않고",
    ]
    forbidden_phrases: List[str] = []
    preferred_replacements: List[str] = []
    preferred_signatures: List[str] = []
    identity_signatures: List[str] = []
    tone_rules: List[str] = []
    sentence_type_rules = [
        # ── 자기인증 금지 (통합) ──
        "경험·경력·이력·성과로 자신의 역량·전문성·리더십을 증명하거나 결론내리지 말 것. "
        "경험은 사실로 끝내고, 그것이 무엇을 증명하는지는 독자에게 맡길 것. "
        "예: '이러한 경험이 전문성을 부여했다', '비전이 도약을 이끌 것이라 확신한다' 모두 금지.",
        # ── 타인 반응·인지도 해설 금지 (통합) ──
        "시민·독자의 반응(감동, 신뢰, 기대, 공감, 인지도 확산)을 추측·보고·해석하지 말 것. "
        "여론조사 수치·언론 보도·직접 인용 같은 검증된 근거가 있을 때만 사실로 쓸 것. "
        "'~라고 믿는다', '~하고 있다' 같은 추정형 완화도 같은 금지.",
        # ── 수치 해석 금지 (통합) ──
        "수치·여론조사 결과를 쓴 뒤 감탄·의미 단정·해석을 덧붙이지 말 것. 수치는 사실에서 멈출 것.",
        # ── 부정-반전 프레임 금지 (통합) ──
        "'단순한/단순히 ... 아니라/아닌/넘어/그치지 않고/머무르지 않고' 패턴을 쓰지 말 것. "
        "명사를 바꿔도, 변형해도 같은 금지. 남길 주장만 바로 말할 것.",
        # ── 범용 개선 구문 ──
        "'더 나은 미래', '더 나은 내일', '더 나은 방향' 대신 등록된 대체어 또는 구체 목표를 직접 쓸 것.",
        # ── 경쟁자 비교 금지 (통합) ──
        "경쟁자 이름으로 '와는 달리', '차별화된', '비해' 같은 우위 비교 구문을 만들지 말 것. "
        "경쟁자 언급은 사실관계·수치 설명에만 쓸 것.",
        # ── 겸손 클리셰 ──
        "겸손 클리셰를 직설적 자신감 문장과 섞지 말 것. 자신감 있는 선언형을 유지할 것.",
        # ── 반복 금지 (통합) ──
        "동일 경력·학력·공약 목록은 원고 전체에서 한 번만. "
        "결론에서 다시 언급하려면 핵심 1~2개만 압축할 것.",
        # ── 보고서체 금지 ──
        "'우선순위를 설정하고, 자원·일정을 현실적으로 맞춘다' 같은 보고서체 금지. "
        "문제 확인, 행동, 해법만 남길 것.",
        # ── 시그니처 정확형 ──
        "등록된 시그니처가 있으면 정확형으로만 쓰고, 띄어쓰기·이름 생략·조사 추가로 변형 금지.",
        # ── 이름+비교조사 ──
        "화자 이름 뒤에 비교 조사 '도'를 붙이지 말 것. '이름도 이깁니다' 대신 '이름, 이깁니다'.",
    ]
    sentence_type_examples: List[tuple[str, str]] = []

    for phrase in pattern_forbidden_phrases:
        if phrase not in forbidden_phrases:
            forbidden_phrases.append(phrase)

    for phrase in static_forbidden:
        if phrase not in forbidden_phrases:
            forbidden_phrases.append(phrase)

    for source in (fingerprint, profile):
        for raw_key in ("forbiddenPhrases", "forbidden_phrases"):
            raw_values = source.get(raw_key) or []
            if not isinstance(raw_values, list):
                continue
            for raw_value in raw_values:
                value = normalize_context_text(raw_value)
                if value and value not in forbidden_phrases:
                    forbidden_phrases.append(value)
                if len(forbidden_phrases) >= max_forbidden_phrases:
                    break
            if len(forbidden_phrases) >= max_forbidden_phrases:
                break

    phrases = fingerprint.get("characteristicPhrases") or {}
    ai_alternatives = fingerprint.get("aiAlternatives") or {}
    for raw_value in (phrases.get("avoidances") or []):
        value = normalize_context_text(raw_value)
        if value and value not in forbidden_phrases:
            forbidden_phrases.append(value)
        if len(forbidden_phrases) >= max_forbidden_phrases:
            break
    for raw_value in (fingerprint.get("avoidances") or []):
        value = normalize_context_text(raw_value)
        if value and value not in forbidden_phrases:
            forbidden_phrases.append(value)
        if len(forbidden_phrases) >= max_forbidden_phrases:
            break

    for raw_key, raw_value in ai_alternatives.items():
        source = normalize_context_text(str(raw_key or "").replace("instead_of_", "").replace("_", " "))
        target = normalize_context_text(raw_value)
        if source and source not in forbidden_phrases:
            forbidden_phrases.append(source)
        if source and target:
            preferred_replacements.append(f'"{source}" 대신 "{target}"')

    # 중앙 상투어 대체어 사전 병합 (per-user aiAlternatives 가 우선)
    if global_alternatives and isinstance(global_alternatives, dict):
        user_sources = {
            normalize_context_text(str(k or "").replace("instead_of_", "").replace("_", " "))
            for k in ai_alternatives
        }
        for cliche, alts in global_alternatives.items():
            cliche_norm = normalize_context_text(cliche)
            if not cliche_norm or cliche_norm in user_sources:
                continue
            if cliche_norm not in forbidden_phrases and len(forbidden_phrases) < max_forbidden_phrases:
                forbidden_phrases.append(cliche_norm)
            if alts:
                top_alt = str(alts[0]).strip()
                if top_alt:
                    preferred_replacements.append(f'"{cliche_norm}" 대신 "{top_alt}"')

    for bucket in ("signatures", "emphatics"):
        for raw_value in (phrases.get(bucket) or []):
            value = normalize_context_text(raw_value)
            if not value:
                continue
            if bucket == "signatures" and _is_identity_signature_phrase(value):
                if value not in identity_signatures:
                    identity_signatures.append(value)
                continue
            if value not in preferred_signatures:
                preferred_signatures.append(value)
            if len(preferred_signatures) >= 4:
                break
        if len(preferred_signatures) >= 4:
            break

    tone = fingerprint.get("toneProfile") or {}
    try:
        directness = float(tone.get("directness") or 0)
    except (TypeError, ValueError):
        directness = 0.0
    try:
        optimism = float(tone.get("optimism") or 0)
    except (TypeError, ValueError):
        optimism = 0.0
    if directness >= 0.6:
        tone_rules.append("자기 해설형 표현보다 단정형 선언을 우선할 것.")
    if optimism >= 0.6:
        tone_rules.append("비장한 호소보다 자신감 있는 미래 선언형을 우선할 것.")

    forbidden_xml = "".join(f"<phrase>{_xml_text(item)}</phrase>" for item in forbidden_phrases[:max_forbidden_phrases])
    replacement_xml = "".join(f"<item>{_xml_text(item)}</item>" for item in preferred_replacements[:8])
    signature_xml = "".join(f"<item>{_xml_text(item)}</item>" for item in preferred_signatures[:4])
    tone_rule_xml = "".join(f"<rule>{_xml_text(item)}</rule>" for item in tone_rules[:3])
    sentence_type_rule_xml = "".join(
        f"<rule>{_xml_text(item)}</rule>" for item in sentence_type_rules
    )
    sentence_type_examples_xml = "".join(
        f"<example><bad>{_xml_text(bad)}</bad><good>{_xml_text(good)}</good></example>"
        for bad, good in sentence_type_examples
    )
    sentence_type_examples_block = (
        f"<sentence_type_examples>{sentence_type_examples_xml}</sentence_type_examples>"
        if sentence_type_examples_xml
        else ""
    )
    style_role_guide_xml = _build_style_role_guide_xml(normalized_guide, fingerprint)
    guide_xml = f"<style_guide>{_xml_cdata(normalized_guide[:1800])}</style_guide>" if normalized_guide else ""
    generation_profile_xml = _build_generation_profile_xml(gen_profile)

    return f"""
<style_generation_guard priority="high" confidence="{confidence:.2f}">
  {style_role_guide_xml}
  {generation_profile_xml}
  <rule id="no_generic_political_boilerplate">아래 금지 표현은 초안 생성 단계에서 직접 쓰지 말 것.</rule>
  <rule id="prefer_registered_replacements">등록된 대체 표현이 있으면 원문 표현 대신 대체 표현을 우선 사용할 것.</rule>
  <rule id="no_sentence_type_reuse">금지 단어만 피하지 말고, 금지된 문장 유형 자체를 피할 것.</rule>
  {'<rule id="examples_are_direction_only">예시는 문장 구조의 방향만 참고하고 그대로 복사하지 말 것.</rule>' if sentence_type_examples_xml else ''}
  <rule id="follow_style_guide_examples">style guide에 실제 사용자 문장이 있으면, 범용 정치문 표현보다 그 전환·호흡·마감 방식을 먼저 따를 것. 다만 문장을 그대로 복사하지 말고 구조와 리듬만 참고할 것.</rule>
  {'<rule id="identity_signature_only">정체성 시그니처는 자기 이름/1인칭 선언 문장(도입·마감)에서만 쓰고, 타인 묘사·복수형·수식어로 변형하지 말 것.</rule>' if identity_signatures else ''}
  {'<rule id="tone_directness">' + _xml_text(tone_rules[0]) + '</rule>' if tone_rules else ''}
  {'<rule id="tone_confidence">' + _xml_text(tone_rules[1]) + '</rule>' if len(tone_rules) > 1 else ''}
  <forbidden_phrases>{forbidden_xml}</forbidden_phrases>
  <forbidden_sentence_types>{sentence_type_rule_xml}</forbidden_sentence_types>
  {sentence_type_examples_block}
  {'<preferred_replacements>' + replacement_xml + '</preferred_replacements>' if replacement_xml else ''}
  {'<preferred_signatures>' + signature_xml + '</preferred_signatures>' if signature_xml else ''}
  {'<identity_signatures>' + ''.join(f'<item>{_xml_text(item)}</item>' for item in identity_signatures[:3]) + '</identity_signatures>' if identity_signatures else ''}
  {guide_xml}
</style_generation_guard>
""".strip()

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
        if card_type == "stance" and looks_like_hashtag_bullet_line(text):
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

def build_poll_focus_bundle_section(bundle: Optional[Dict[str, Any]]) -> str:
    if not isinstance(bundle, dict):
        return ""
    if str(bundle.get("scope") or "").strip().lower() != "matchup":
        return ""

    primary_pair = bundle.get("primaryPair") if isinstance(bundle.get("primaryPair"), dict) else {}
    primary_fact_template = (
        bundle.get("primaryFactTemplate") if isinstance(bundle.get("primaryFactTemplate"), dict) else {}
    )
    speaker = normalize_context_text(primary_pair.get("speaker"))
    opponent = normalize_context_text(primary_pair.get("opponent"))
    speaker_score = normalize_context_text(primary_pair.get("speakerPercent") or primary_pair.get("speakerScore"))
    opponent_score = normalize_context_text(primary_pair.get("opponentPercent") or primary_pair.get("opponentScore"))
    if not speaker or not opponent or not speaker_score or not opponent_score:
        return ""

    secondary_pairs = bundle.get("secondaryPairs") if isinstance(bundle.get("secondaryPairs"), list) else []
    allowed_title_lanes = (
        bundle.get("allowedTitleLanes") if isinstance(bundle.get("allowedTitleLanes"), list) else []
    )
    allowed_h2_kinds = bundle.get("allowedH2Kinds") if isinstance(bundle.get("allowedH2Kinds"), list) else []
    forbidden_metrics = bundle.get("forbiddenMetrics") if isinstance(bundle.get("forbiddenMetrics"), list) else []
    focused_source_text = normalize_context_text(bundle.get("focusedSourceText"), sep="\n")
    primary_fact_sentence = normalize_context_text(primary_fact_template.get("sentence"))
    primary_heading = normalize_context_text(primary_fact_template.get("heading"))

    secondary_lines: List[str] = []
    for idx, raw_pair in enumerate(secondary_pairs[:2], start=1):
        pair = raw_pair if isinstance(raw_pair, dict) else {}
        pair_speaker = normalize_context_text(pair.get("speaker"))
        pair_opponent = normalize_context_text(pair.get("opponent"))
        pair_speaker_score = normalize_context_text(pair.get("speakerPercent") or pair.get("speakerScore"))
        pair_opponent_score = normalize_context_text(pair.get("opponentPercent") or pair.get("opponentScore"))
        if not pair_speaker or not pair_opponent or not pair_speaker_score or not pair_opponent_score:
            continue
        secondary_lines.append(
            f'    <pair index="{idx}">{_xml_text(pair_speaker)} vs {_xml_text(pair_opponent)} '
            f'({_xml_text(pair_speaker_score)} 대 {_xml_text(pair_opponent_score)})</pair>'
        )
    secondary_xml = "\n".join(secondary_lines) if secondary_lines else '    <pair index="0">없음</pair>'

    forbidden_lines = "\n".join(
        f"    <metric>{_xml_text(item)}</metric>"
        for item in forbidden_metrics[:5]
        if normalize_context_text(item)
    )
    if not forbidden_lines:
        forbidden_lines = "    <metric>정당 지지율</metric>"

    title_lane_lines: List[str] = []
    for raw_lane in allowed_title_lanes[:3]:
        lane = raw_lane if isinstance(raw_lane, dict) else {}
        lane_id = normalize_context_text(lane.get("id"))
        lane_label = normalize_context_text(lane.get("label"))
        lane_template = normalize_context_text(lane.get("template"))
        if not lane_id or not lane_template:
            continue
        title_lane_lines.append(
            f'    <lane id="{_xml_text(lane_id)}" label="{_xml_text(lane_label or lane_id)}">'
            f"{_xml_text(lane_template)}</lane>"
        )
    title_lane_xml = "\n".join(title_lane_lines) if title_lane_lines else (
        '    <lane id="fact_direct" label="fact_direct">없음</lane>'
    )

    h2_kind_lines: List[str] = []
    for raw_kind in allowed_h2_kinds[:5]:
        kind = raw_kind if isinstance(raw_kind, dict) else {}
        kind_id = normalize_context_text(kind.get("id"))
        kind_label = normalize_context_text(kind.get("label"))
        kind_template = normalize_context_text(kind.get("template"))
        kind_answer_lead = normalize_context_text(kind.get("answerLead"))
        kind_heading_style = normalize_context_text(kind.get("headingStyle")) or "declarative"
        kind_first_roles = normalize_context_text(kind.get("firstSentenceRoles"), sep=", ")
        kind_followup_roles = normalize_context_text(kind.get("experienceFollowupRoles"), sep=", ")
        kind_allowed_roles = normalize_context_text(kind.get("allowedSentenceRoles"), sep=", ")
        kind_hint = normalize_context_text(kind.get("bodyWriterHint"))
        if not kind_id or not kind_template:
            continue
        h2_kind_lines.append(
            f'    <kind id="{_xml_text(kind_id)}" label="{_xml_text(kind_label or kind_id)}">'
            f"<title>{_xml_text(kind_template)}</title>"
            f"<answer_lead>{_xml_text(kind_answer_lead)}</answer_lead>"
            f"<heading_style>{_xml_text(kind_heading_style)}</heading_style>"
            f"<first_sentence_roles>{_xml_text(kind_first_roles)}</first_sentence_roles>"
            f"<experience_followup_roles>{_xml_text(kind_followup_roles)}</experience_followup_roles>"
            f"<allowed_sentence_roles>{_xml_text(kind_allowed_roles)}</allowed_sentence_roles>"
            f"<body_writer_hint>{_xml_text(kind_hint)}</body_writer_hint>"
            f"</kind>"
        )
    h2_kind_xml = "\n".join(h2_kind_lines) if h2_kind_lines else (
        '    <kind id="primary_matchup" label="주대결 결과"><title>없음</title><answer_lead>없음</answer_lead></kind>'
    )

    return f"""
<poll_focus_bundle priority="critical">
  <scope>matchup</scope>
  <primary_pair>
    <speaker>{_xml_text(speaker)}</speaker>
    <opponent>{_xml_text(opponent)}</opponent>
    <score>{_xml_text(speaker_score)} 대 {_xml_text(opponent_score)}</score>
    <heading_template>{_xml_text(primary_heading or f"{opponent}과의 가상대결, {speaker} {speaker_score} 대 {opponent_score}")}</heading_template>
    <sentence_template>{_xml_text(primary_fact_sentence or f"{speaker}·{opponent} 가상대결에서는 {speaker_score} 대 {opponent_score}로 나타났습니다.")}</sentence_template>
  </primary_pair>
  <secondary_pairs>
{secondary_xml}
  </secondary_pairs>
  <allowed_title_lanes>
{title_lane_xml}
  </allowed_title_lanes>
  <allowed_h2_kinds>
{h2_kind_xml}
  </allowed_h2_kinds>
  <forbidden_metrics>
{forbidden_lines}
  </forbidden_metrics>
  <rules>
    <rule order="1">도입과 핵심 본문은 primary_pair를 중심으로 작성하고, 정당 지지율이나 당내 경선 수치로 중심을 바꾸지 않습니다.</rule>
    <rule order="2">주대결을 설명하는 첫 문장은 sentence_template 구조를 따르며, 인물 이름과 수치를 절단하거나 뒤섞지 않습니다.</rule>
    <rule order="3">소제목(H2)은 allowed_h2_kinds 범위 안에서만 고르되, 질문을 먼저 세우지 말고 해당 섹션 본문이 이미 답한 핵심 논지를 선언형 또는 명사형으로 요약합니다.</rule>
    <rule order="4">각 섹션은 첫 2문장을 먼저 완성한 뒤 H2를 작성합니다. H2는 그 문단이 실제로 답한 내용을 한 문장으로 압축한 것이어야 하며, 본문 없이 H2를 먼저 확정하지 않습니다.</rule>
    <rule order="4.5">각 섹션 문장은 allowed_sentence_roles 안에서만 씁니다. 타인 반응 해석형과 경험 → 역량 인증형은 어떤 섹션에도 넣지 않습니다.</rule>
    <rule order="5">브랜딩 문구를 그대로 H2로 쓰지 말고, 같은 H2 의미를 반복하지 않습니다.</rule>
    <rule order="6">결론 문단은 미완성 절로 끝내지 말고, 모든 문장을 완결된 서술형으로 마무리합니다.</rule>
    <rule order="7">secondary_pairs는 보조 근거로만 짧게 언급하고, 글의 중심 논지를 primary_pair에서 이탈시키지 않습니다.</rule>
  </rules>
  <focused_reference>{_xml_cdata(focused_source_text)}</focused_reference>
</poll_focus_bundle>
""".strip()

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
            "모든 섹션(서론·본론·결론)은 반드시 3개의 <p>를 가져야 합니다. "
            "기존 사실/근거 문장은 최대한 보존하면서 문단을 3개로 맞추십시오."
        )

    if code == 'SECTION_ROLE_CONTRACT':
        return (
            "실패한 섹션만 부분 수정하십시오. "
            "첫 문장은 해당 소제목에 직접 답하는 사실·해법·결론 요약으로 다시 쓰고, "
            "경험 문장 다음에는 사실·행동·구체 결과·현재 해법 연결만 오도록 재작성하십시오."
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
