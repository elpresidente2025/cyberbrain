
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
        keyword_aliases = context.get('keywordAliases') or {}
        if not isinstance(keyword_aliases, dict):
            keyword_aliases = {}
        status = context.get('status', 'active')
        target_word_count = context.get('targetWordCount', 2000)
        polish_mode = bool(context.get('polishMode') is True)
        speaker_name = str(context.get('fullName') or context.get('speakerName') or '').strip()
        style_guide = str(context.get('styleGuide') or '').strip()
        style_fingerprint = context.get('styleFingerprint')
        if not isinstance(style_fingerprint, dict):
            style_fingerprint = {}
        generation_profile = context.get('generationProfile')
        if not isinstance(generation_profile, dict):
            generation_profile = {}
        style_polish_mode = str(context.get('stylePolishMode') or '').strip().lower()
        style_instruction = self._build_style_polish_instruction(
            style_guide=style_guide,
            style_fingerprint=style_fingerprint,
            generation_profile=generation_profile,
            mode=style_polish_mode,
            enabled=polish_mode,
        )

        # AI alternatives + userNativeWords (style fingerprint → prompt hints)
        _ai_alts: Dict[str, str] = {}
        _sf_alts = style_fingerprint.get("aiAlternatives") if isinstance(style_fingerprint, dict) else None
        if isinstance(_sf_alts, dict):
            for _ak, _av in _sf_alts.items():
                _src = str(_ak or "").replace("instead_of_", "").replace("_", " ").strip()
                _dst = str(_av or "").strip()
                if _src and _dst:
                    _ai_alts[_src] = _dst
        _user_native: set = set()
        if isinstance(style_fingerprint, dict):
            _unw = style_fingerprint.get("userNativeWords")
            if isinstance(_unw, list):
                _user_native = {str(w).strip() for w in _unw if w}
        if _user_native:
            print(f"[EditorAgent] userNativeWords whitelist={sorted(_user_native)}")

        # Kiwi pre-analysis on input content (naturalness hints fed into single LLM call)
        from ..common import korean_morph
        _plain_for_kiwi = re.sub(r'<[^>]+>', ' ', content)
        _plain_for_kiwi = re.sub(r'\s+', ' ', _plain_for_kiwi).strip()
        fp_labels = korean_morph.label_first_person_sentences(_plain_for_kiwi)
        ai_rhetoric_labels = korean_morph.label_ai_rhetoric_sentences(_plain_for_kiwi)
        _fp_label_count = len(fp_labels) if isinstance(fp_labels, list) else 0
        _rl_pre = {k: len(v) for k, v in ai_rhetoric_labels.items()} if ai_rhetoric_labels else {}
        print(f"[EditorAgent] Pre-LLM Kiwi fp_labels={_fp_label_count}건, ai_rhetoric={_rl_pre or 'clean'}")

        # Build prompt (naturalness rules + Kiwi hints merged into single LLM pass)
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
            keyword_aliases=keyword_aliases,
            fp_labels=fp_labels,
            ai_rhetoric_labels=ai_rhetoric_labels,
            ai_alternatives=_ai_alts or None,
            user_native_words=_user_native or None,
        )

        if not self._client:
            logger.warning("No client for EditorAgent, returning original")
            return self.apply_hard_constraints(content, title, user_keywords)

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

            # 3.7. "저는" 문두 비율 검증 (LLM 교정 결과 확인)
            _fp_re = re.compile(r'저는\s')
            _fp_plain = re.sub(r'<[^>]+>', ' ', constrained['content'])
            _fp_plain = re.sub(r'\s+', ' ', _fp_plain).strip()
            _fp_all_sents = [s.strip() for s in re.split(r'(?<=[.?!])\s+', _fp_plain) if len(s.strip()) > 5]
            _fp_matched = [s for s in _fp_all_sents if _fp_re.match(s)]
            _fp_ratio = len(_fp_matched) / len(_fp_all_sents) if _fp_all_sents else 0
            print(f"[EditorAgent] Step 3.7 '저는' 비율={len(_fp_matched)}/{len(_fp_all_sents)}({_fp_ratio:.0%})")
            if _fp_ratio > 0.20 and len(_fp_matched) >= 3:
                constrained['editSummary'].append(
                    f"'저는' 문두 과다 — {len(_fp_matched)}/{len(_fp_all_sents)}문장({_fp_ratio:.0%}), 목표 20% 이하"
                )

            # 3.7b. AI 수사 잔존 검증 (LLM 교정 결과 확인)
            _post_ai_labels = korean_morph.label_ai_rhetoric_sentences(_fp_plain)
            _post_rl_summary = {k: len(v) for k, v in _post_ai_labels.items()} if _post_ai_labels else {}
            print(f"[EditorAgent] Step 3.7b ai_rhetoric={_post_rl_summary or '(clean/None)'}")
            if _post_ai_labels:
                _ai_rhet_instr = {
                    "unsourced_evidence": "출처 없는 근거",
                    "demonstrative_overuse": "지시 관형사",
                    "abstract_inclusive": "추상 포용 수사",
                    "suffix_jeok_overuse": "~적 접미사",
                    "ai_adjective_overuse": "AI 고빈도 수식",
                    "progressive_overuse": "진행형",
                    "vague_source": "모호 출처",
                    "hyperbole": "과장 수사",
                    "negative_parallel": "부정 병렬",
                    "verbose_particle": "장황 조사",
                    "translationese": "번역체",
                    "superficial_chain": "~하며 체인",
                    "cliche_prospect": "클리셰 전망",
                }
                _ai_warnings = []
                for _ai_key, _ai_items in _post_ai_labels.items():
                    if _ai_items:
                        _ai_warnings.append(f"'{_ai_rhet_instr.get(_ai_key, _ai_key)}' {len(_ai_items)}건")
                if _ai_warnings:
                    constrained['editSummary'].append(
                        f"AI 수사 잔존 — {', '.join(_ai_warnings)}"
                    )

            # 3.9. 소스에 없는 허구 수치가 포함된 문장 삭제
            # <p> 블록 전체 삭제 대신 문장 단위로 drop 하여 섹션 문단 수 계약을 보존한다.
            # 문장을 모두 drop 해 <p> 가 비게 되면 그 <p> 는 원본 유지 (허구 수치 잔존 감수 —
            # BLOCKER:STRUCTURE 로 원고가 안 나오는 것보다는 낫다).
            _source_texts = context.get('sourceTexts') or []
            if _source_texts:
                from ..common.fact_guard import build_fact_allowlist, find_unsupported_numeric_tokens
                _fact_allowlist = build_fact_allowlist(_source_texts)
                _fact_plain = re.sub(r'<[^>]+>', ' ', constrained['content'])
                _fact_plain = re.sub(r'\s+', ' ', _fact_plain).strip()
                _fact_check = find_unsupported_numeric_tokens(_fact_plain, _fact_allowlist)
                _unsupported = _fact_check.get('unsupported') or []
                if _unsupported:
                    _fc = constrained['content']
                    _before_fc = _fc
                    _sentences_dropped = 0
                    _empty_paragraphs_preserved = 0

                    def _strip_token_sentences_from_p(match: re.Match) -> str:
                        nonlocal _sentences_dropped, _empty_paragraphs_preserved
                        full = match.group(0)
                        inner_m = re.match(r'(<p[^>]*>)([\s\S]*?)(</p\s*>)', full, re.IGNORECASE)
                        if not inner_m:
                            return full
                        open_tag, inner, close_tag = inner_m.groups()

                        hit_tokens = [tok for tok in _unsupported if tok and tok in inner]
                        if not hit_tokens:
                            return full

                        sentences = re.split(r'(?<=[.!?。！？…])\s+', inner.strip())
                        kept: list = []
                        for sent in sentences:
                            sent_stripped = sent.strip()
                            if not sent_stripped:
                                continue
                            contains_token = any(tok in sent_stripped for tok in hit_tokens)
                            if contains_token:
                                _sentences_dropped += 1
                                continue
                            kept.append(sent_stripped)

                        if not kept:
                            _empty_paragraphs_preserved += 1
                            return full  # <p> 통째 삭제 금지 — 원본 유지
                        return f"{open_tag}{' '.join(kept)}{close_tag}"

                    _fc = re.sub(
                        r'<p\b[^>]*>[\s\S]*?</p\s*>',
                        _strip_token_sentences_from_p,
                        _fc,
                    )

                    if _fc != _before_fc:
                        constrained['content'] = _fc
                        msg = f"소스에 없는 허구 수치 {_unsupported} 포함 문장 {_sentences_dropped}건 삭제"
                        if _empty_paragraphs_preserved:
                            msg += f" (문단 구조 보존을 위해 {_empty_paragraphs_preserved}개 문단은 원본 유지)"
                        constrained['editSummary'].append(msg)
                    print(
                        f"[EditorAgent] Step 3.9 unsupported_numerics: {_unsupported}, "
                        f"sentences_dropped={_sentences_dropped}, "
                        f"paragraphs_preserved_intact={_empty_paragraphs_preserved}"
                    )
                else:
                    print("[EditorAgent] Step 3.9 unsupported_numerics: none")
            else:
                print("[EditorAgent] Step 3.9 skipped (no sourceTexts)")

            # 4. 필수 키워드 최소 등장 검증 (경고만, 자동 치환 안 함)
            MIN_BODY_OCCURRENCES = 3
            plain_body_final = re.sub(r'<[^>]+>', ' ', constrained['content'])
            plain_body_final = re.sub(r'\s+', ' ', plain_body_final).strip()
            for keyword in (user_keywords or []):
                kw = str(keyword).strip()
                if not kw:
                    continue
                body_count = plain_body_final.count(kw)
                if body_count < MIN_BODY_OCCURRENCES:
                    constrained['editSummary'].append(
                        f"필수 키워드 '{kw}' 본문 {body_count}회 — 기준({MIN_BODY_OCCURRENCES}회) 미달, 지시어 과치환 검토"
                    )

            return constrained

        except Exception as e:
            logger.error(f"EditorAgent failed: {e}")
            # Fallback to hard constraints only
            return self.apply_hard_constraints(content, title, user_keywords, error=str(e))

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
        keyword_aliases: Optional[Dict[str, Any]] = None,
        fp_labels: Optional[List[Dict[str, str]]] = None,
        ai_rhetoric_labels: Optional[Dict[str, list]] = None,
        ai_alternatives: Optional[Dict[str, str]] = None,
        user_native_words: Optional[set] = None,
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

        # 문체 지시 (polishMode 시에만)
        style_note = ""
        if style_instruction:
            style_note = (
                "[사용자 문체 덧씌우기 — 도입·연결·강조·결론 문장에만 부분 적용]\n"
                + style_instruction
            )

        # 키워드 변형어 (동어 반복 회피)
        alias_note = ""
        if keyword_aliases and isinstance(keyword_aliases, dict):
            kw_set = set(str(k).strip() for k in (user_keywords or []) if str(k).strip())
            alias_lines = []
            for canonical, aliases in keyword_aliases.items():
                canonical_s = str(canonical).strip()
                if not canonical_s or (kw_set and canonical_s not in kw_set):
                    continue
                if not isinstance(aliases, list) or not aliases:
                    continue
                clean = [str(a).strip() for a in aliases if str(a).strip()]
                if clean:
                    alias_lines.append(f'- "{canonical_s}" → {", ".join(repr(a) for a in clean)}')
            if alias_lines:
                alias_note = (
                    "[키워드 변형어 — 동어 반복 회피, 원형과 합산 범위 내에서 2~3회 사용]\n"
                    + "\n".join(alias_lines)
                )

        # "저는" pro-drop Kiwi 라벨 힌트
        fp_hint_note = ""
        if fp_labels and isinstance(fp_labels, list):
            delete_count = sum(1 for lbl in fp_labels if lbl.get("label") == "삭제 권장")
            if delete_count > 0:
                lines_fp = []
                for lbl in fp_labels:
                    marker = "→ 삭제/분산" if lbl.get("label") == "삭제 권장" else "→ 유지"
                    snippet = str(lbl.get("text", ""))[:60]
                    lines_fp.append(f'  {marker} ({lbl.get("reason", "")}): "{snippet}"')
                fp_hint_note = (
                    f'["저는" 문장별 교정 지시 — 형태소 분석]\n'
                    f'{len(fp_labels)}개 "저는" 문장 중 {delete_count}개 삭제/분산 권장.\n'
                    + "\n".join(lines_fp)
                )

        # AI 수사 패턴 Kiwi 라벨 힌트
        _AI_RHETORIC_INSTRUCTIONS = {
            "unsourced_evidence": "출처 없는 근거 호출 — 수식구 삭제 후 직접 서술",
            "demonstrative_overuse": "지시 관형사 남용 — 절반을 구체 명사로 교체",
            "abstract_inclusive": "추상 포용 수사 반복 — 하나만 남기고 구체 전환",
            "suffix_jeok_overuse": "~적 접미사 남용 — 하나를 풀어쓰거나 구체어 전환",
            "ai_adjective_overuse": "AI 고빈도 관형사 — 절반을 구체 서술로 교체",
            "progressive_overuse": "진행형 남용 — 과거형·현재형·명사형으로 다양화",
            "vague_source": "모호 출처 — 구체 인명·기관·날짜 없으면 삭제",
            "hyperbole": "과장 수사 — 일상 대상의 '전환점/패러다임' 축소 또는 삭제",
            "negative_parallel": "부정 병렬 과다 — 하나만 남기고 직접 연결",
            "verbose_particle": "장황 조사 — '에 있어서' 등을 '에서/으로/은'으로 교체",
            "translationese": "번역체 — '것은 사실이다/에 의해' 등 자연 한국어로 전환",
            "superficial_chain": "~하며 피상 체인 — 3회+ 연결 체인 분리",
            "cliche_prospect": "과제와 전망 클리셰 — 구체 계획·일정으로 교체",
        }
        ai_rhetoric_hint = ""
        if ai_rhetoric_labels:
            _alts = ai_alternatives or {}
            _native = user_native_words or set()
            hints = []
            for key, instruction in _AI_RHETORIC_INSTRUCTIONS.items():
                items = ai_rhetoric_labels.get(key, [])
                if _native and items:
                    items = [i for i in items if not any(nw in i.get("text", "") for nw in _native)]
                if items:
                    alt_note = ""
                    if _alts and key in ("ai_adjective_overuse", "suffix_jeok_overuse", "hyperbole", "cliche_prospect"):
                        matched_alts = []
                        for item in items:
                            txt = item.get("text", "")
                            for src, dst in _alts.items():
                                if src in txt:
                                    matched_alts.append(f'"{src}"→"{dst}"')
                        if matched_alts:
                            alt_note = f" (대체: {', '.join(matched_alts[:3])})"
                    hints.append(f"▸ {instruction}{alt_note} ({len(items)}건):")
                    for item in items[:4]:
                        hints.append(f'  · "{str(item.get("text", ""))[:60]}"')
            if hints:
                ai_rhetoric_hint = (
                    "[AI 수사 패턴 교정 — 형태소 분석 결과, 모두 교정 필수]\n"
                    + "\n".join(hints)
                )

        return f"""당신은 정치 원고 편집 전문가입니다. 아래 원고의 문제를 수정하고 자연어 교정도 함께 수행하세요.

[수정이 필요한 문제들]
{issues_text}
{status_note}

{alias_note}

{fp_hint_note}

{ai_rhetoric_hint}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[자연어 교정 — "저는" 문두 비율]
한국어는 pro-drop 언어입니다. "저는" 문두 ≤ 20%, 연속 2문장 금지.
유지: 대조(직전 주어가 타인), 첫 등장, 강조/책임, 모호성 해소.
생략: 동일 주어 연속, 서술어(-겠습니다)로 화자가 자명, 나열/병렬.
분산: (a) 문중 이동 (b) 주어를 사실·정책으로 전환.
⚠ "저해/저하/저축/저장/저항/저지/저감/저변/저력" 어두의 "저"는 대명사가 아님. 삭제 금지.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{style_note}

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
4. **말투 (tone)**:
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
        generation_profile: Optional[Dict[str, Any]] = None,
        mode: str = "",
        enabled: bool = False,
    ) -> str:
        if not enabled:
            return ""
        gen_profile = generation_profile if isinstance(generation_profile, dict) else {}

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

        if gen_profile:
            target_len = gen_profile.get("target_sentence_length")
            if isinstance(target_len, (list, tuple)) and len(target_len) == 2:
                try:
                    lo = int(target_len[0])
                    hi = int(target_len[1])
                    if lo > 0 and hi > lo:
                        lines.append(f"- 목표 문장 길이: 평균 {lo}~{hi}자 범위 유지")
                except (TypeError, ValueError):
                    pass
            try:
                target_cv = float(gen_profile.get("target_cv") or 0)
            except (TypeError, ValueError):
                target_cv = 0.0
            if target_cv > 0:
                if target_cv < 0.25:
                    lines.append("- 문장 길이 변동: 고르게 유지(변동 최소)")
                elif target_cv < 0.45:
                    lines.append("- 문장 길이 변동: 자연스러운 리듬 변화")
                else:
                    lines.append("- 문장 길이 변동: 짧은 문장과 긴 문장 적극 혼합")
            forbidden = gen_profile.get("forbidden_patterns") or []
            if isinstance(forbidden, list):
                forbidden_clean = [str(p).strip() for p in forbidden if str(p).strip()][:4]
                if forbidden_clean:
                    lines.append(f"- 사용 금지 패턴: {', '.join(forbidden_clean)}")
            preferred_endings = gen_profile.get("preferred_endings") or []
            if isinstance(preferred_endings, list):
                endings_clean = [str(e).strip() for e in preferred_endings if str(e).strip()][:4]
                if endings_clean:
                    lines.append(f"- 선호 종결 어미: {', '.join(endings_clean)}")

            # ── 서술 전략 지시 ────────────────────────────────
            try:
                emo_dir = float(gen_profile.get("emotionDirectness") or gen_profile.get("emotion_directness") or 0.5)
            except (TypeError, ValueError):
                emo_dir = 0.5
            if emo_dir < 0.3:
                lines.append(
                    "- 감정 표현 전략: '안타깝다/감사하다/가슴 아프다' 등 감정 직접 명명을 최소화하세요. "
                    "상황·행동·장면 묘사로 독자가 감정을 추론하도록 유도합니다(show, don't tell)."
                )
            elif emo_dir > 0.7:
                lines.append(
                    "- 감정 표현 전략: 이 화자는 감정을 직접 명명하는 스타일입니다. 억누르지 마세요."
                )

            try:
                cdr = float(gen_profile.get("concreteDetailRatio") or gen_profile.get("concrete_detail_ratio") or 0.4)
            except (TypeError, ValueError):
                cdr = 0.4
            if cdr < 0.25:
                lines.append(
                    "- 구체 디테일: 이 화자는 수치·데이터보다 서사·경험 중심입니다. "
                    "숫자를 과도하게 삽입하지 마세요."
                )
            elif cdr > 0.6:
                lines.append(
                    "- 구체 디테일: 이 화자는 사실·수치·날짜를 적극 사용합니다. "
                    "추상 서술은 구체 근거로 뒷받침하세요."
                )

        return "\n".join(lines)

    def apply_hard_constraints(self, content: str, title: str, user_keywords: List[str], previous_summary: List[str] = [], error: str = None) -> Dict[str, Any]:
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

        # 0. 프롬프트 누출 감지 및 제거
        # personalization_guide 의 hints 조각이 본문에 그대로 복사되는 현상 차단.
        # 문장 단위로 매칭해서, 키프레이즈를 2개 이상 포함하는 문장을 통째로 제거.
        _PROMPT_LEAK_PHRASES = [
            "신선한 관점에서",
            "따뜻하고 친근한 어조",
            "모든 계층을 포용하는 수용적 표현",
            "지역현안과 주민들의 실제 경험을 구체적으로 반영",
            "지역 용어를 사용",
            "개인적 경험과 사례를 풍부하게 포함",
            "구체적인 숫자와 데이터를 적극적으로",
            "미래 비전과 발전 방향을 제시",
            "보수보다 혁신을 강조하는 진보적 관점",
            "안정성과 전통 가치를 중시하는 보수적 관점",
            "균형잡힌 중도적 관점에서",
            "협력과 소통을 강조하는 협업적 표현",
            "격식있고 전문적인 어조",
        ]

        def _remove_leaked_sentences(html: str) -> tuple[str, int]:
            """<p> 블록 내 문장 중 프롬프트 키프레이즈를 2개+ 포함하면 제거."""
            removed = 0

            def _clean_p(m: re.Match) -> str:
                nonlocal removed
                full = m.group(0)
                inner_m = re.match(r'(<p[^>]*>)(.*?)(</p>)', full, re.DOTALL)
                if not inner_m:
                    return full
                open_tag, inner, close_tag = inner_m.groups()
                # 문장 분리
                sents = re.split(r'(?<=[.?!])\s+', inner)
                clean = []
                for s in sents:
                    hit = sum(1 for phrase in _PROMPT_LEAK_PHRASES if phrase in s)
                    if hit >= 2:
                        removed += 1
                    else:
                        clean.append(s)
                if not clean:
                    return ""  # 전체 <p> 가 누출이면 태그째 제거
                return f"{open_tag}{' '.join(clean)}{close_tag}"

            result = re.sub(r'<p[^>]*>.*?</p>', _clean_p, html, flags=re.DOTALL)
            return result, removed

        updated_content, leak_count = _remove_leaked_sentences(updated_content)
        if leak_count:
            summary.append(f"프롬프트 누출 문장 {leak_count}건 제거")

        # 1.2. 고유명사 속격 "의" 삽입 강제 치환
        # LLM이 "계양 테크노밸리" → "계양의 테크노밸리"로 풀어쓰는 것을
        # regex 로 강제 복원. HTML 태그가 끼어있어도 잡는다.
        for kw in (user_keywords or []):
            kw = str(kw).strip()
            if not kw:
                continue
            parts = kw.split()
            if len(parts) < 2:
                continue
            for i in range(len(parts) - 1):
                left = re.escape(parts[i])
                right = re.escape(" ".join(parts[i + 1:]))
                pattern = left + r'의\s*(?:<[^>]*>\s*)*' + right
                replacement = parts[i] + " " + " ".join(parts[i + 1:])
                new_content = re.sub(pattern, replacement, updated_content)
                if new_content != updated_content:
                    updated_content = new_content
                    summary.append(f"고유명사 '{kw}' 속격 분해 강제 복원")

        # 1.5. 문장 레벨 비문 스캔 (치환 없음 — EditorAgent LLM 이 해당 문장을 찾아 교정하도록
        # 문제 문장 원문을 editSummary 에 박아 전달한다.)
        from ..common import korean_morph

        def _truncate_sentence_for_flag(text: str, limit: int = 120) -> str:
            """flag 문자열에 들어갈 문장 축약. 너무 길면 말줄임."""
            stripped = (text or "").strip()
            if len(stripped) <= limit:
                return stripped
            return stripped[: limit - 1] + "…"

        plain_body = re.sub(r'<[^>]+>', ' ', updated_content)
        plain_body = re.sub(r'\s+', ' ', plain_body).strip()
        sentences = korean_morph.split_sentences(plain_body)
        if sentences:  # None 이면 Kiwi 불가 → 스킵
            for sent in sentences:
                if korean_morph.detect_subject_predicate_mismatch(sent) is True:
                    summary.append(
                        f"주술 불일치 — 다음 문장 재검토: \"{_truncate_sentence_for_flag(sent)}\""
                    )
                chain = korean_morph.find_genitive_chain(sent, min_count=3)
                if chain:
                    summary.append(
                        f"속격 '의' 체인 3회+ — 다음 문장 축약: \"{_truncate_sentence_for_flag(sent)}\""
                    )
                if korean_morph.detect_double_nominative(sent) is True:
                    summary.append(
                        f"이중 주어 — 다음 문장 절 분리: \"{_truncate_sentence_for_flag(sent)}\""
                    )
                dup_stems = korean_morph.find_duplicate_stems(sent, min_count=2)
                if dup_stems:
                    stems_str = ", ".join(stem for stem, _n in dup_stems)
                    summary.append(
                        f"어간 반복('{stems_str}') — 다음 문장 유의어 교체: \"{_truncate_sentence_for_flag(sent)}\""
                    )

            # 인접 쌍: "이를 위해" 지시어 역전
            for prev_s, next_s in zip(sentences, sentences[1:]):
                if korean_morph.detect_purpose_pointer_inversion(prev_s, next_s) is True:
                    summary.append(
                        f"지시어 역전 — '이를 위해' 가 부정 상태를 받음. 직전 문장: \"{_truncate_sentence_for_flag(prev_s)}\" / 해당 문장: \"{_truncate_sentence_for_flag(next_s)}\""
                    )

        # 1.55. "저는" 문두 과다 반복 감지 (Kiwi 불필요 — regex 문장 분리)
        # Kiwi split_sentences 가 None 이어도 독립 동작해야 하므로 별도 블록.
        _fp_plain = re.sub(r'<[^>]+>', ' ', updated_content)
        _fp_plain = re.sub(r'\s+', ' ', _fp_plain).strip()
        # regex 기반 문장 분리: 마침표/물음표/느낌표 + 공백/끝 경계
        _fp_sents = [s.strip() for s in re.split(r'(?<=[.?!])\s+', _fp_plain) if len(s.strip()) > 5]
        if _fp_sents:
            _first_person_re = re.compile(r'^저는\s')
            _fp_matched = [s for s in _fp_sents if _first_person_re.match(s)]
            _fp_ratio = len(_fp_matched) / len(_fp_sents)
            if _fp_ratio >= 0.4 and len(_fp_matched) >= 4:
                examples = _fp_matched[:5]
                example_lines = " / ".join(
                    f"\"{_truncate_sentence_for_flag(s, 60)}\"" for s in examples
                )
                summary.append(
                    f"'저는' 문두 과다 반복 — 전체 {len(_fp_sents)}문장 중 {len(_fp_matched)}문장({_fp_ratio:.0%})이 '저는'으로 시작. "
                    f"예시: {example_lines}"
                )

        # 1.6. H2 섹션 첫 문장 지시어 고립 스캔
        # "이 사업/이곳/이 정책/이러한 노력" 류가 섹션 시작 위치에 오면 referent 가
        # 앞 섹션까지 거슬러 가야 해석됨 → EditorAgent LLM 에 경고.
        # LLM 이 무엇으로 복원할지 모호해 손대지 않던 문제를 피하려, 해당 섹션
        # H2 텍스트에서 사용자 키워드 후보를 뽑아 flag 에 명시한다.
        try:
            import re as _re
            # <h2>...</h2> + 그 뒤 첫 <p>...</p> 를 쌍으로 포착 (H2 내용 → 후보 선정에 사용)
            section_pairs = _re.findall(
                r'<h2[^>]*>(.*?)</h2>\s*(<p[^>]*>.*?</p>)',
                updated_content,
                flags=_re.DOTALL | _re.IGNORECASE,
            )
            # 두 종류 패턴:
            # (a) "이/그/저" + 사업·정책·... 류 일반명사 (referent 모호)
            # (b) "이는/이로써/이로/이를/이러한" 단독 지시어 (referent 이전 섹션까지)
            _ORPHAN_WITH_NOUN_RE = _re.compile(
                r'^\s*(?:이|그|저)\s*(?:사업|정책|조치|조례|노력|곳|것|분|때|문제|사안|사례|현상|방침|계획|성과|비전|과제|원칙|방안)'
            )
            _ORPHAN_STANDALONE_RE = _re.compile(
                r'^\s*(?:이는|이로써|이로|이를|이러한)\s'
            )

            def _pick_section_proper_noun(h2_text: str) -> str:
                """섹션 H2 에 등장하는 user_keyword 중 첫 매칭을 반환. 없으면 primary.

                우선순위:
                  1. H2 에 그대로 들어있는 user_keyword 중 첫 매칭 (가장 문맥 근거 있음)
                  2. user_keywords[0] (primary)
                  3. 빈 문자열 (user_keywords 가 없을 때)
                """
                keywords = [str(k).strip() for k in (user_keywords or []) if str(k).strip()]
                if not keywords:
                    return ""
                for kw in keywords:
                    if kw in h2_text:
                        return kw
                return keywords[0]

            for h2_inner, p_block in section_pairs:
                h2_text = _re.sub(r'<[^>]+>', ' ', h2_inner)
                h2_text = _re.sub(r'\s+', ' ', h2_text).strip()
                inner = _re.sub(r'<[^>]+>', ' ', p_block)
                inner = _re.sub(r'\s+', ' ', inner).strip()
                if _ORPHAN_WITH_NOUN_RE.match(inner) or _ORPHAN_STANDALONE_RE.match(inner):
                    quoted = inner[:120] + ('…' if len(inner) > 120 else '')
                    candidate = _pick_section_proper_noun(h2_text)
                    if candidate:
                        summary.append(
                            f"섹션 첫 문장 지시어 고립 — '{candidate}' 로 복원: \"{quoted}\""
                        )
                    else:
                        summary.append(
                            f"섹션 첫 문장 지시어 고립 — 고유명사 원형 복원: \"{quoted}\""
                        )
        except Exception:
            # 지시어 스캔은 보조 — 실패해도 파이프라인 중단하지 않음.
            pass

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

        # Double Transformation 은 content_processor.GRAMMATICAL_ERROR_PATTERNS 에서
        # 더 포괄적으로 처리하므로 여기서는 제거함.

        return {
            'content': updated_content,
            'title': updated_title,
            'editSummary': summary,
            'fixed': True
        }
