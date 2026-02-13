"""EditorAgent 프롬프트 빌더.

Node.js `functions/prompts/builders/editor-prompts.js` 포팅.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from agents.common.natural_tone import build_natural_tone_prompt


STRUCTURE_GUIDELINE = """
<structure_guideline priority="critical" description="5단 구조 유지 필수 (황금 비율)">
  <rule id="layout">전체 구조: [서론] - [본론1] - [본론2] - [본론3] - [결론] (총 5개 섹션 유지)</rule>
  <rule id="paragraphs">각 섹션은 반드시 3개의 문단으로 구성 (총 15문단)</rule>
  <rule id="paragraph_length">한 문단은 120~150자 범위</rule>
  <rule id="subheadings">
    <item type="must-not">서론: 소제목 절대 금지 (인사말로 시작)</item>
    <item type="must">본론1~3, 결론: 각 섹션 시작에 뉴스 헤드라인형 소제목 삽입</item>
    <item type="example">이관훈 배우, 부산 방문</item>
  </rule>
  <rule id="preserve_structure">편집/수정 시 섹션-문단 구조를 절대 깨지 마세요. 내용이 늘어나거나 줄어들어도 이 비율을 유지해야 합니다.</rule>
</structure_guideline>
""".strip()

TITLE_GUIDELINE = """
<title_rules priority="critical">
  <rule type="must-not">"XXX 님의 공지", "XXX 후보의 약속" 같은 제목 절대 금지</rule>
  <rule type="must-not">"[지역명] 키워드" 같은 기계적인 대괄호 형식 절대 금지</rule>
  <rule type="must">"부산 경제, 확실하게 살리겠습니다 - 국비 5천억 확보" 처럼 자연스러운 헤드라인 형태로 작성</rule>
  <rule type="must-not">지역명을 제목 앞머리에 말머리처럼 '[부산]' 형태로 붙이는 행위 금지. 문맥상 자연스럽게 녹여낼 것</rule>
</title_rules>
""".strip()

EDITING_INSTRUCTIONS = """
<editing_instructions description="수정 지침">
  <rule id="tone_correction" priority="critical" description="말투 강제 교정 (AI 투 제거)">
    본인에 대한 서술에 추측성 어미 금지: "저는 ~일 것입니다" → "저는 ~생각합니다/판단합니다"
  </rule>
  <rule id="hallucination_prevention" priority="critical" description="할루시네이션(거짓 정보) 방지">
    <item type="must-not">없는 정책 창작 금지: 원문에 없는 구체적인 정책명/수치 지어내기 금지</item>
    <item type="must">방향성 제시: 구체 팩트가 없으면 "지원이 필요합니다", "방안을 모색하겠습니다"</item>
  </rule>
  <rule id="structure_format" description="구조 및 서식 (AEO 최적화 소제목)">
    <item>소제목(H2)은 검색 사용자가 궁금해하는 구체적인 질문이나 데이터 기반 정보 형태로 작성 (15~25자 권장)</item>
    <item>소제목 텍스트는 반드시 h2 태그로 감쌀 것</item>
    <item>문단은 3줄~4줄 정도로 호흡을 짧게 끊어 가독성 확보</item>
  </rule>
  <rule id="seo_keywords" description="검색어/SEO">
    <item>키워드는 문맥에 맞게 자연스럽게 녹이되, 전체 글에서 4~6회까지만 사용</item>
    <item priority="critical">제공된 검색어를 단 한 글자도 바꾸지 말고 그대로 사용</item>
    <item>숫자나 통계는 원문에 있는 것만 정확히 인용</item>
  </rule>
  <rule id="quality_improvement" priority="critical" description="글의 품질 향상 (중복·과장·논리 비약 제거)">
    <item>중복 표현 제거, 과장된 수사 완화, 논리적 비약 방지, 섹션 간 연결 강화</item>
    <item>호칭 문법 교정: "부산광역시 여러분" → "부산광역시민 여러분"</item>
  </rule>
  <rule id="minimal_editing" description="최소한의 수정 원칙">
    <item>위 문제들이 없는 문장은 원문의 맛을 살려 그대로 유지</item>
    <item>선거법 위반 표현만 완곡하게 다듬을 것</item>
  </rule>
