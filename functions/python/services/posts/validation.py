"""원고 품질/선거법/키워드 휴리스틱 검증 모듈.

Node.js `functions/services/posts/validation.js`의 핵심 검증 로직 포팅.
"""

from __future__ import annotations

import json
import html
import logging
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from agents.common.election_rules import get_election_stage
from agents.common.fact_guard import extract_numeric_tokens, find_unsupported_numeric_tokens
from agents.common.legal import ViolationDetector

from .corrector import apply_corrections, summarize_violations
from .critic import has_hard_violations, run_critic_review, summarize_guidelines
from .generation_stages import GENERATION_STAGES, create_progress_state, create_retry_message

logger = logging.getLogger(__name__)


# ============================================================================
# 선거법 하이브리드 검증 상수
# ============================================================================

ALLOWED_ENDINGS: List[re.Pattern[str]] = [
    re.compile(r"입니다\.?$"),
    re.compile(r"습니다\.?$"),
    re.compile(r"됩니다\.?$"),
    re.compile(r"했습니다\.?$"),
    re.compile(r"되었습니다\.?$"),
    re.compile(r"였습니다\.?$"),
    re.compile(r"었습니다\.?$"),
    re.compile(r"해야\s*합니다\.?$"),
    re.compile(r"되어야\s*합니다\.?$"),
    re.compile(r"필요합니다\.?$"),
    re.compile(r"바랍니다\.?$"),
    re.compile(r"생각합니다\.?$"),
    re.compile(r"봅니다\.?$"),
    re.compile(r"압니다\.?$"),
    re.compile(r"느낍니다\.?$"),
    re.compile(r"[까요까]\?$"),
    re.compile(r"[습읍]니까\?$"),
    re.compile(r"라고\s*합니다\.?$"),
    re.compile(r"답니다\.?$"),
]

EXPLICIT_PLEDGE_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"약속드립니다"),
    re.compile(r"약속합니다"),
    re.compile(r"공약합니다"),
    re.compile(r"반드시.*하겠습니다"),
    re.compile(r"꼭.*하겠습니다"),
    re.compile(r"제가.*하겠습니다"),
    re.compile(r"저는.*하겠습니다"),
    re.compile(r"당선되면"),
    re.compile(r"당선\s*후"),
]


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", text or "")).strip()


def extract_sentences(text: str) -> List[str]:
    plain_text = _strip_html(text)
    if not plain_text:
        return []
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.?!])\s+", plain_text)
        if sentence and len(sentence.strip()) > 10
    ]


def is_allowed_ending(sentence: str) -> bool:
    return any(pattern.search(sentence or "") for pattern in ALLOWED_ENDINGS)


def is_explicit_pledge(sentence: str) -> bool:
    return any(pattern.search(sentence or "") for pattern in EXPLICIT_PLEDGE_PATTERNS)


def contains_pledge_candidate(sentence: str) -> bool:
    return bool(re.search(r"겠[습어]", sentence or ""))


def _extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return None
    text = re.sub(r"```(?:json)?\s*([\s\S]*?)```", r"\1", text).strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


async def check_pledges_with_llm(
    sentences: Sequence[str],
    model_name: str = "gemini-2.5-flash",
) -> List[Dict[str, Any]]:
    if not sentences:
        return []

    prompt = f"""당신은 대한민국 선거법 전문가입니다.
아래 문장들이 "정치인 본인의 선거 공약/약속"인지 판단하세요.

[판단 기준]
- 공약 O: 정치인 본인이 주어로, 미래에 ~하겠다는 약속
  예: "일자리를 만들겠습니다", "교통 문제를 해결하겠습니다"

- 공약 X: 다음은 공약이 아님
  예: "비가 오겠습니다" (날씨 예측)
  예: "좋은 결과가 있겠습니다" (희망/기대)
  예: "정부가 해야겠습니다" (제3자 당위)
  예: "함께 만들어가겠습니다" (시민 참여 호소, 맥락에 따라)

[검증 대상 문장]
{chr(10).join(f'{i + 1}. "{s}"' for i, s in enumerate(sentences))}

[출력 형식 - JSON]
{{
  "results": [
    {{ "index": 1, "isPledge": true/false, "reason": "판단 근거" }},
    ...
  ]
}}"""

    try:
        from agents.common.gemini_client import generate_content_async

        response = await generate_content_async(
            prompt,
            model_name=model_name,
            temperature=0.1,
            response_mime_type="application/json",
        )
        parsed = _extract_json_object(response) or {}
        results = parsed.get("results")
        if not isinstance(results, list):
            raise ValueError("results 필드 없음")

        normalized: list[Dict[str, Any]] = []
        for idx, item in enumerate(results):
            if not isinstance(item, dict):
                continue
            item_index = int(item.get("index", idx + 1))
            source_idx = max(1, item_index) - 1
            sentence = sentences[source_idx] if source_idx < len(sentences) else sentences[idx]
            normalized.append(
                {
                    "sentence": sentence,
                    "isPledge": bool(item.get("isPledge")),
                    "reason": str(item.get("reason") or "판단 근거 없음"),
                }
            )
        return normalized
    except Exception as exc:
        logger.warning("LLM 공약 검증 실패, 보수적 처리: %s", exc)
        return [
            {"sentence": sentence, "isPledge": True, "reason": "LLM 검증 실패 - 보수적 처리"}
            for sentence in sentences
        ]


def _collect_bribery_violations(plain_text: str) -> List[Dict[str, Any]]:
    violations: list[Dict[str, Any]] = []
    for item in ViolationDetector.check_bribery_risk(plain_text):
        matches = item.get("matches") or []
        sentence = matches[0] if matches else ""
        violations.append(
            {
                "sentence": sentence,
                "type": "BRIBERY",
                "reason": item.get("reason") or "기부행위 금지 위반 위험",
            }
        )
    return violations


def _collect_fact_violations(plain_text: str) -> List[Dict[str, Any]]:
    violations: list[Dict[str, Any]] = []
    for item in ViolationDetector.check_fact_claims(plain_text):
        matches = item.get("matches") or item.get("claims") or []
        sentence = matches[0] if matches else ""
        severity = str(item.get("severity") or "").upper()
        violations.append(
            {
                "sentence": sentence,
                "type": "FACT_CRITICAL" if severity == "CRITICAL" else "FACT_WARNING",
                "reason": item.get("reason") or "허위사실/비방 위험",
            }
        )
    return violations


