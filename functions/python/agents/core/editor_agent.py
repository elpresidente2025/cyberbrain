
import logging
import re
from typing import Dict, Any, List, Optional
from ..base_agent import Agent
from ..common.natural_tone import build_natural_tone_prompt

logger = logging.getLogger(__name__)

STYLE_FINGERPRINT_MIN_CONFIDENCE = 0.55
STYLE_GUIDE_MAX_CHARS = 700
STYLE_POLISH_LIMITS = {
    "light": {"max_sentences": 3, "max_ratio": "20%"},
    "medium": {"max_sentences": 6, "max_ratio": "30%"},
}


def _is_identity_signature_phrase(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    return any(
        token in normalized
        for token in ("뼛속까지", "입니다", "저 ", "저는", "이재성!", "저 이재성")
    )


# 선거법 위반 표현 패턴 (Regex)
PLEDGE_REPLACEMENTS = [
    (r'약속드?립니다', '필요성을 말씀드립니다'),
    (r'약속합니다', '필요하다고 봅니다'),
    (r'공약드?립니다', '방향을 제시합니다'),
    (r'공약합니다', '방향을 제시합니다'),
    (r'추진하겠(?:습니다)?', '추진이 필요합니다'),
    (r'마련하겠(?:습니다)?', '마련이 필요합니다'),
    (r'실현하겠(?:습니다)?', '실현이 필요합니다'),
    (r'강화하겠(?:습니다)?', '강화가 필요합니다'),
    (r'확대하겠(?:습니다)?', '확대가 필요합니다'),
    (r'줄이겠(?:습니다)?', '줄이는 노력이 필요합니다'),
    (r'늘리겠(?:습니다)?', '늘리는 방안이 필요합니다'),
    (r'되겠(?:습니다)?', '되는 방향을 모색해야 합니다'),
    (r'하겠(?:습니다)?', '할 필요가 있습니다')
]

# 서명 마커 (요약문 삽입 위치 파악용)
SIGNATURE_REGEX = r'(<p[^>]*>\s*감사합니다\.?\s*<\/p>|<p[^>]*>\s*감사드립니다\.?\s*<\/p>|<p[^>]*>\s*고맙습니다\.?\s*<\/p>|<p[^>]*>\s*[^<]*드림\s*<\/p>|감사합니다|감사드립니다|고맙습니다|사랑합니다|드림)'

class EditorAgent(Agent):
    def __init__(self, name: str = 'EditorAgent', options: Optional[Dict[str, Any]] = None):
        super().__init__(name, options)
        from ..common.gemini_client import get_client, DEFAULT_MODEL
        self.model_name = (options or {}).get('modelName', DEFAULT_MODEL)
        self._client = get_client()

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Refine content using LLM based on validation issues.
        Matches Node.js refineWithLLM logic.
        """
        from ..common.gemini_client import generate_json_async

        content = context.get('content', '')
        title = context.get('title', '')
        validation_result = context.get('validationResult', {})
        keyword_result = context.get('keywordResult', {})
        user_keywords = context.get('keywords', [])
        status = context.get('status', 'active')
        target_word_count = context.get('targetWordCount', 2000)
        polish_mode = bool(context.get('polishMode') is True)
        speaker_name = str(context.get('fullName') or context.get('speakerName') or '').strip()
        style_guide = str(context.get('styleGuide') or '').strip()
        style_fingerprint = context.get('styleFingerprint')
        if not isinstance(style_fingerprint, dict):
            style_fingerprint = {}
        style_polish_mode = str(context.get('stylePolishMode') or '').strip().lower()
        style_instruction = self._build_style_polish_instruction(
            style_guide=style_guide,
            style_fingerprint=style_fingerprint,
            mode=style_polish_mode,
            enabled=polish_mode,
        )

        # 1. Apply Hard Constraints First (Pre-LLM cleanups if any? Node.js does it post-LLM usually, but applyHardConstraintsOnly uses it)
        # We will use LLM first, then apply hard constraints as fallback/final polish.
        
        # Build prompt
        prompt = self.build_editor_prompt(
            content=content,
            title=title,
            validation_result=validation_result,
            keyword_result=keyword_result,
            user_keywords=user_keywords,
            status=status,
            target_word_count=target_word_count,
            speaker_name=speaker_name,
            polish_mode=polish_mode,
            style_instruction=style_instruction,
        )

        if not self._client:
            logger.warning("No client for EditorAgent, returning original")
            return self.apply_hard_constraints(content, title, user_keywords, status)

        # Call LLM
        try:
            result = await generate_json_async(
                prompt,
                model_name=self.model_name,
                temperature=0.7,
                max_output_tokens=8192,
                retries=2,
                required_keys=("content",),
                options={'json_parse_retries': 2},
            )

            new_content = result.get('content', content)
            new_title = result.get('title', title)
            edit_summary = result.get('editSummary', [])

            # 2. Apply Hard Constraints (Post-LLM)
            constrained = self.apply_hard_constraints(
                content=new_content,
                title=new_title,
                user_keywords=user_keywords,
                status=status,
                previous_summary=edit_summary
            )

            # 3. Humanize pass (oh-my-humanizer 스타일 2차 LLM)
            humanized = await self._humanize_pass(
                content=constrained['content'],
                title=constrained['title'],
                speaker_name=speaker_name,
                style_instruction=style_instruction,
            )
            constrained['content'] = humanized.get('content', constrained['content'])
            constrained['editSummary'] = constrained['editSummary'] + humanized.get('changes', [])
            if (
                style_instruction
                and constrained['content'] != content
                and "사용자 문체 일부 반영" not in constrained['editSummary']
            ):
                constrained['editSummary'].append("사용자 문체 일부 반영")

            return constrained

        except Exception as e:
            logger.error(f"EditorAgent failed: {e}")
            # Fallback to hard constraints only
            return self.apply_hard_constraints(content, title, user_keywords, status, error=str(e))

    def build_editor_prompt(
        self,
        content,
        title,
        validation_result,
        keyword_result,
        user_keywords,
        status,
        target_word_count,
        speaker_name: str = "",
        polish_mode: bool = False,
        style_instruction: str = "",
    ):
        issues = []
        
        # 1. Validation issues
        details = {}
        if hasattr(validation_result, 'get'):
             details = validation_result.get('details', {})

             # Election Law
             election_law = details.get('electionLaw', {}) or {}
             election_items = election_law.get('items') or []
             if isinstance(election_items, list) and election_items:
                  election_lines = []
                  for item in election_items[:3]:
                       if not isinstance(item, dict):
                            continue
                       reason = str(item.get('reason') or '선거법 위반 위험').strip()
                       sentence = str(item.get('sentence') or '').strip()
                       repair_hint = str(item.get('repairHint') or '').strip()
                       matched_text = str(item.get('matchedText') or '').strip()
                       detail_parts = [reason]
                       if sentence:
                            detail_parts.append(f'문제 문장: "{sentence}"')
                       if matched_text:
                            detail_parts.append(f'문제 표현: "{matched_text}"')
                       if repair_hint:
                            detail_parts.append(f'수정 가이드: {repair_hint}')
                       election_lines.append("   - " + " | ".join(detail_parts))
                  if election_lines:
                       issues.append(
                            "[CRITICAL] 선거법 위반 표현 발견:\n"
                            + "\n".join(election_lines)
                            + "\n   → 문제 문장만 최소 수정하되, 전언/소문/간접전언 표현은 완전히 제거"
                       )
             elif election_law.get('violations'):
                  violations = ", ".join(election_law['violations'])
                  issues.append(f"[CRITICAL] 선거법 위반 표현 발견: {violations}\n   → 선거법을 준수하는 완곡한 표현으로 수정 (예: '~하겠습니다' -> '~추진합니다')")

             # Repetition
             if details.get('repetition', {}).get('repeatedSentences'):
                  repeated = ", ".join(details['repetition']['repeatedSentences'][:3])
                  issues.append(f"[HIGH] 문장 반복 감지: {repeated}...\n   → 반복을 피하고 다른 표현으로 수정")

        # 3. Keyword issues
        if hasattr(keyword_result, 'get'):
             if not keyword_result.get('passed', True):
                  kw_issues = keyword_result.get('issues', [])
                  if kw_issues:
                       issues.append(f"[HIGH] 키워드 문제:\n" + "\n".join([f"   - {i}" for i in kw_issues]))

        # Format issues list
        if issues:
            issues_text = "\n".join([f"{i+1}. {msg}" for i, msg in enumerate(issues)])
        elif polish_mode:
            issues_text = "(치명 이슈 없음 - 최종 윤문 모드: 가독성/문장 완성도 중심으로 다듬으세요)"
        else:
            issues_text = "(없음 - 전반적인 톤앤매너와 구조만 다듬으세요)"
        
        status_note = ""
        if status in ['준비', '현역']:
             status_note = f"\n⚠️ 작성자 상태: {status} (예비후보 등록 전) - 공약성 표현 엄격 금지"
             
        natural_tone = build_natural_tone_prompt({'severity': 'strict'})
        speaker_guard = ""
        if speaker_name:
            speaker_guard = f"""
7. **화자 정체성 고정**: 이 글의 유일한 1인칭 화자는 \"{speaker_name}\"입니다.
   - \"저는 {speaker_name}\" 또는 \"저는/제가\" 시점만 허용
   - \"저는 [다른 인물명] 후보/시장/의원...\" 형태는 절대 금지
   - 경쟁자 언급은 반드시 3인칭(예: \"주진우 후보는\")으로만 작성
""".strip()
        else:
            speaker_guard = """
7. **화자 정체성 고정**: 1인칭 화자를 다른 인물로 바꾸지 마세요.
   - \"저는 [다른 인물명] 후보/시장/의원...\" 형태는 절대 금지
""".strip()
        
        return f"""당신은 정치 원고 편집 전문가입니다. 아래 원고에서 발견된 문제들을 수정해주세요.

[수정이 필요한 문제들]
{issues_text}
{status_note}

[원본 제목]
{title}

[원본 본문]
{content}

[필수 포함 키워드]
{", ".join(user_keywords) if user_keywords else "(없음)"}

[수정 가이드]
1. **5단 구조 유지**: 서론-본론1-본론2-본론3-결론
2. **소제목**: H2 태그 사용, 뉴스 헤드라인처럼 구체적으로
3. **분량**: 목표 {target_word_count}자 내외 유지
4. **말투 ( tone)**:
{natural_tone}
5. **최종 윤문**: 의미/사실/정치적 입장/수치/고유명사는 유지하고 문장 흐름, 연결어, 호흡만 개선
6. **과편집 금지**: 원문의 핵심 주장과 논리 순서를 바꾸지 말 것
{speaker_guard}
 
다음 JSON 형식으로만 응답하세요:
{{
  "title": "수정된 제목",
  "content": "수정된 본문 (HTML)",
  "editSummary": ["수정 사항 1", "수정 사항 2"]
}}"""

    def _build_style_polish_instruction(
        self,
        *,
        style_guide: str,
        style_fingerprint: Dict[str, Any],
        mode: str = "",
        enabled: bool = False,
    ) -> str:
        if not enabled:
            return ""

        normalized_mode = mode if mode in STYLE_POLISH_LIMITS else "light"
        limits = STYLE_POLISH_LIMITS[normalized_mode]

        metadata = style_fingerprint.get("analysisMetadata") or {}
        try:
            confidence = float(metadata.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0

        normalized_guide = re.sub(r"\s+", " ", str(style_guide or "")).strip()
        if not normalized_guide and confidence < STYLE_FINGERPRINT_MIN_CONFIDENCE:
            return ""

        lines = [
            (
                f"- 전체 재작성은 금지하고 도입, 문단 연결, 강조, 결론 문장 위주로만 "
                f"최대 {limits['max_sentences']}문장 또는 전체의 {limits['max_ratio']} 이내에서 조정합니다."
            ),
            "- 숫자, 날짜, 인명, 지명, 인용, 정책 주장, 법적 표현, 필수 키워드는 절대 바꾸지 않습니다.",
            "- 내용과 논리 구조는 유지하고 말맛과 호흡만 사용자답게 다듬습니다.",
        ]

        if normalized_guide:
            guide_excerpt = normalized_guide[:STYLE_GUIDE_MAX_CHARS]
            if len(normalized_guide) > STYLE_GUIDE_MAX_CHARS:
                guide_excerpt += "..."
            lines.append(f"- 사용자 문체 가이드: {guide_excerpt}")

        if confidence >= STYLE_FINGERPRINT_MIN_CONFIDENCE:
            phrases = style_fingerprint.get("characteristicPhrases") or {}
            patterns = style_fingerprint.get("sentencePatterns") or {}
            tone = style_fingerprint.get("toneProfile") or {}
            alts = style_fingerprint.get("aiAlternatives") or {}

            signature_candidates = []
            identity_signatures: List[str] = []
            for key in ("signatures", "emphatics", "conclusions"):
                raw_values = phrases.get(key) or []
                if isinstance(raw_values, list):
                    for item in raw_values:
                        value = str(item).strip()
                        if not value:
                            continue
                        if key == "signatures" and _is_identity_signature_phrase(value):
                            if value not in identity_signatures:
                                identity_signatures.append(value)
                            continue
                        signature_candidates.append(value)
            deduped_signatures: List[str] = []
            seen_signatures = set()
            for item in signature_candidates:
                if item in seen_signatures:
                    continue
                seen_signatures.add(item)
                deduped_signatures.append(item)
                if len(deduped_signatures) >= 5:
                    break
            if deduped_signatures:
                lines.append(f"- 선호 표현 예시: {', '.join(deduped_signatures)}")
            if identity_signatures:
                lines.append(
                    "- 정체성 시그니처는 자기 이름/1인칭 선언 문장(도입·마감)에서만 사용: "
                    f"{', '.join(identity_signatures[:3])}"
                )

            starters = patterns.get("preferredStarters") or []
            if isinstance(starters, list):
                preferred_starters = [str(item).strip() for item in starters if str(item).strip()][:3]
                if preferred_starters:
                    lines.append(f"- 문장 시작 습관: {', '.join(preferred_starters)}")

            avg_length = patterns.get("avgLength")
            clause_complexity = str(patterns.get("clauseComplexity") or "").strip()
            if avg_length or clause_complexity:
                lines.append(
                    f"- 문장 호흡: 평균 {avg_length or 45}자 안팎, 복잡도 {clause_complexity or 'medium'}"
                )

            tone_tags: List[str] = []
            try:
                formality = float(tone.get("formality") or 0)
            except (TypeError, ValueError):
                formality = 0.0
            try:
                directness = float(tone.get("directness") or 0)
            except (TypeError, ValueError):
                directness = 0.0
            try:
                optimism = float(tone.get("optimism") or 0)
            except (TypeError, ValueError):
                optimism = 0.0
            if formality >= 0.6:
                tone_tags.append("격식 있는 존댓말")
            elif formality and formality <= 0.4:
                tone_tags.append("조금 더 구어적인 호흡")
            if directness >= 0.6:
                tone_tags.append("직설적인 전달")
            if optimism >= 0.6:
                tone_tags.append("희망과 확신의 어조")
            tone_description = str(tone.get("toneDescription") or "").strip()
            if tone_tags or tone_description:
                tone_text = ", ".join(tone_tags) if tone_tags else tone_description
                if tone_description and tone_description not in tone_text:
                    tone_text = f"{tone_text}, {tone_description}"
                lines.append(f"- 어조 목표: {tone_text}")

            replacement_pairs: List[str] = []
            for raw_key, raw_value in list(alts.items())[:4]:
                replacement = str(raw_value or "").strip()
                if not replacement:
                    continue
                source = str(raw_key or "").replace("instead_of_", "").replace("_", " ").strip()
                if not source:
                    continue
                replacement_pairs.append(f'"{source}" -> "{replacement}"')
                if len(replacement_pairs) >= 2:
                    break
            if replacement_pairs:
                lines.append(f"- AI 상투어 대체 예시: {', '.join(replacement_pairs)}")

        return "\n".join(lines)

    async def _humanize_pass(
        self,
        content: str,
        title: str,
        speaker_name: str = "",
        style_instruction: str = "",
    ) -> Dict[str, Any]:
        """oh-my-humanizer 스타일 2차 LLM 패스.

        1단계(감지): AI 투 표현 식별
        2단계(교체): 자연스러운 구어체로 재작성
        3단계(검증): 스스로 잔존 패턴 확인
        """
        from ..common.gemini_client import generate_json_async

        prompt = self._build_humanize_prompt_v2(
            content,
            title,
            speaker_name,
            style_instruction=style_instruction,
        )
        try:
            result = await generate_json_async(
                prompt,
                model_name=self.model_name,
                temperature=0.4,
                max_output_tokens=8192,
                retries=1,
                required_keys=("content",),
                options={'json_parse_retries': 1},
            )
            return {
                'content': result.get('content', content),
                'changes': result.get('changes', []),
            }
        except Exception as e:
            logger.warning(f"humanize_pass 실패 (원본 유지): {e}")
            return {'content': content, 'changes': []}

    def _build_humanize_prompt(
        self,
        content: str,
        title: str,
        speaker_name: str = "",
        style_instruction: str = "",
    ) -> str:
        speaker_note = f'화자는 "{speaker_name}"입니다. 화자 정체성을 바꾸지 마세요.' if speaker_name else ""
        return f"""당신은 AI가 생성한 한국어 텍스트를 인간이 쓴 것처럼 자연스럽게 다듬는 전문가입니다.
{speaker_note}

아래 원고를 3단계로 처리하세요.

[1단계 — 감지]
다음 AI 투 패턴을 찾으세요:
- 대칭 구조 남발: "~뿐만 아니라 ~도", "~은 물론 ~까지", "~을 넘어 ~로"
- 추상 수식어: "혁신적인", "실현 가능한", "진정성", "새로운 미래", "더 나은 내일"
- 형식적 마무리: "함께 만들겠습니다", "함께 나아가겠습니다", "도움이 되었으면 합니다"
- 결론 클리셰: "결론적으로", "요약하자면", "이러한 점에서"
- 과도한 확신: "확신합니다", "분명합니다", "틀림없습니다" (사실 근거 없이)

[2단계 — 교체]
감지된 표현을 아래 원칙으로 교체하세요:
- 추상어 → 구체적 사실/수치/경험으로 대체
- 대칭 구조 → 단문으로 분리하거나 어순 변경
- 형식적 마무리 → 구체적 다짐이나 행동으로 대체
- 수정 시 의미·사실·수치·고유명사는 절대 변경 금지
- 5단 구조(서론-본론1-본론2-본론3-결론) 유지

예시:
BAD:  "이는 단순한 경제 성장을 넘어, 시민 모두가 함께 잘사는 부산을 의미합니다."
GOOD: "부산 경제가 살아나면 시민 삶의 질도 함께 오릅니다."

BAD:  "저의 혁신적인 비전과 실현 가능한 정책들을 통해"
GOOD: "제가 준비한 정책들을 통해"

BAD:  "저의 진정성은 시민 여러분께 큰 공감을 얻을 것이라고 확신합니다."
GOOD: "시민 여러분이 직접 판단해 주시리라 믿습니다."

[3단계 — 검증]
수정 후 스스로 확인: "아직도 AI가 쓴 것처럼 들리는 문장이 있는가?"
있다면 추가 수정.

[원본 제목]
{title}

[원본 본문]
{content}

다음 JSON 형식으로만 응답하세요:
{{
  "content": "수정된 본문 (HTML 태그 유지)",
  "changes": ["교체한 표현 1: BAD → GOOD", "교체한 표현 2: BAD → GOOD"]
}}"""

    def _build_humanize_prompt_v2(
        self,
        content: str,
        title: str,
        speaker_name: str = "",
        style_instruction: str = "",
    ) -> str:
        speaker_note = (
            f'화자는 "{speaker_name}"입니다. 화자 정체성을 바꾸지 마세요.'
            if speaker_name
            else ""
        )
        style_note = ""
        if style_instruction:
            style_note = f"""
[사용자 문체 덧씌우기]
{style_instruction}
- 이 지시는 필요한 문장에만 부분 적용합니다.
- 특히 도입, 연결, 강조, 결론에 우선 적용하고 나머지는 최소한으로 손봅니다.
""".strip()

        return f"""당신은 AI가 생성한 한국어 정치 원고를 더 사람답고 자연스럽게 다듬는 편집자입니다.
{speaker_note}

{style_note}

아래 원고를 3단계로 처리하세요.

[1단계 - 감지]
다음과 같은 AI 티 표현을 찾으세요.
- 과도한 대칭 구조와 추상적 수식
- 뜻은 약한데 그럴듯해 보이는 표현
- 결론과 다짐 문장이 지나치게 형식적인 경우
- 연결어가 기계적으로 반복되는 경우

[2단계 - 교정]
- 의미, 사실, 수치, 고유명사, 정치적 입장은 유지합니다.
- 문장 흐름, 연결, 호흡, 어미 반복만 더 자연스럽게 바꿉니다.
- 사용자 문체 지시가 있으면 전체 재작성 없이 일부 문장에만 반영합니다.
- 5단 구조와 HTML 형식은 유지합니다.

[3단계 - 검증]
- 수정 후에도 원문 의미가 바뀌지 않았는지 다시 확인하세요.
- 과장되거나 캐릭터화된 말투는 피하세요.

[원문 제목]
{title}

[원문 본문]
{content}

반드시 다음 JSON만 반환하세요.
{{
  "content": "수정된 본문 (HTML 유지)",
  "changes": ["수정 사항 1", "수정 사항 2"]
}}"""

    def apply_hard_constraints(self, content: str, title: str, user_keywords: List[str], status: str, previous_summary: List[str] = [], error: str = None) -> Dict[str, Any]:
        """
        Node.js applyHardConstraints logic ported.
        Handles:
        1. Election law neutralization (Regex)
        2. Keyword spam reduction
        3. Double transformation prevention
        """
        updated_content = content
        updated_title = title
        summary = previous_summary[:]
        
        if error:
            summary.append(f"LLM 실패로 인한 자동 보정: {error}")

        # 1. 선거법 위반 표현 필터 (기계적 치환)
        # Node.js switched to LLM delegation, but kept regex as fallback/safety. 
        # Since user complained about rules not being followed, strict regex is safer.
        if status in ['준비', '현역']: # Pre-candidate constraints
            original_content = updated_content
            for pattern, replacement in PLEDGE_REPLACEMENTS:
                updated_content = re.sub(pattern, replacement, updated_content)
                updated_title = re.sub(pattern, replacement, updated_title)
            
            if original_content != updated_content:
                summary.append("선거법 위험 표현 기계적 완화 적용")

        # 2. 과다 키워드 강제 분산 (reduceKeywordSpam)
        # Porting strict logic: max 6 times allowed
        MAX_ALLOWED = 6
        
        for keyword in user_keywords:
            # Count occurrences using simple text search to avoid complex regex issues for now
            # (or use regex to be accurate)
            # Python's re.escape is useful
            escaped_kw = re.escape(keyword)
            # Find all (overlapping not needed usually)
            matches = list(re.finditer(escaped_kw, updated_content))
            count = len(matches)
            
            if count > MAX_ALLOWED:
                excess = count - MAX_ALLOWED
                summary.append(
                    f"키워드 과다('{keyword}' {count}회) 감지 - 문장 파손 방지를 위해 자동 치환은 수행하지 않음 ({excess}회 초과)"
                )

        # 3. Double Transformation Check ("것일 것입니다" -> "것입니다")
        updated_content = re.sub(r'것일 것입니다', '것입니다', updated_content)
        updated_content = re.sub(r'것일 것', '것', updated_content)

        return {
            'content': updated_content,
            'title': updated_title,
            'editSummary': summary,
            'fixed': True
        }