</editing_instructions>
""".strip()


def _default_strip_html(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", text or "")).strip()


def build_editor_prompt(
    *,
    content: str,
    title: str,
    issues: Sequence[Dict[str, Any]] | Sequence[Any],
    user_keywords: Sequence[str],
    status: str,
    target_word_count: Optional[int],
    strip_html: Optional[Callable[[str], str]] = None,
) -> str:
    strip_html_fn = strip_html or _default_strip_html
    issues = list(issues or [])
    user_keywords = list(user_keywords or [])

    issues_list = []
    for idx, issue in enumerate(issues, start=1):
        if isinstance(issue, dict):
            severity = str(issue.get("severity", "medium")).upper()
            description = str(issue.get("description") or issue.get("message") or "설명 없음")
            instruction = str(issue.get("instruction") or issue.get("suggestion") or "자연스럽게 수정")
            issues_list.append(f"{idx}. [{severity}] {description}\n   → {instruction}")
        else:
            issues_list.append(f"{idx}. [MEDIUM] {issue}\n   → 자연스럽게 수정")

    status_note = (
        f'\n<author_status status="{status}" stage="예비후보 등록 전" priority="critical">'
        '"~하겠습니다" 같은 공약성 표현 금지'
        "</author_status>"
        if status in {"준비", "현역"}
        else ""
    )

    has_length_issue = any(
        (isinstance(issue, dict) and issue.get("type") == "content_length")
        for issue in issues
    )
    current_length = len((strip_html_fn(content or "")).replace(" ", ""))
    max_target = round(float(target_word_count) * 1.2) if isinstance(target_word_count, (int, float)) else None
    length_guideline = (
        f"\n<length_target min=\"{int(target_word_count)}\" max=\"{max_target}\" current=\"{current_length}\" unit=\"자(공백 제외)\">\n"
        "  <rule type=\"must-not\">새 주제/추신 추가 금지</rule>\n"
        "  <rule type=\"must\">기존 문단의 근거를 구체화해 분량을 맞출 것</rule>\n"
        '  <rule priority="critical" type="must-not">문단 복사 붙여넣기 절대 금지. 동일한 문단이 2번 이상 등장하면 원고 폐기</rule>\n'
        "</length_target>"
        if has_length_issue and isinstance(target_word_count, (int, float)) and max_target is not None
        else ""
    )

    repetition_instruction = (
        '\n\n<repetition_warning priority="critical">'
        "동일한 문장이나 표현을 반복하지 마십시오. "
        "같은 내용을 말하더라도 반드시 다른 단어와 문장 구조를 사용해야 합니다."
        "</repetition_warning>"
        if any((isinstance(issue, dict) and issue.get("type") == "repetition") for issue in issues)
        else ""
    )

    keyword_variation_guide = (
        '\n<keyword_variation_guide>'
        '조사/어미가 붙은 형태(예: "부산의", "경제는")나 '
        '복합 명사(예: "부산경제", "부산 경제")도 키워드 사용으로 인정합니다.'
        "</keyword_variation_guide>"
    )

    natural_tone_guide = build_natural_tone_prompt({"severity": "strict"})
    issue_block = "\n\n".join(issues_list) if issues_list else "(없음 - 전반적인 톤앤매너와 구조만 다듬으세요)"

    return f"""당신은 정치 원고 편집 전문가입니다. 아래 원고에서 발견된 문제들을 수정해주세요.

[수정이 필요한 문제들]
{issue_block}
{status_note}
{STRUCTURE_GUIDELINE}
{length_guideline}
{TITLE_GUIDELINE}

[원본 제목]
{title}

[원본 본문]
{content}

[필수 포함 키워드]
{", ".join(user_keywords) if user_keywords else "(없음)"}

{EDITING_INSTRUCTIONS}
{natural_tone_guide}
{repetition_instruction}
{keyword_variation_guide}
다음 JSON 형식으로만 응답하세요:
{{
  "title": "수정된 제목",
  "content": "수정된 본문 (HTML) - h2, h3, p 태그 구조 준수",
  "editSummary": ["~라는 점입니다 말투 수정", "소제목 태그 적용"]
}}"""


def build_expand_prompt(
    *,
    body: str,
    actual_expansion: int,
    natural_tone_guide: Optional[str] = None,
) -> str:
    tone_guide = natural_tone_guide or build_natural_tone_prompt({"severity": "strict"})
    return f"""당신은 정치 블로그 원고 작성 전문가입니다.
현재 원고의 분량이 부족하여, 독자에게 깊은 울림을 줄 수 있는 마무리 문단을 추가하려 합니다.
아래 본문의 맥락을 이어받아, 정확히 {actual_expansion}자 분량으로 자연스럽게 작성해 주십시오.

<expansion_instructions target_length="{actual_expansion}">
  <rule id="length" priority="critical">반드시 {actual_expansion}자 내외로 작성</rule>
  <rule id="position">본문 맨 마지막(결론부)에 자연스럽게 이어짐</rule>
  <rule id="tone" priority="critical">
{tone_guide}
    블로그 이웃에게 말하듯 부드럽고 호소력 짙은 문체. ("~합니다", "~하겠습니다", "~함께 나아갑시다")
  </rule>
  <rule id="content">
    <item type="must">미래지향적인 다짐이나 독자의 동참을 호소하는 감성적인 내용</item>
    <item type="must-not">새로운 사실(수치, 정책명) 지어내기 금지. 본문의 흐름을 감성적으로 마무리</item>
  </rule>
  <rule id="format">p 태그 하나로 감싸서 작성</rule>
</expansion_instructions>

<source_content>
{body}
</source_content>

다음 JSON 형식으로만 응답하세요:
{{
  "summaryBlock": "<p>...작성된 문단...</p>"
}}"""


EDITOR_CONSTANTS = {
    "STRUCTURE_GUIDELINE": STRUCTURE_GUIDELINE,
    "TITLE_GUIDELINE": TITLE_GUIDELINE,
    "EDITING_INSTRUCTIONS": EDITING_INSTRUCTIONS,
}


# JS 호환 별칭
buildEditorPrompt = build_editor_prompt
buildExpandPrompt = build_expand_prompt


__all__ = [
    "build_editor_prompt",
    "build_expand_prompt",
    "buildEditorPrompt",
    "buildExpandPrompt",
    "EDITOR_CONSTANTS",
]