async def detect_election_law_violation_hybrid(
    content: str,
    status: str | None,
    title: str = "",
    *,
    model_name: str = "gemini-2.5-flash",
) -> Dict[str, Any]:
    if not status:
        return {"passed": True, "violations": [], "skipped": True}

    election_stage = get_election_stage(status)
    if not election_stage or election_stage.get("name") != "STAGE_1":
        return {"passed": True, "violations": [], "skipped": True}

    full_text = f"{title or ''} {content or ''}"
    sentences = extract_sentences(full_text)
    violations: list[Dict[str, Any]] = []
    llm_candidates: list[str] = []

    for sentence in sentences:
        if is_explicit_pledge(sentence):
            violations.append(
                {
                    "sentence": sentence[:60] + ("..." if len(sentence) > 60 else ""),
                    "type": "EXPLICIT_PLEDGE",
                    "reason": "명시적 공약 표현",
                }
            )
            continue
        if is_allowed_ending(sentence):
            continue
        if contains_pledge_candidate(sentence):
            llm_candidates.append(sentence)

    if llm_candidates:
        llm_results = await check_pledges_with_llm(llm_candidates, model_name=model_name)
        for result in llm_results:
            if result.get("isPledge"):
                sentence = str(result.get("sentence") or "")
                violations.append(
                    {
                        "sentence": sentence[:60] + ("..." if len(sentence) > 60 else ""),
                        "type": "LLM_DETECTED",
                        "reason": str(result.get("reason") or "공약성 표현"),
                    }
                )

    plain_text = _strip_html(full_text)
    violations.extend(_collect_bribery_violations(plain_text))
    violations.extend(_collect_fact_violations(plain_text))

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "status": status,
        "stage": election_stage.get("name"),
        "stats": {
            "totalSentences": len(sentences),
            "llmChecked": len(llm_candidates),
            "violationCount": len(violations),
        },
    }


# ============================================================================
# 휴리스틱 품질 검증
# ============================================================================


def detect_sentence_repetition(content: str) -> Dict[str, Any]:
    plain_text = _strip_html(content)
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.?!])\s+", plain_text)
        if sentence and len(sentence.strip()) > 20
    ]
    normalized = [re.sub(r"\s+", "", sentence).lower() for sentence in sentences]
    counts: Dict[str, Dict[str, Any]] = {}
    repeated_sentences: list[str] = []

    for idx, sentence in enumerate(normalized):
        if sentence not in counts:
            counts[sentence] = {"count": 0, "original": sentences[idx]}
        counts[sentence]["count"] += 1

    for value in counts.values():
        if value["count"] >= 2:
            original = str(value["original"])
            repeated_sentences.append(f"\"{original[:50]}...\" ({value['count']}회 반복)")

    return {"passed": len(repeated_sentences) == 0, "repeatedSentences": repeated_sentences}


def detect_phrase_repetition(content: str) -> Dict[str, Any]:
    plain_text = _strip_html(content)
    words = [word for word in re.split(r"\s+", plain_text) if word]
    phrase_count: Dict[str, int] = {}

    for n in range(3, 7):
        for idx in range(0, len(words) - n + 1):
            phrase = " ".join(words[idx : idx + n])
            if len(phrase) < 10:
                continue
            phrase_count[phrase] = phrase_count.get(phrase, 0) + 1

    over_limit = sorted(
        [(phrase, count) for phrase, count in phrase_count.items() if count >= 3],
        key=lambda item: len(item[0]),
        reverse=True,
    )

    covered: set[str] = set()
    repeated_phrases: list[str] = []
    for phrase, count in over_limit:
        if any(existing.find(phrase) >= 0 for existing in covered):
            continue
        covered.add(phrase)
        repeated_phrases.append(f"\"{phrase[:40]}{'...' if len(phrase) > 40 else ''}\" ({count}회 반복)")

    return {"passed": len(repeated_phrases) == 0, "repeatedPhrases": repeated_phrases}


def detect_near_duplicate_sentences(content: str, threshold: float = 0.6) -> Dict[str, Any]:
    plain_text = _strip_html(content)
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.?!])\s+", plain_text)
        if sentence and len(sentence.strip()) > 25
    ]
    word_sets: list[set[str]] = []
    for sentence in sentences:
        words = [word for word in re.split(r"\s+", re.sub(r"[.?!,]", "", sentence)) if len(word) >= 2]
        word_sets.append(set(words))

    similar_pairs: list[Dict[str, Any]] = []
    for i in range(len(sentences)):
        for j in range(i + 1, len(sentences)):
            set_a = word_sets[i]
            set_b = word_sets[j]
            if len(set_a) < 3 or len(set_b) < 3:
                continue
            intersection = len(set_a.intersection(set_b))
            union = len(set_a.union(set_b))
            similarity = (intersection / union) if union else 0
            if similarity < threshold:
                continue
            if similarity >= 0.95:
                continue
            similar_pairs.append(
                {
                    "a": sentences[i][:50] + ("..." if len(sentences[i]) > 50 else ""),
                    "b": sentences[j][:50] + ("..." if len(sentences[j]) > 50 else ""),
                    "similarity": round(similarity * 100),
                }
            )

    return {"passed": len(similar_pairs) == 0, "similarPairs": similar_pairs}


def detect_election_law_violation(content: str, status: str | None, title: str = "") -> Dict[str, Any]:
    if not status:
        return {"passed": True, "violations": [], "skipped": True}

    election_stage = get_election_stage(status)
    if not election_stage or election_stage.get("name") != "STAGE_1":
        return {"passed": True, "violations": [], "skipped": True}

    plain_text = _strip_html(f"{title or ''} {content or ''}")

    pledge_patterns = [
        r"추진하겠습니다",
        r"실현하겠습니다",
        r"만들겠습니다",
        r"해내겠습니다",
        r"전개하겠습니다",
        r"제공하겠습니다",
        r"활성화하겠습니다",
        r"개선하겠습니다",
        r"확대하겠습니다",
        r"강화하겠습니다",
        r"설립하겠습니다",
        r"구축하겠습니다",
        r"마련하겠습니다",
        r"지원하겠습니다",
        r"해결하겠습니다",
        r"바꾸겠습니다",
        r"펼치겠습니다",
        r"이루겠습니다",
        r"열겠습니다",
        r"세우겠습니다",
        r"이뤄내겠습니다",
        r"해드리겠습니다",
        r"드리겠습니다",
        r"약속드리겠습니다",
        r"바꿉니다",
        r"만듭니다",
        r"이룹니다",
        r"해결합니다",
        r"약속합니다",
        r"실현합니다",
        r"책임집니다",
    ]

    violations: list[str] = []
    for pattern in pledge_patterns:
        matches = re.findall(pattern, plain_text)
        if matches:
            violations.append(f"\"{matches[0]}\" ({len(matches)}회) - 공약성 표현")

    bribery_items = ViolationDetector.check_bribery_risk(plain_text)
    for item in bribery_items:
        violations.append(f"🔴 {item.get('reason') or '기부행위 금지 위반 위험'}")

    fact_items = ViolationDetector.check_fact_claims(plain_text)
    for item in fact_items:
        severity = str(item.get("severity") or "").upper()
        emoji = "🔴" if severity == "CRITICAL" else "⚠️"
        violations.append(f"{emoji} {item.get('reason') or '허위사실/비방 위험'}")

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "status": status,
        "stage": election_stage.get("name"),
        "hasCritical": bool(bribery_items) or any(
            str(item.get("severity") or "").upper() == "CRITICAL" for item in fact_items
        ),
    }


