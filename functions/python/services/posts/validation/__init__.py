"""원고 품질/선거법/키워드 휴리스틱 검증 모듈."""

from __future__ import annotations

from ..generation_stages import GENERATION_STAGES
from .date_validation import extract_date_weekday_pairs, repair_date_weekday_pairs, validate_date_weekday_pairs
from .election_law import check_pledges_with_llm, detect_election_law_violation, detect_election_law_violation_hybrid
from .heuristics import (
    BIPARTISAN_FORBIDDEN_PHRASES,
    calculate_praise_proportion,
    detect_ai_writing_patterns,
    detect_bipartisan_forbidden_phrases,
    run_heuristic_validation,
    run_heuristic_validation_sync,
    validate_bipartisan_praise,
    validate_criticism_target,
    validate_key_phrase_inclusion,
)
from .keyword_common import (
    _count_user_keyword_exact_non_overlap,
    build_keyword_variants,
    count_keyword_coverage,
    count_keyword_occurrences,
    find_shadowed_user_keywords,
)
from .keyword_injection import _inject_keyword_into_section
from .keyword_reduction import (
    _remove_low_signal_keyword_sentence_once,
    _reduce_excess_user_keyword_mentions,
    _rewrite_sentence_to_reduce_keyword,
)
from .keyword_reference import _build_keyword_replacement_pool, _should_block_role_keyword_reference_sentence
from .keyword_validation import (
    build_fallback_draft,
    enforce_keyword_requirements,
    force_insert_insufficient_keywords,
    force_insert_preferred_exact_keywords,
    validate_keyword_insertion,
)
from .repetition_checker import (
    ALLOWED_ENDINGS,
    EXPLICIT_PLEDGE_PATTERNS,
    contains_pledge_candidate,
    detect_near_duplicate_sentences,
    detect_phrase_repetition,
    detect_sentence_repetition,
    enforce_repetition_requirements,
    extract_sentences,
    is_allowed_ending,
    is_explicit_pledge,
)
from .title_quality import validate_title_quality
from .workflow import evaluate_quality_with_llm, validate_and_retry

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
extractDateWeekdayPairs = extract_date_weekday_pairs
validateDateWeekdayPairs = validate_date_weekday_pairs
repairDateWeekdayPairs = repair_date_weekday_pairs
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
enforceRepetitionRequirements = enforce_repetition_requirements
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
    "extract_date_weekday_pairs",
    "validate_date_weekday_pairs",
    "repair_date_weekday_pairs",
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
    "find_shadowed_user_keywords",
    "validate_keyword_insertion",
    "enforce_keyword_requirements",
    "enforce_repetition_requirements",
    "force_insert_preferred_exact_keywords",
    "force_insert_insufficient_keywords",
    "validate_and_retry",
    "evaluate_quality_with_llm",
    "_build_keyword_replacement_pool",
    "_count_user_keyword_exact_non_overlap",
    "_inject_keyword_into_section",
    "_remove_low_signal_keyword_sentence_once",
    "_reduce_excess_user_keyword_mentions",
    "_rewrite_sentence_to_reduce_keyword",
    "_should_block_role_keyword_reference_sentence",
]