def validate_title_quality(
    title: str,
    user_keywords: Optional[Sequence[str]] = None,
    content: str = "",
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    options = options or {}
    strict_facts = options.get("strictFacts") is True
    user_keywords = list(user_keywords or [])

    if not title:
        return {"passed": True, "issues": [], "details": {}}

    issues: list[Dict[str, Any]] = []
    details: Dict[str, Any] = {
        "length": len(title),
        "maxLength": 25,
        "keywordPosition": None,
        "abstractExpressions": [],
        "hasNumbers": False,
    }

    if len(title) < 10:
        issues.append(
            {
                "type": "title_too_short",
                "severity": "critical",
                "description": f"제목이 너무 짧음 ({len(title)}자)",
                "instruction": "10자 이상으로 구체적인 내용을 포함하여 작성하세요. 단순 키워드 나열 금지.",
            }
        )

    if len(title) > 25:
        issues.append(
            {
                "type": "title_length",
                "severity": "critical",
                "description": f"제목 {len(title)}자 → 25자 초과 (네이버에서 잘림)",
                "instruction": "25자 이내로 줄이세요. 불필요한 조사, 부제목(:, -) 제거.",
            }
        )

    if user_keywords:
        primary_kw = user_keywords[0]
        kw_index = title.find(primary_kw)
        details["keywordPosition"] = kw_index

        if kw_index == -1:
            issues.append(
                {
                    "type": "keyword_missing",
                    "severity": "high",
                    "description": f"핵심 키워드 \"{primary_kw}\" 제목에 없음",
                    "instruction": f"\"{primary_kw}\"를 제목 앞부분에 포함하세요.",
                }
            )
        elif kw_index > 10:
            issues.append(
                {
                    "type": "keyword_position",
                    "severity": "medium",
                    "description": f"키워드 \"{primary_kw}\" 위치 {kw_index}자 → 너무 뒤쪽",
                    "instruction": "핵심 키워드는 제목 앞쪽 8자 이내에 배치하세요 (앞쪽 1/3 법칙).",
                }
            )

        clean_title = re.sub(r"\s+", "", title)
        clean_kw = re.sub(r"\s+", "", primary_kw)
        if clean_kw and clean_kw in clean_title and len(clean_title) <= len(clean_kw) + 4:
            issues.append(
                {
                    "type": "title_too_generic",
                    "severity": "critical",
                    "description": "제목이 키워드와 너무 유사함 (단순 명사형)",
                    "instruction": "서술어인 \"현안 진단\", \"핵심 분석\", \"이슈 점검\" 등을 반드시 포함하여 구체화하세요.",
                }
            )

    if content:
        title_numeric_tokens = extract_numeric_tokens(title)
        content_numeric_tokens = extract_numeric_tokens(content)
        if title_numeric_tokens:
            if not content_numeric_tokens:
                issues.append(
                    {
                        "type": "title_number_mismatch",
                        "severity": "high",
                        "description": "제목에 수치가 있으나 본문에 근거 수치 없음",
                        "instruction": "본문에 실제로 있는 수치/단위를 제목에 사용하세요.",
                    }
                )
            else:
                missing_tokens = [token for token in title_numeric_tokens if token not in content_numeric_tokens]
                if missing_tokens:
                    issues.append(
                        {
                            "type": "title_number_mismatch",
                            "severity": "high",
                            "description": f"제목 수치/단위가 본문과 불일치: {', '.join(missing_tokens)}",
                            "instruction": "본문에 실제로 등장하는 수치/단위를 제목에 그대로 사용하세요.",
                        }
                    )

    abstract_patterns = [
        ("비전", r"비전"),
        ("혁신", r"혁신"),
        ("발전", r"발전"),
        ("노력", r"노력"),
        ("최선", r"최선"),
        ("약속", r"약속"),
        ("다짐", r"다짐"),
        ("함께", r"함께"),
        ("확충", r"확충"),
        ("개선", r"개선"),
        ("추진", r"추진"),
        ("시급", r"시급"),
        ("강화", r"강화"),
        ("증진", r"증진"),
        ("도모", r"도모"),
        ("향상", r"향상"),
        ("활성화", r"활성화"),
        ("선도", r"선도"),
        ("선진", r"선진"),
        ("미래", r"미래"),
    ]
    found_abstract = [word for word, pattern in abstract_patterns if re.search(pattern, title)]
    if found_abstract:
        details["abstractExpressions"] = found_abstract
        issues.append(
            {
                "type": "abstract_expression",
                "severity": "medium",
                "description": f"추상적 표현 사용: {', '.join(found_abstract)}",
                "instruction": "구체적 수치나 사실로 대체하세요. 예: \"발전\" → \"40% 증가\", \"비전\" → \"3대 핵심 정책\"",
            }
        )

    details["hasNumbers"] = bool(re.search(r"\d", title))
    if (not details["hasNumbers"]) and issues and (not strict_facts):
        issues.append(
            {
                "type": "no_numbers",
                "severity": "low",
                "description": "숫자/구체적 데이터 없음",
                "instruction": "가능하면 숫자를 포함하세요. 예: \"3대 정책\", \"120억 확보\", \"40% 개선\"",
            }
        )

    has_blocking_issue = any(issue.get("severity") in {"critical", "high"} for issue in issues)
    return {"passed": not has_blocking_issue, "issues": issues, "details": details}


def run_heuristic_validation_sync(
    content: str,
    status: str,
    title: str = "",
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    options = options or {}
    fact_allowlist = options.get("factAllowlist")

    issues: list[str] = []

    repetition_result = detect_sentence_repetition(content)
    if not repetition_result.get("passed", True):
        issues.append(f"⚠️ 문장 반복 감지: {', '.join(repetition_result.get('repeatedSentences', []))}")

    phrase_result = detect_phrase_repetition(content)
    if not phrase_result.get("passed", True):
        issues.append(f"⚠️ 구문 반복 감지: {', '.join(phrase_result.get('repeatedPhrases', []))}")

    near_dup_result = detect_near_duplicate_sentences(content)
    if not near_dup_result.get("passed", True):
        summary = ", ".join(
            f"\"{pair['a']}\" ≈ \"{pair['b']}\" ({pair['similarity']}%)"
            for pair in (near_dup_result.get("similarPairs") or [])[:3]
        )
        issues.append(f"⚠️ 유사 문장 감지: {summary}")

    election_result = detect_election_law_violation(content, status, title)
    if not election_result.get("passed", True):
        issues.append(f"⚠️ 선거법 위반 표현: {', '.join(election_result.get('violations', []))}")

    fact_check_result = None
    if fact_allowlist:
        content_check = find_unsupported_numeric_tokens(content, fact_allowlist)
        title_check = find_unsupported_numeric_tokens(title, fact_allowlist) if title else {"passed": True, "unsupported": []}
        fact_check_result = {"content": content_check, "title": title_check}

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "details": {
            "repetition": repetition_result,
            "electionLaw": election_result,
            "factCheck": fact_check_result,
        },
    }


async def run_heuristic_validation(
    content: str,
    status: str,
    title: str = "",
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    options = options or {}
    use_llm = options.get("useLLM", True)
    user_keywords = list(options.get("userKeywords") or [])
    fact_allowlist = options.get("factAllowlist")
    model_name = options.get("modelName", "gemini-2.5-flash")

    issues: list[str] = []

    repetition_result = detect_sentence_repetition(content)
    if not repetition_result.get("passed", True):
        issues.append(f"⚠️ 문장 반복 감지: {', '.join(repetition_result.get('repeatedSentences', []))}")

    phrase_result = detect_phrase_repetition(content)
    if not phrase_result.get("passed", True):
        issues.append(f"⚠️ 구문 반복 감지: {', '.join(phrase_result.get('repeatedPhrases', []))}")

    near_dup_result = detect_near_duplicate_sentences(content)
    if not near_dup_result.get("passed", True):
        summary = ", ".join(
            f"\"{pair['a']}\" ≈ \"{pair['b']}\" ({pair['similarity']}%)"
            for pair in (near_dup_result.get("similarPairs") or [])[:3]
        )
        issues.append(f"⚠️ 유사 문장 감지: {summary}")

    if use_llm:
        election_result = await detect_election_law_violation_hybrid(
            content,
            status,
            title,
            model_name=model_name,
        )
        if not election_result.get("passed", True):
            violation_summary = ", ".join(
                f"\"{item.get('sentence', '')}\" ({item.get('reason', '')})"
                for item in (election_result.get("violations") or [])
            )
            issues.append(f"⚠️ 선거법 위반: {violation_summary}")
    else:
        election_result = detect_election_law_violation(content, status, title)
        if not election_result.get("passed", True):
            issues.append(f"⚠️ 선거법 위반 표현: {', '.join(election_result.get('violations', []))}")

    title_result = validate_title_quality(
        title,
        user_keywords=user_keywords,
        content=content,
        options={"strictFacts": bool(fact_allowlist)},
    )
    if not title_result.get("passed", True):
        blocking_title_issues = [
            issue.get("description")
            for issue in (title_result.get("issues") or [])
            if issue.get("severity") in {"critical", "high"}
        ]
        if blocking_title_issues:
            issues.append(f"⚠️ 제목 품질 문제: {', '.join(blocking_title_issues)}")

    fact_check_result = None
    if fact_allowlist:
        content_check = find_unsupported_numeric_tokens(content, fact_allowlist)
        title_check = find_unsupported_numeric_tokens(title, fact_allowlist) if title else {"passed": True, "unsupported": []}
        fact_check_result = {"content": content_check, "title": title_check}

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "details": {
            "repetition": repetition_result,
            "electionLaw": election_result,
            "titleQuality": title_result,
            "factCheck": fact_check_result,
        },
    }


# ============================================================================
# 초당적 협력 / 핵심 문구 / 비판 대상 검증
# ============================================================================


BIPARTISAN_FORBIDDEN_PHRASES = [
    "정신을 이어받아",
    "뜻을 받들어",
    "배워야 합니다",
    "배울 점",
    "깊은 울림",
    "용기에 박수",
    "귀감이 됩니다",
    "본받아야",
    "존경합니다",
    "멘토",
    "스승",
    "깊은 감명",
    "우리보다 낫다",
    "우리보다 훨씬 낫다",
    "우리는 저렇게 못한다",
    "정책이 100% 맞다",
    "전적으로 동의한다",
    "완전히 옳다",
    "정치인 중 최고",
    "유일하게 믿을 수 있다",
    "가장 훌륭하다",
    "개인적으로 좋아한다",
    "헌신적인 노력",
    "헌신적인 모습",
]


def detect_bipartisan_forbidden_phrases(content: str) -> Dict[str, Any]:
    violations: list[str] = []
    corrected = content or ""

    for phrase in BIPARTISAN_FORBIDDEN_PHRASES:
        if phrase not in corrected:
            continue
        violations.append(phrase)
        if phrase == "귀감이 됩니다":
            corrected = corrected.replace(phrase, "주목할 만합니다")
        elif phrase == "배워야 합니다":
            corrected = corrected.replace(phrase, "참고할 수 있습니다")
        elif phrase == "깊은 감명":
            corrected = corrected.replace(phrase, "관심")
        elif "헌신적인" in phrase:
            corrected = corrected.replace(phrase, "꾸준한 노력")
        else:
            corrected = corrected.replace(phrase, "")

    corrected = re.sub(r"\s+", " ", corrected)
    corrected = re.sub(r"\s+\.", ".", corrected).strip()
    return {"hasForbidden": len(violations) > 0, "violations": violations, "correctedContent": corrected}


def calculate_praise_proportion(content: str, rival_names: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    rival_names = list(rival_names or [])
    if not rival_names:
        return {"percentage": 0, "exceedsLimit": False, "rivalMentions": 0}

    sentences = extract_sentences(content or "")
    rival_mention_sentences = 0
    for sentence in sentences:
        if any(name in sentence for name in rival_names):
            rival_mention_sentences += 1

    percentage = round((rival_mention_sentences / len(sentences)) * 100) if sentences else 0
    return {
        "percentage": percentage,
        "exceedsLimit": percentage > 15,
        "rivalMentions": rival_mention_sentences,
        "totalSentences": len(sentences),
    }


def validate_bipartisan_praise(content: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    options = options or {}
    rival_names = list(options.get("rivalNames") or [])
    category = str(options.get("category") or "")

    if ("bipartisan" not in category) and ("초당적" not in category):
        return {"passed": True, "issues": [], "correctedContent": content}

    issues: list[str] = []
    forbidden_result = detect_bipartisan_forbidden_phrases(content or "")
    if forbidden_result["hasForbidden"]:
        issues.append(
            f"⚠️ 초당적 협력 금지 표현 감지 및 자동 수정: {', '.join(forbidden_result['violations'])}"
        )

    proportion_result = calculate_praise_proportion(forbidden_result["correctedContent"], rival_names)
    if proportion_result.get("exceedsLimit"):
        issues.append(
            f"⚠️ 경쟁자 칭찬 비중 초과: {proportion_result['percentage']}% "
            f"({proportion_result['rivalMentions']}/{proportion_result['totalSentences']} 문장) - 권장 15% 이하"
        )

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "correctedContent": forbidden_result["correctedContent"],
        "details": {"forbiddenPhrases": forbidden_result, "praiseProportion": proportion_result},
    }


def validate_key_phrase_inclusion(content: str, required_phrases: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    required_phrases = list(required_phrases or [])
    if not content or not required_phrases:
        return {"passed": True, "missing": [], "included": [], "details": {}}

    plain_content = _strip_html(content)
    included: list[Dict[str, str]] = []
    missing: list[str] = []
    details: Dict[str, Any] = {}

    for phrase in required_phrases:
        if not phrase or len(phrase) < 5:
            continue
        exact_match = phrase in plain_content
        core_words = [
            word
            for word in re.split(r"\s+", re.sub(r"[.?!,~]", "", phrase))
            if len(word) >= 4 and not re.match(r"^(있습니다|없습니다|합니다|입니다|것입니다|아닙니다)$", word)
        ]
        core_word_matches = [word for word in core_words if word in plain_content]
        paraphrase_match = bool(core_words) and len(core_word_matches) >= (len(core_words) + 1) // 2

        details[phrase] = {
            "exactMatch": exact_match,
            "paraphraseMatch": paraphrase_match,
            "coreWords": core_words,
            "coreWordMatches": core_word_matches,
            "included": exact_match or paraphrase_match,
        }

        if exact_match or paraphrase_match:
            included.append({"phrase": phrase, "matchType": "exact" if exact_match else "paraphrase"})
        else:
            missing.append(phrase)

    has_exact_match = any(item.get("matchType") == "exact" for item in included)
    all_included = len(missing) == 0
    passed = all_included and (len(required_phrases) <= 1 or has_exact_match)

    return {
        "passed": passed,
        "missing": missing,
        "included": included,
        "hasExactMatch": has_exact_match,
        "details": details,
        "message": (
            None
            if passed
            else (
                f"핵심 문구 누락: {', '.join(f'\"{item[:30]}...\"' for item in missing)}"
                if missing
                else "원문 그대로 인용된 문구가 없습니다. 최소 1개는 원문 인용이 필요합니다."
            )
        ),
    }


def validate_criticism_target(content: str, responsibility_target: str) -> Dict[str, Any]:
    if not content or not responsibility_target:
        return {"passed": True, "targetMentioned": False, "count": 0}

    plain_content = re.sub(r"<[^>]*>", " ", content)
    target_parts = [part for part in re.split(r"\s+", responsibility_target) if part]
    target_name = target_parts[0] if target_parts else responsibility_target
    escaped_name = re.escape(target_name)

    matches = re.findall(escaped_name, plain_content)
    count = len(matches)
    count_passed = count >= 2

    intent_reversal_patterns = [
        re.compile(rf"{escaped_name}[^.]*(?:협력|존중|함께|노력|인정|공로|성과)"),
        re.compile(rf"(?:협력|존중|함께)하여[^.]*{escaped_name}"),
        re.compile(rf"{escaped_name}[^.]*(?:의\s*노력|과\s*협력|과\s*함께|을\s*존중)"),
    ]

    intent_reversal_count = 0
    intent_reversal_matches: list[str] = []
    for pattern in intent_reversal_patterns:
        detected = pattern.findall(plain_content)
        intent_reversal_count += len(detected)
        intent_reversal_matches.extend(detected)

    criticism_patterns = [
        re.compile(rf"{escaped_name}[^.]*(?:역부족|한계|문제|책임|비판|실패|부족)"),
        re.compile(rf"(?:역부족|한계|문제|책임|비판|실패|부족)[^.]*{escaped_name}"),
    ]
    criticism_context_count = sum(len(pattern.findall(plain_content)) for pattern in criticism_patterns)
    has_intent_reversal = intent_reversal_count > 0 and intent_reversal_count > criticism_context_count
    passed = count_passed and (not has_intent_reversal)

    message = None
    if not count_passed:
        message = f"비판 대상 \"{target_name}\" 언급 부족 (현재 {count}회, 최소 2회 필요)"
    elif has_intent_reversal:
        message = (
            f"🔴 의도 역전 감지: 비판 대상 \"{target_name}\"이(가) 긍정적 맥락(협력/존중/함께)으로 언급됨. "
            f"원본의 비판적 논조를 유지하세요. [감지된 표현: {', '.join(intent_reversal_matches[:2])}]"
        )

    return {
        "passed": passed,
        "targetMentioned": count > 0,
        "count": count,
        "targetName": target_name,
        "hasIntentReversal": has_intent_reversal,
        "intentReversalCount": intent_reversal_count,
        "criticismContextCount": criticism_context_count,
        "message": message,
    }


# ============================================================================
# 키워드 삽입 검증
# ============================================================================


def count_keyword_occurrences(content: str, keyword: str) -> int:
    clean_content = re.sub(r"<[^>]*>", "", content or "")
    escaped = re.escape(keyword or "")
    if not escaped:
        return 0
    return len(re.findall(escaped, clean_content))


def build_keyword_variants(keyword: str) -> List[str]:
    trimmed = str(keyword or "").strip()
    if not trimmed:
        return []
    parts = [part for part in re.split(r"\s+", trimmed) if part]
    variants: list[str] = []
    if len(parts) >= 2:
        first = parts[0]
        rest = " ".join(parts[1:])
        variants.append(f"{first}의 {rest}")
        variants.append(f"{rest} {first}")
    deduped: list[str] = []
    seen: set[str] = set()
    for item in variants:
        if item and item != trimmed and item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def count_keyword_coverage(content: str, keyword: str) -> int:
    if not keyword:
        return 0
    keywords = [keyword, *build_keyword_variants(keyword)]
    return sum(count_keyword_occurrences(content, item) for item in keywords)


def _keyword_user_threshold(user_keywords: Optional[Sequence[str]] = None) -> tuple[int, int]:
    normalized = [item for item in (user_keywords or []) if item]
    kw_count = len(normalized) if normalized else 1
    user_min_count = 3 if kw_count >= 2 else 5
    user_max_count = user_min_count + 1
    return user_min_count, user_max_count


def _parse_keyword_sections(content: str) -> List[Dict[str, Any]]:
    sections: list[Dict[str, Any]] = []
    h2_matches = list(re.finditer(r"<h2[^>]*>[\s\S]*?<\/h2>", content or "", re.IGNORECASE))

    if not h2_matches:
        return [
            {
                "type": "single",
                "startIndex": 0,
                "endIndex": len(content or ""),
                "content": content or "",
            }
        ]

    first_h2_start = h2_matches[0].start()
    if first_h2_start > 0:
        sections.append(
            {
                "type": "intro",
                "startIndex": 0,
                "endIndex": first_h2_start,
                "content": (content or "")[:first_h2_start],
            }
        )

    for idx, match in enumerate(h2_matches):
        start_index = match.start()
        end_index = h2_matches[idx + 1].start() if idx < len(h2_matches) - 1 else len(content or "")
        section_type = "conclusion" if idx == len(h2_matches) - 1 else f"body{idx + 1}"
        sections.append(
            {
                "type": section_type,
                "startIndex": start_index,
                "endIndex": end_index,
                "content": (content or "")[start_index:end_index],
            }
        )

    return sections


def _section_priority(section_type: str) -> int:
    if section_type.startswith("body"):
        return 0
    if section_type == "conclusion":
        return 1
    if section_type == "intro":
        return 2
    return 3


def _select_keyword_section_indexes(
    sections: Sequence[Dict[str, Any]],
    keyword: str,
    needed: int,
) -> List[int]:
    if not sections or needed <= 0:
        return []

    indexed = list(enumerate(sections))
    ranked = sorted(
        indexed,
        key=lambda item: (
            count_keyword_coverage(str(item[1].get("content") or ""), keyword),
            _section_priority(str(item[1].get("type") or "")),
            item[0],
        ),
    )
    if not ranked:
        return []

    chosen: list[int] = []
    while len(chosen) < needed:
        progressed = False
        for idx, _section in ranked:
            chosen.append(idx)
            progressed = True
            if len(chosen) >= needed:
                break
        if not progressed:
            break
    return chosen[:needed]


def _build_keyword_enforcement_sentence(keyword: str, section_type: str, variant_index: int = 0) -> str:
    safe_kw = html.escape(str(keyword or "").strip())
    section_key = "single"
    if section_type == "intro":
        section_key = "intro"
    elif section_type == "conclusion":
        section_key = "conclusion"
    elif section_type.startswith("body"):
        section_key = "body"

    templates = {
        "intro": [
            "{kw} 이슈는 시민 생활과 맞닿은 핵심 현안입니다.",
            "지금 {kw} 의제는 현장에서 체감도가 높은 문제입니다.",
        ],
        "body": [
            "{kw} 문제는 현장 사례와 데이터로 함께 점검해야 합니다.",
            "{kw} 관련 쟁점은 생활 불편과 정책 효과를 함께 봐야 합니다.",
        ],
        "conclusion": [
            "끝으로 {kw} 과제는 지속적인 점검과 실행이 필요합니다.",
            "{kw} 의제는 마지막까지 책임 있게 확인해야 할 사안입니다.",
        ],
        "single": [
            "{kw} 이슈는 지금 가장 우선적으로 점검해야 할 과제입니다.",
            "{kw} 관련 논점은 사실과 현장 중심으로 계속 살펴봐야 합니다.",
        ],
    }
    options = templates.get(section_key, templates["single"])
    template = options[variant_index % len(options)]
    return template.format(kw=safe_kw)


def enforce_keyword_requirements(
    content: str,
    user_keywords: Optional[Sequence[str]] = None,
    auto_keywords: Optional[Sequence[str]] = None,
    target_word_count: Optional[int] = None,
    max_iterations: int = 2,
) -> Dict[str, Any]:
    working_content = str(content or "")
    user_keywords = [item for item in (user_keywords or []) if item]
    auto_keywords = [item for item in (auto_keywords or []) if item]

    initial_result = validate_keyword_insertion(
        working_content,
        user_keywords,
        auto_keywords,
        target_word_count,
    )
    if not working_content or (not user_keywords and not auto_keywords):
        return {
            "content": working_content,
            "edited": False,
            "insertions": [],
            "keywordResult": initial_result,
        }
    if initial_result.get("valid"):
        return {
            "content": working_content,
            "edited": False,
            "insertions": [],
            "keywordResult": initial_result,
        }

    insertions: list[Dict[str, Any]] = []
    per_keyword_insertions: Dict[str, int] = {}
    current_result = initial_result

    for _ in range(max_iterations):
        details = (current_result.get("details") or {}).get("keywords") or {}
        sections = _parse_keyword_sections(working_content)
        if not details or not sections:
            break

        insertion_plan: Dict[int, List[Dict[str, Any]]] = {}
        needs_fix = False

        for keyword in [*user_keywords, *auto_keywords]:
            keyword_info = details.get(keyword) or {}
            expected = int(keyword_info.get("expected") or (1 if keyword in auto_keywords else _keyword_user_threshold(user_keywords)[0]))
            coverage = int(keyword_info.get("coverage") or 0)
            deficit = max(0, expected - coverage)
            if deficit <= 0:
                continue

            needs_fix = True
            target_indexes = _select_keyword_section_indexes(sections, keyword, deficit)
            for section_idx in target_indexes:
                if section_idx < 0 or section_idx >= len(sections):
                    continue
                section = sections[section_idx]
                variant_index = per_keyword_insertions.get(keyword, 0)
                sentence = _build_keyword_enforcement_sentence(
                    keyword,
                    str(section.get("type") or ""),
                    variant_index,
                )
                per_keyword_insertions[keyword] = variant_index + 1
                end_index = int(section.get("endIndex") or 0)
                insertion_plan.setdefault(end_index, []).append(
                    {
                        "keyword": keyword,
                        "section": section_idx,
                        "sectionType": section.get("type"),
                        "sentence": sentence,
                    }
                )

        if not needs_fix or not insertion_plan:
            break

        for position in sorted(insertion_plan.keys(), reverse=True):
            payload = insertion_plan[position]
            paragraphs = "".join(f"\n<p>{item['sentence']}</p>" for item in payload)
            working_content = working_content[:position] + paragraphs + working_content[position:]
            insertions.extend(payload)

        current_result = validate_keyword_insertion(
            working_content,
            user_keywords,
            auto_keywords,
            target_word_count,
        )
        if current_result.get("valid"):
            break

    return {
        "content": working_content,
        "edited": working_content != str(content or ""),
        "insertions": insertions,
        "keywordResult": current_result,
    }


def build_fallback_draft(params: Optional[Dict[str, Any]] = None) -> str:
    params = params or {}
    topic = str(params.get("topic") or "현안").strip()
    full_name = str(params.get("fullName") or "").strip()
    user_keywords = list(params.get("userKeywords") or [])

    greeting = f"존경하는 시민 여러분, {full_name}입니다." if full_name else "존경하는 시민 여러분."
    keyword_sentences = [f"{keyword}와 관련한 현황을 점검합니다." for keyword in user_keywords[:5] if keyword]
    keyword_paragraph = f"<p>{' '.join(keyword_sentences)}</p>" if keyword_sentences else ""

    blocks = [
        f"<p>{greeting} {topic}에 대해 핵심 현황을 정리합니다.</p>",
        "<h2>현안 개요</h2>",
        f"<p>{topic}의 구조적 배경과 최근 흐름을 객관적으로 살펴봅니다.</p>",
        keyword_paragraph,
        "<h2>핵심 쟁점</h2>",
        "<p>원인과 영향을 구분해 사실관계를 정리하고, 논의가 필요한 지점을 확인합니다.</p>",
        "<h2>확인 과제</h2>",
        "<p>추가 확인이 필요한 데이터와 점검 과제를 중심으로 정리합니다.</p>",
        f"<p>{full_name} 드림</p>" if full_name else "",
    ]
    return "\n".join(block for block in blocks if block)


def validate_keyword_insertion(
    content: str,
    user_keywords: Optional[Sequence[str]] = None,
    auto_keywords: Optional[Sequence[str]] = None,
    target_word_count: Optional[int] = None,
) -> Dict[str, Any]:
    _ = target_word_count
    user_keywords = [item for item in (user_keywords or []) if item]
    auto_keywords = [item for item in (auto_keywords or []) if item]
    plain_text = re.sub(r"\s", "", re.sub(r"<[^>]*>", "", content or ""))
    actual_word_count = len(plain_text)

    user_min_count, user_max_count = _keyword_user_threshold(user_keywords)
    auto_min_count = 1

    results: Dict[str, Dict[str, Any]] = {}
    all_valid = True

    for keyword in user_keywords:
        exact_count = count_keyword_occurrences(content, keyword)
        coverage_count = count_keyword_coverage(content, keyword)
        is_under_min = coverage_count < user_min_count
        is_over_max = exact_count > user_max_count or coverage_count > user_max_count
        is_valid = (not is_under_min) and (not is_over_max)
        results[keyword] = {
            "count": coverage_count,
            "exactCount": exact_count,
            "coverage": coverage_count,
            "expected": user_min_count,
            "max": user_max_count,
            "valid": is_valid,
            "type": "user",
        }
        if not is_valid:
            all_valid = False

    for keyword in auto_keywords:
        exact_count = count_keyword_occurrences(content, keyword)
        coverage_count = count_keyword_coverage(content, keyword)
        is_valid = coverage_count >= auto_min_count
        results[keyword] = {
            "count": coverage_count,
            "exactCount": exact_count,
            "coverage": coverage_count,
            "expected": auto_min_count,
            "valid": is_valid,
            "type": "auto",
        }

    all_keywords = [*user_keywords, *auto_keywords]
    total_keyword_chars = 0
    for keyword in all_keywords:
        occurrences = count_keyword_coverage(content, keyword)
        total_keyword_chars += len(re.sub(r"\s", "", keyword)) * occurrences
    density = (total_keyword_chars / actual_word_count * 100) if actual_word_count else 0

    return {
        "valid": all_valid,
        "details": {
            "keywords": results,
            "density": {
                "value": f"{density:.2f}",
                "valid": True,
                "optimal": 1.5 <= density <= 2.5,
            },
            "wordCount": actual_word_count,
        },
    }


async def _generate_draft_text(
    prompt: str,
    model_name: str,
    generate_fn: Optional[Callable[..., Awaitable[str]]] = None,
) -> str:
    if generate_fn:
        try:
            candidate = generate_fn(prompt, model_name)
        except TypeError:
            candidate = generate_fn(prompt)
        result = await candidate
        return str(result or "")

    from agents.common.gemini_client import generate_content_async

    return await generate_content_async(
        prompt,
        model_name=model_name,
        temperature=1.0,
    )


async def validate_and_retry(
    *,
    prompt: str,
    model_name: str,
    full_name: str | None = None,
    full_region: str | None = None,
    target_word_count: Optional[int] = None,
    user_keywords: Optional[Sequence[str]] = None,
    auto_keywords: Optional[Sequence[str]] = None,
    status: str | None = None,
    fact_allowlist: Optional[Sequence[str]] = None,
    rag_context: Optional[str] = None,
    author_name: Optional[str] = None,
    topic: Optional[str] = None,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    max_attempts: int = 3,
    max_critic_attempts: int = 2,
    generate_fn: Optional[Callable[..., Awaitable[str]]] = None,
) -> str:
    """AI 응답 생성 + 휴리스틱 검증 + Critic/Corrector 루프."""

    _ = (full_region, target_word_count, auto_keywords)
    user_keywords = list(user_keywords or [])
    status_value = status or ""
    author = author_name or full_name
    critic_model = "gemini-2.5-flash"
    corrector_model = "gemini-2.5-flash"

    def notify_progress(stage_id: str, additional_info: Optional[Dict[str, Any]] = None) -> None:
        if not callable(on_progress):
            return
        try:
            on_progress(create_progress_state(stage_id, additional_info or {}))
        except Exception as exc:
            logger.warning("Progress 콜백 오류: %s", exc)

    best_version: Optional[str] = None
    best_score = 0
    draft: Optional[str] = None
    heuristic_passed = False

    notify_progress("DRAFTING")

    for attempt in range(1, max_attempts + 1):
        logger.info("원고 생성 시도 (%s/%s)", attempt, max_attempts)

        try:
            candidate = await _generate_draft_text(prompt, model_name, generate_fn=generate_fn)
        except Exception as exc:
            logger.warning("원고 생성 실패 (%s/%s): %s", attempt, max_attempts, exc)
            continue

        if not candidate or len(candidate.strip()) < 100:
            logger.warning("응답이 너무 짧아 재시도합니다 (%s/%s)", attempt, max_attempts)
            continue

        notify_progress("BASIC_CHECK", {"attempt": attempt})
        heuristic_result = await run_heuristic_validation(
            candidate,
            status_value,
            "",
            {
                "useLLM": False,
                "factAllowlist": fact_allowlist,
                "userKeywords": user_keywords,
                "modelName": model_name,
            },
        )

        issues = list(heuristic_result.get("issues") or [])
        draft = candidate

        if heuristic_result.get("passed", False):
            heuristic_passed = True
            best_version = candidate
            best_score = max(best_score, 70)
            logger.info("휴리스틱 검증 통과 (%s/%s)", attempt, max_attempts)
            break

        estimated_score = max(10, 70 - (len(issues) * 15))
        if estimated_score > best_score:
            best_score = estimated_score
            best_version = candidate

        logger.warning("휴리스틱 검증 실패 (%s/%s): %s", attempt, max_attempts, issues)
        if attempt < max_attempts:
            notify_progress("DRAFTING", {"attempt": attempt + 1})

    if not heuristic_passed:
        logger.error("%s회 시도 후에도 휴리스틱 검증 실패", max_attempts)
        fallback = best_version or build_fallback_draft(
            {
                "topic": topic,
                "fullName": full_name,
                "userKeywords": user_keywords,
            }
        )
        notify_progress("COMPLETED", {"warning": "품질 검증 일부 실패", "score": best_score})
        return fallback

    guidelines = summarize_guidelines(status_value, topic)
    current_draft = draft or ""
    critic_attempt = 0

    while critic_attempt < max_critic_attempts:
        critic_attempt += 1
        retry_msg = create_retry_message(critic_attempt, max_critic_attempts, best_score)
        notify_progress(
            "EDITOR_REVIEW",
            {
                "attempt": critic_attempt,
                "message": retry_msg.get("message"),
                "detail": retry_msg.get("detail"),
            },
        )

        critic_report = await run_critic_review(
            draft=current_draft,
            rag_context=rag_context,
            guidelines=guidelines,
            status=status_value,
            topic=topic,
            author_name=author,
            model_name=critic_model,
        )

        score = int(critic_report.get("score") or 0)
        if score > best_score:
            best_score = score
            best_version = current_draft

        if critic_report.get("passed") or (not critic_report.get("needsRetry")):
            notify_progress("FINALIZING")
            final_check = await run_heuristic_validation(
                current_draft,
                status_value,
                "",
                {
                    "useLLM": True,
                    "factAllowlist": fact_allowlist,
                },
            )

            if not final_check.get("passed", True):
                details = final_check.get("details") or {}
                election_law = details.get("electionLaw") or {}
                violations = election_law.get("violations") or []
                if violations:
                    correction_result = await apply_corrections(
                        draft=current_draft,
                        violations=[
                            {
                                "type": "HARD",
                                "field": "content",
                                "issue": item.get("reason"),
                                "suggestion": f"\"{item.get('sentence', '')}\" 표현을 수정하세요",
                                "severity": "HARD",
                                "location": "본문",
                                "problematic": item.get("sentence", ""),
                            }
                            for item in violations
                        ],
                        rag_context=rag_context,
                        author_name=author,
                        status=status_value,
                        model_name=corrector_model,
                    )
                    if correction_result.get("success") and (not correction_result.get("unchanged")):
                        current_draft = str(correction_result.get("corrected") or current_draft)

            notify_progress("COMPLETED", {"score": score})
            return current_draft

        violations = list(critic_report.get("violations") or [])
        if has_hard_violations(critic_report):
            notify_progress("CORRECTING", {"violations": summarize_violations(violations)})
            correction_result = await apply_corrections(
                draft=current_draft,
                violations=violations,
                rag_context=rag_context,
                author_name=author,
                status=status_value,
                model_name=corrector_model,
            )
            if correction_result.get("success") and (not correction_result.get("unchanged")):
                current_draft = str(correction_result.get("corrected") or current_draft)
            else:
                logger.warning("Corrector 수정 실패: %s", correction_result.get("error") or "변경 없음")
        else:
            notify_progress("COMPLETED", {"score": score, "warnings": len(violations)})
            return current_draft

    notify_progress(
        "COMPLETED",
        {
            "score": best_score,
            "warning": "일부 품질 기준 미달 - 수동 검토 권장",
        },
    )
    final_draft = best_version if best_score >= 70 else current_draft
    return final_draft or current_draft or (draft or "")


async def evaluate_quality_with_llm(content: str, model_name: str) -> Dict[str, Any]:
    """Legacy 호환 함수 (Critic 대체 이전 API)."""

    _ = (content, model_name)
    return {"passed": True, "issues": [], "suggestions": []}


# JS 호환 별칭
extractSentences = extract_sentences
isAllowedEnding = is_allowed_ending
isExplicitPledge = is_explicit_pledge
containsPledgeCandidate = contains_pledge_candidate
checkPledgesWithLLM = check_pledges_with_llm
detectElectionLawViolationHybrid = detect_election_law_violation_hybrid
detectSentenceRepetition = detect_sentence_repetition
detectPhraseRepetition = detect_phrase_repetition
detectNearDuplicateSentences = detect_near_duplicate_sentences
detectElectionLawViolation = detect_election_law_violation
validateTitleQuality = validate_title_quality
runHeuristicValidationSync = run_heuristic_validation_sync
runHeuristicValidation = run_heuristic_validation
detectBipartisanForbiddenPhrases = detect_bipartisan_forbidden_phrases
calculatePraiseProportion = calculate_praise_proportion
validateBipartisanPraise = validate_bipartisan_praise
validateKeyPhraseInclusion = validate_key_phrase_inclusion
validateCriticismTarget = validate_criticism_target
countKeywordOccurrences = count_keyword_occurrences
buildKeywordVariants = build_keyword_variants
countKeywordCoverage = count_keyword_coverage
buildFallbackDraft = build_fallback_draft
validateKeywordInsertion = validate_keyword_insertion
enforceKeywordRequirements = enforce_keyword_requirements
validateAndRetry = validate_and_retry
evaluateQualityWithLLM = evaluate_quality_with_llm


__all__ = [
    "ALLOWED_ENDINGS",
    "EXPLICIT_PLEDGE_PATTERNS",
    "BIPARTISAN_FORBIDDEN_PHRASES",
    "GENERATION_STAGES",
    "extract_sentences",
    "is_allowed_ending",
    "is_explicit_pledge",
    "contains_pledge_candidate",
    "check_pledges_with_llm",
    "detect_election_law_violation_hybrid",
    "detect_sentence_repetition",
    "detect_phrase_repetition",
    "detect_near_duplicate_sentences",
    "detect_election_law_violation",
    "validate_title_quality",
    "run_heuristic_validation_sync",
    "run_heuristic_validation",
    "detect_bipartisan_forbidden_phrases",
    "calculate_praise_proportion",
    "validate_bipartisan_praise",
    "validate_key_phrase_inclusion",
    "validate_criticism_target",
    "count_keyword_occurrences",
    "build_keyword_variants",
    "count_keyword_coverage",
    "build_fallback_draft",
    "validate_keyword_insertion",
    "enforce_keyword_requirements",
    "validate_and_retry",
    "evaluate_quality_with_llm",
]
