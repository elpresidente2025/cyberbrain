"""Shared section contracts for matchup-oriented structured writing."""

from __future__ import annotations

from functools import lru_cache
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

_SPACE_RE = re.compile(r"\s+")
_SENTENCE_RE = re.compile(r"[^.!?。]+(?:(?<=\d)\.(?=\d)[^.!?。]+)*[.!?。]?")
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")
_SCORE_RE = re.compile(r"\d{1,2}(?:\.\d+)?%\s*대\s*\d{1,2}(?:\.\d+)?%")
_MATCHUP_RE = re.compile(r"(?:가상대결|양자대결|대결|접전)")
_FIRST_PERSON_RE = re.compile(r"(?:저는|제가)")
_ACTION_VERB_RE = re.compile(
    r"(?:확인했|준비했|찾아다녔|살폈|챙겼|겪었|배웠|세웠|만들었|이어왔|추진했|봤더니|정리했)"
)
_POLICY_LINK_RE = re.compile(
    r"(?:하겠습니다|세우겠습니다|추진하겠습니다|만들겠습니다|바꾸겠습니다|살리겠습니다|지원하겠습니다|유치하겠습니다|완성하겠습니다)"
)
_POLICY_ANSWER_RE = re.compile(r"(?:해법은|핵심은|방법은|실질(?:적)? 정책|실행 계획)")
_POLICY_DETAIL_RE = re.compile(
    r"(?:유치|지원|재개발|혁신|스타트업|산업 구조|일자리|첨단금융|관광 인프라|규제 완화|투자 유치|산학 협력)"
)
_EXPERIENCE_RE = re.compile(
    r"(?:\b\d{1,2}세에\b|이사\b|전무\b|CEO\b|센터장\b|졸업\b|태어나|다녔|거쳐|활약|활동(?:했|하며)?|경영 일선|현장에서|봉사|역임|재직|근무|맡(?:아|았|으며)?)"
)
_CONCRETE_RESULT_RE = re.compile(r"(?:\b\d{1,3}(?:\.\d+)?%|\b\d{1,4}명\b)")
_CLOSING_RE = re.compile(r"(?:반드시|끝까지|함께|해내겠습니다|실행하겠습니다|살려내겠습니다|이뤄내겠습니다)")
_QUESTION_HEADING_RE = re.compile(r"^(?:왜|무엇|어떻게|언제|어디|누가)\b")
_CAREER_REPEAT_MARKERS = (
    "스타트업 CEO",
    "CEO",
    "이사",
    "전무",
    "경영 일선",
)
_CAREER_SIGNATURE_MARKERS: tuple[tuple[str, str], ...] = (
    ("스타트업CEO", "ceo"),
    ("CEO", "ceo"),
    ("이사", "이사"),
    ("전무", "전무"),
    ("경영일선", "경영일선"),
    ("보좌관", "보좌관"),
    ("사무국장", "사무국장"),
    ("직무대행", "직무대행"),
    ("공동선대위원장", "선대위원장"),
    ("선대위원장", "선대위원장"),
    ("종합상황실장", "종합상황실장"),
    ("광역시의원", "광역의원"),
    ("광역의원", "광역의원"),
    ("시의원", "광역의원"),
    ("도의원", "광역의원"),
    ("구의원", "기초의원"),
    ("군의원", "기초의원"),
)

_POLICY_EVIDENCE_PROOF_RE = re.compile(r"(?:증명한\s+바|입증(?:된|됐다|되었|했습니다)?|검증(?:된|됐다|되었|했습니다)?)")
_POLICY_EVIDENCE_TOPIC_RE = re.compile(
    r"(?P<topic>[가-힣A-Za-z0-9][가-힣A-Za-z0-9·'\"_-]{1,24})의\s+(?:역할과\s+효과|효과)"
)
_POLICY_EVIDENCE_TENURE_RE = re.compile(
    r"(?P<office>[가-힣A-Za-z0-9][가-힣A-Za-z0-9·'\"_-]{1,24}(?:도지사|시장|군수|구청장|대통령|국회의원|지사))\s+재임\s*시절"
)
_POLICY_EVIDENCE_PERSON_RE = re.compile(
    r"(?P<name>[가-힣A-Za-z0-9][가-힣A-Za-z0-9·'\"_-]{1,20})\s*(?:대통령님?|대통령|국회의원님?|국회의원|도지사|시장|군수|구청장|지사)"
)
_POLICY_EVIDENCE_STOPWORDS = {
    "저는",
    "저의",
    "제가",
    "이미",
    "역할",
    "효과",
    "증명",
    "증명한",
    "입증",
    "검증",
    "바",
    "같이",
    "재임",
    "시절",
}

_HEADING_STOPWORDS = {
    "이유",
    "배경",
    "무엇",
    "무엇인가",
    "무엇을",
    "어떻게",
    "왜",
    "지금",
    "해야",
    "하나",
    "대한",
    "위한",
    "통한",
    "관련",
    "에서",
    "하는",
    "살릴",
    "드러난",
    "확인된",
}

_SELF_CERTIFICATION_PATTERNS = [
    re.compile(
        r"(?:이러한|이런|저의)?\s*(?:실질적인\s+|실천적인\s+|실천적\s+)?(?:삶의 궤적|경험|이력|경영 경험|행보|노력|비전)"
        r"[^.!?]{0,60}(?:자산|동력|기반|통찰력|전문성|실행력|역량|리더십|바탕|밑거름)"
        r"[^.!?]{0,30}(?:되|됩|될|갖추게|제공했|부여했|길러주었|주었|증명)"
    ),
    re.compile(
        r"(?:\b\d{1,2}세(?:라는\s+젊은\s+나이)?|CEO|이사|전무|경영\s+일선)"
        r"[^.!?]{0,96}(?:자산|동력|기반|통찰력|전문성|실행력|역량|리더십)"
        r"[^.!?]{0,24}(?:입니|되|됩|될|갖추게|제공했|부여했|길러주었|주었)"
    ),
    re.compile(
        r"(?:이러한|이런|저의)?\s*(?:혁신적인\s+|실천적인\s+|실천적\s+)?(?:경영\s+)?경험(?:은|이|을)"
        r"[^.!?]{0,72}(?:통찰력|전문성|역량|자산|능력|리더십|바탕|밑거름)"
        r"[^.!?]{0,30}(?:길러주었|제공했|증명|부여했|갖추게|주었)"
    ),
    re.compile(
        r"(?:실제\s+성과(?:로)?\s+(?:이미\s+)?)증명된\s+(?:저의\s+)?(?:역량|전문성|능력|리더십)"
    ),
    re.compile(
        r"(?:혁신적인\s+사고방식과\s+과감한\s+실행력|저의\s+리더십과\s+실질적인\s+경험)"
        r"[^.!?]{0,80}(?:자산|동력|기반|변화|도약)"
        r"[^.!?]{0,20}(?:되|됩|될|이끌|확신)"
    ),
    re.compile(
        r"(?:저의|제)\s+(?:비전|경쟁력|역량|리더십)"
        r"[^.!?]{0,40}(?:보여주|증명|이끌|확신)"
    ),
    re.compile(
        r"(?:저는|제가)\s+[^.!?]{0,48}(?:적임자|유일한\s+선택|준비된\s+후보|검증된\s+리더)"
        r"(?:입니다|라고\s+생각합니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:저는|제가)\s+[^.!?]{0,48}(?:유일한\s+후보|최고(?:의)?\s+후보)"
        r"(?:라고\s+자부합니다|입니다|라고\s+생각합니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:이는|이러한\s+결과(?:는)?)\s+[^.!?]{0,72}"
        r"(?:인정한\s+결과(?:라고\s+생각합니다|입니다)|비전과\s+[^.!?]{0,24}전문성을\s+인정한\s+결과)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:이는|이러한\s+결과(?:는)?)\s+[^.!?]{0,72}"
        r"(?:인정받은\s+결과(?:라고\s+생각합니다|입니다)|평가받은\s+결과(?:라고\s+생각합니다|입니다))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:저는|제가)\s+[^.!?]{0,64}"
        r"(?:준비가\s+완벽(?:하게|히)\s+되어\s+있(?:습니다|다고\s+생각합니다)"
        r"|완벽(?:하게|히)\s+준비되어\s+있(?:습니다|다고\s+생각합니다))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:[^.!?]{0,48})?"
        r"(?:준비가\s+완벽(?:하게|히)\s+되어\s+있(?:습니다|다고\s+생각합니다)"
        r"|완벽(?:하게|히)\s+준비되어\s+있(?:습니다|다고\s+생각합니다))",
        re.IGNORECASE,
    ),
]

_AUDIENCE_REACTION_PATTERNS = [
    re.compile(
        r"(?:시민|주민|독자|여러분)(?:들|께서|은|는|의)?"
        r"[^.!?]{0,50}(?:기대|열망|바람|원하|갈망|염원|지지|신뢰|공감)"
    ),
    re.compile(
        r"(?:(?:저의|제)[^.!?]{0,60}|(?:이러한|이런)[^.!?]{0,40}(?:경험|행동|결과|접근|노력|행보|방식)[^.!?]{0,20})"
        r"(?:시민|여러분)[^.!?]{0,40}"
        r"(?:덕분|덕택|덕에|때문|이어진|이어졌|연결|이끌|보여드리|보여주고|보여줍니다)"
    ),
    re.compile(
        r"(?:결과|수치|여론조사)[^.!?]{0,40}(?:시민|여러분)[^.!?]{0,60}"
        r"(?:기대|열망|바람|원하|갈망|염원)"
    ),
    re.compile(
        r"(?:저는|제가)[^.!?]{0,20}알려지고\s+있"
    ),
    re.compile(
        r"(?:시민|주민|여러분)(?:들|께서|은|는|이|가)?"
        r"[^.!?]{0,40}"
        r"(?:저의|제)[^.!?]{0,30}"
        r"(?:알아봐|알아주|인정해|평가해|선택해|지지해)"
        r"[^.!?]{0,10}(?:주신|주셨|주었|줬)"
    ),
]

_ROLE_PROMPTS = {
    "primary_matchup": "첫 문장은 가상대결 수치 사실로 시작하고, 다음 문장은 그 수치를 뒷받침하는 경력 사실·당시 행동·구체 결과로만 잇습니다.",
    "policy": "첫 문장은 해법을 직접 답하고, 다음 문장은 실행 방식·정책 수단·구체 계획으로만 전개합니다.",
    "secondary_matchup": "첫 문장은 보조 대결 수치 사실로 시작하고, 다음 문장은 구도 해석이 아니라 추가 사실·행동·구체 결과로만 이어갑니다.",
    "closing": "소제목은 선언형으로 두고, 첫 문장은 결론 요약 또는 다짐으로 시작하되 뒤 문장은 실행 계획과 생활 변화 약속으로만 정리합니다.",
}

_SECTION_WIDE_FORBIDDEN_ROLES = {"audience_reaction", "self_certification"}
_CROSS_SECTION_CONTRACT_CATEGORIES = frozenset({"matchup", "activity-report", "policy-proposal"})


def _merge_allowed_roles(*role_groups: Sequence[str]) -> List[str]:
    ordered_roles: List[str] = []
    for group in role_groups:
        for role in group:
            normalized = _normalize_text(role)
            if not normalized or normalized in ordered_roles:
                continue
            ordered_roles.append(normalized)
    return ordered_roles


def _normalize_text(value: Any) -> str:
    text = str(value or "")
    return _SPACE_RE.sub(" ", text).strip()


def _with_particle(word: str, consonant_particle: str, vowel_particle: str) -> str:
    text = _normalize_text(word)
    if not text:
        return ""
    last = text[-1]
    if not ("가" <= last <= "힣"):
        return f"{text}{consonant_particle}"
    has_jongseong = (ord(last) - ord("가")) % 28 != 0
    return f"{text}{consonant_particle if has_jongseong else vowel_particle}"


@lru_cache(maxsize=128)
def _build_first_person_re(speaker: str) -> re.Pattern[str]:
    normalized_speaker = _normalize_text(speaker)
    if not normalized_speaker:
        return _FIRST_PERSON_RE

    escaped_name = re.escape(normalized_speaker)
    topic_form = re.escape(_with_particle(normalized_speaker, "은", "는"))
    subject_form = re.escape(_with_particle(normalized_speaker, "이", "가"))
    return re.compile(
        rf"(?:저는|제가|저 {escaped_name}|저 {topic_form}|{topic_form}|{subject_form})"
    )


@lru_cache(maxsize=128)
def _build_dynamic_audience_reaction_patterns(speaker: str) -> tuple[re.Pattern[str], ...]:
    normalized_speaker = _normalize_text(speaker)
    if not normalized_speaker:
        return ()

    escaped_name = re.escape(normalized_speaker)
    topic_form = re.escape(_with_particle(normalized_speaker, "은", "는"))
    subject_form = re.escape(_with_particle(normalized_speaker, "이", "가"))
    return (
        re.compile(
            rf"(?:저 {escaped_name}|저 {topic_form}|{topic_form}|{subject_form})"
            rf"[^.!?]{{0,20}}알려지고\s+있"
        ),
        re.compile(
            rf"(?:시민|주민|여러분)(?:들|께서|은|는|이|가)?"
            rf"[^.!?]{{0,40}}"
            rf"(?:저의|제|{escaped_name})[^.!?]{{0,30}}"
            rf"(?:알아봐|알아주|인정해|평가해|선택해|지지해)"
            rf"[^.!?]{{0,10}}(?:주신|주셨|주었|줬)"
        ),
    )


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_speaker_ahead(record: Dict[str, Any]) -> bool:
    speaker_score = _to_float(record.get("speakerScore"))
    opponent_score = _to_float(record.get("opponentScore"))
    if speaker_score is None or opponent_score is None:
        return False
    return speaker_score > opponent_score


def _build_pair_fact_sentence(record: Dict[str, Any]) -> str:
    speaker = _normalize_text(record.get("speaker"))
    opponent = _normalize_text(record.get("opponent"))
    speaker_percent = _normalize_text(record.get("speakerPercent") or record.get("speakerScore"))
    opponent_percent = _normalize_text(record.get("opponentPercent") or record.get("opponentScore"))
    if not speaker or not opponent or not speaker_percent or not opponent_percent:
        return ""
    return f"{speaker}·{opponent} 가상대결에서는 {speaker_percent} 대 {opponent_percent}로 나타났습니다."


def _build_primary_matchup_heading(record: Dict[str, Any]) -> str:
    speaker = _normalize_text(record.get("speaker"))
    opponent = _normalize_text(record.get("opponent"))
    if not speaker or not opponent:
        return ""
    subject = _with_particle(speaker, "이", "가")
    if _is_speaker_ahead(record):
        return f"{subject} {opponent}와의 가상대결에서 앞선 이유"
    return f"{subject} {opponent}와의 가상대결에서 접전을 만든 배경"


def _build_secondary_matchup_heading(record: Dict[str, Any]) -> str:
    speaker = _normalize_text(record.get("speaker"))
    opponent = _normalize_text(record.get("opponent"))
    if not speaker or not opponent:
        return ""
    margin = _to_float(record.get("margin"))
    if margin is not None and margin <= 3.1:
        return f"{opponent}과의 접전에서 확인된 {speaker} 경쟁력"
    return f"{opponent}과의 대결에서 드러난 {speaker} 구도"


def split_sentences(text: Any) -> List[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    return [sentence for sentence in (_normalize_text(chunk) for chunk in _SENTENCE_RE.findall(normalized)) if sentence]


def _tokenize(text: Any) -> List[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    tokens: List[str] = []
    for raw in _TOKEN_RE.findall(normalized):
        token = raw.lower()
        if token in _HEADING_STOPWORDS or token.isdigit():
            continue
        tokens.append(token)
    return tokens


def _answer_lead_alignment_score(sentence: str, answer_lead: str) -> float:
    answer_tokens = set(_tokenize(answer_lead))
    if not answer_tokens:
        return 0.0
    sentence_tokens = set(_tokenize(sentence))
    if not sentence_tokens:
        return 0.0
    return len(answer_tokens & sentence_tokens) / max(1, len(answer_tokens))


def is_declarative_heading(heading: Any) -> bool:
    text = _normalize_text(heading)
    if not text:
        return False
    if "?" in text or text.endswith("?"):
        return False
    if _QUESTION_HEADING_RE.search(text):
        return False
    return True


def infer_sentence_role(
    sentence: Any,
    *,
    speaker: str = "",
    opponent: str = "",
) -> str:
    text = _normalize_text(sentence)
    if not text:
        return "empty"
    normalized_speaker = _normalize_text(speaker)
    normalized_opponent = _normalize_text(opponent)
    first_person_re = _build_first_person_re(normalized_speaker)
    dynamic_audience_patterns = _build_dynamic_audience_reaction_patterns(normalized_speaker)
    if any(pattern.search(text) for pattern in _AUDIENCE_REACTION_PATTERNS) or any(
        pattern.search(text) for pattern in dynamic_audience_patterns
    ):
        return "audience_reaction"
    if any(pattern.search(text) for pattern in _SELF_CERTIFICATION_PATTERNS):
        return "self_certification"
    if _MATCHUP_RE.search(text) and _SCORE_RE.search(text):
        return "matchup_fact"
    if normalized_speaker and normalized_speaker in text and normalized_opponent and normalized_opponent in text and _SCORE_RE.search(text):
        return "matchup_fact"
    if _POLICY_ANSWER_RE.search(text):
        return "policy_answer"
    if _CLOSING_RE.search(text):
        return "closing_commitment"
    if _EXPERIENCE_RE.search(text):
        return "experience_fact"
    if first_person_re.search(text) and _ACTION_VERB_RE.search(text):
        return "speaker_action"
    if _POLICY_LINK_RE.search(text):
        return "policy_link"
    if _POLICY_DETAIL_RE.search(text):
        return "policy_detail"
    if _CONCRETE_RESULT_RE.search(text) or _SCORE_RE.search(text):
        return "concrete_result"
    return "other"


def _extract_normalized_career_markers(sentence: Any) -> List[str]:
    text = _normalize_text(sentence)
    if not text:
        return []

    compact = re.sub(r"\s+", "", text).lower()
    markers: List[str] = []
    for raw_marker, normalized_marker in _CAREER_SIGNATURE_MARKERS:
        probe = re.sub(r"\s+", "", str(raw_marker or "")).lower()
        if not probe or probe not in compact or normalized_marker in markers:
            continue
        markers.append(normalized_marker)
    return markers


def extract_career_fact_signature(
    sentence: Any,
    *,
    speaker: str = "",
    opponent: str = "",
) -> str:
    text = _normalize_text(sentence)
    if not text:
        return ""

    markers = _extract_normalized_career_markers(text)
    has_experience_cue = bool(_EXPERIENCE_RE.search(text))
    is_list_like = (text.count(",") + text.count("·")) >= 1
    inferred_role = infer_sentence_role(text, speaker=speaker, opponent=opponent)

    if inferred_role != "experience_fact" and not (has_experience_cue and len(markers) >= 2):
        return ""
    if len(markers) >= 2:
        return "|".join(sorted(markers))
    if len(markers) == 1 and has_experience_cue and is_list_like:
        return markers[0]
    if len(text) >= 24 and has_experience_cue and is_list_like:
        return text.lower()
    return ""


def _normalize_policy_evidence_token(token: Any) -> str:
    normalized = _normalize_text(token).lower()
    if not normalized:
        return ""
    for suffix in (
        "님께서",
        "께서",
        "님께",
        "께",
        "님",
        "으로서",
        "로서",
        "으로",
        "로",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "과",
        "와",
        "도",
        "의",
    ):
        if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 2:
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def extract_policy_evidence_signature(sentence: Any) -> str:
    text = _normalize_text(sentence)
    if not text or not _POLICY_EVIDENCE_PROOF_RE.search(text):
        return ""

    tokens: List[str] = []
    topic_match = _POLICY_EVIDENCE_TOPIC_RE.search(text)
    if topic_match:
        topic_token = _normalize_policy_evidence_token(topic_match.group("topic"))
        if topic_token:
            tokens.append(topic_token)

    person_match = _POLICY_EVIDENCE_PERSON_RE.search(text)
    if person_match:
        person_token = _normalize_policy_evidence_token(person_match.group("name"))
        if person_token:
            tokens.append(person_token)

    tenure_match = _POLICY_EVIDENCE_TENURE_RE.search(text)
    if tenure_match:
        office_token = _normalize_policy_evidence_token(tenure_match.group("office"))
        if office_token:
            tokens.append(office_token)

    if len(tokens) < 2:
        for raw_token in _TOKEN_RE.findall(text):
            normalized = _normalize_policy_evidence_token(raw_token)
            if (
                not normalized
                or normalized in _POLICY_EVIDENCE_STOPWORDS
                or normalized in tokens
            ):
                continue
            if any(cue in normalized for cue in ("정책", "제도", "모델", "화폐", "연금", "공약", "기본소득")):
                tokens.append(normalized)

    deduped_tokens: List[str] = []
    for token in tokens:
        if token and token not in _POLICY_EVIDENCE_STOPWORDS and token not in deduped_tokens:
            deduped_tokens.append(token)

    if len(deduped_tokens) < 2:
        return ""
    return "|".join(sorted(deduped_tokens))


def build_matchup_allowed_h2_kinds(
    primary_pair: Dict[str, Any],
    secondary_pairs: Sequence[Dict[str, Any]],
    speaker: str,
) -> List[Dict[str, Any]]:
    contracts: List[Dict[str, Any]] = []
    primary_heading = _build_primary_matchup_heading(primary_pair)
    primary_answer = _build_pair_fact_sentence(primary_pair)
    if primary_heading:
        contracts.append(
            {
                "id": "primary_matchup",
                "label": "주대결 결과",
                "template": primary_heading,
                "answerLead": primary_answer,
                "headingStyle": "declarative",
                "firstSentenceRoles": ["matchup_fact"],
                "experienceFollowupRoles": [
                    "experience_fact",
                    "speaker_action",
                    "concrete_result",
                    "policy_link",
                    "policy_detail",
                ],
                "allowedSentenceRoles": _merge_allowed_roles(
                    ["matchup_fact"],
                    [
                        "experience_fact",
                        "speaker_action",
                        "concrete_result",
                        "policy_link",
                        "policy_detail",
                    ],
                ),
                "forbiddenLeadRoles": ["self_certification", "audience_reaction"],
                "forbiddenAfterExperienceRoles": ["self_certification", "audience_reaction"],
                "bodyWriterHint": _ROLE_PROMPTS["primary_matchup"],
                "minLeadOverlap": 0.35,
            }
        )

    contracts.append(
        {
            "id": "policy",
            "label": "정책 비전",
            "template": f"부산 경제를 살릴 {speaker}의 해법",
            "answerLead": (
                "부산 경제를 살릴 해법은 지역 산업과 일자리 문제를 함께 풀 수 있는 "
                "실질적 정책에 있습니다."
            ),
            "headingStyle": "declarative",
            "firstSentenceRoles": ["policy_answer", "policy_link"],
            "experienceFollowupRoles": [
                "speaker_action",
                "policy_detail",
                "policy_link",
                "concrete_result",
                "experience_fact",
            ],
            "allowedSentenceRoles": _merge_allowed_roles(
                ["policy_answer", "policy_link"],
                [
                    "speaker_action",
                    "policy_detail",
                    "policy_link",
                    "concrete_result",
                    "experience_fact",
                ],
            ),
            "forbiddenLeadRoles": ["self_certification", "audience_reaction"],
            "forbiddenAfterExperienceRoles": ["self_certification", "audience_reaction"],
            "bodyWriterHint": _ROLE_PROMPTS["policy"],
            "minLeadOverlap": 0.28,
        }
    )

    if secondary_pairs:
        secondary_heading = _build_secondary_matchup_heading(secondary_pairs[0])
        secondary_answer = _build_pair_fact_sentence(secondary_pairs[0])
        if secondary_heading:
            contracts.append(
                {
                    "id": "secondary_matchup",
                    "label": "보조 대결",
                    "template": secondary_heading,
                    "answerLead": secondary_answer,
                    "headingStyle": "declarative",
                    "firstSentenceRoles": ["matchup_fact"],
                    "experienceFollowupRoles": [
                        "experience_fact",
                        "speaker_action",
                        "concrete_result",
                        "policy_link",
                        "policy_detail",
                    ],
                    "allowedSentenceRoles": _merge_allowed_roles(
                        ["matchup_fact"],
                        [
                            "experience_fact",
                            "speaker_action",
                            "concrete_result",
                            "policy_link",
                            "policy_detail",
                        ],
                    ),
                    "forbiddenLeadRoles": ["self_certification", "audience_reaction"],
                    "forbiddenAfterExperienceRoles": ["self_certification", "audience_reaction"],
                    "bodyWriterHint": _ROLE_PROMPTS["secondary_matchup"],
                    "minLeadOverlap": 0.3,
                }
            )

    contracts.append(
        {
            "id": "closing",
            "label": "마무리",
            "template": f"지금 {speaker}에 주목해야 하는 이유",
            "answerLead": f"지금 {speaker}의 경쟁력은 확인됐습니다.",
            "headingStyle": "declarative",
            "firstSentenceRoles": ["closing_commitment", "policy_link", "policy_answer", "speaker_action"],
            "experienceFollowupRoles": [
                "speaker_action",
                "policy_detail",
                "policy_link",
                "closing_commitment",
                "concrete_result",
            ],
            "allowedSentenceRoles": _merge_allowed_roles(
                ["closing_commitment", "policy_link", "policy_answer", "speaker_action"],
                [
                    "speaker_action",
                    "policy_detail",
                    "policy_link",
                    "closing_commitment",
                    "concrete_result",
                ],
            ),
            "forbiddenLeadRoles": ["self_certification", "audience_reaction"],
            "forbiddenAfterExperienceRoles": ["self_certification", "audience_reaction"],
            "bodyWriterHint": _ROLE_PROMPTS["closing"],
            "minLeadOverlap": 0.12,
        }
    )
    return contracts


def get_matchup_section_contracts(bundle: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(bundle, dict):
        return []
    if _normalize_text(bundle.get("scope")).lower() != "matchup":
        return []
    allowed = bundle.get("allowedH2Kinds")
    if isinstance(allowed, list):
        contracts = [dict(item) for item in allowed if isinstance(item, dict) and _normalize_text(item.get("id"))]
        if contracts and all(item.get("firstSentenceRoles") for item in contracts):
            return contracts
    primary_pair = bundle.get("primaryPair") if isinstance(bundle.get("primaryPair"), dict) else {}
    secondary_pairs = bundle.get("secondaryPairs") if isinstance(bundle.get("secondaryPairs"), list) else []
    speaker = _normalize_text(bundle.get("speaker") or primary_pair.get("speaker"))
    return build_matchup_allowed_h2_kinds(primary_pair, secondary_pairs, speaker)


def get_section_contract_sequence(
    bundle: Optional[Dict[str, Any]],
    *,
    body_sections: int,
) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    contracts = get_matchup_section_contracts(bundle)
    if not contracts:
        return [], None
    body_contracts = [item for item in contracts if _normalize_text(item.get("id")) != "closing"]
    conclusion_contract = next(
        (item for item in contracts if _normalize_text(item.get("id")) == "closing"),
        None,
    )
    if body_sections > 0:
        body_contracts = body_contracts[:body_sections]
    return body_contracts, conclusion_contract


def build_shared_contract_rules() -> List[str]:
    return [
        "섹션 전체 허용 역할은 수치 사실, 경력 사실, 화자 행동, 구체 결과, 정책 연결·세부, 결론 다짐뿐입니다.",
        "타인 반응 해석형과 경험 → 역량 인증형은 어떤 자리에서도 허용 역할에 포함되지 않습니다.",
        "경험 문장 다음에는 사실, 당시 행동, 구체 결과, 현재 해법 연결만 올 수 있습니다.",
        "경험 다음 문장에서 자기 역량 인증이나 시민 반응 해설로 건너뛰지 않습니다.",
        "같은 경력 나열은 원고 전체에서 한 번만 쓰고, 이후 섹션에서는 그 경험이나 현장에서 익힌 것으로만 받습니다.",
        "소제목은 본문 첫 2문장을 먼저 쓴 뒤, 그 문단이 이미 답한 핵심을 선언형 또는 명사형으로만 요약합니다.",
    ]


def _extract_career_fact_signature(
    sentence: Any,
    *,
    speaker: str = "",
    opponent: str = "",
) -> str:
    return extract_career_fact_signature(
        sentence,
        speaker=speaker,
        opponent=opponent,
    )


def validate_cross_section_contracts(
    *,
    sections: Sequence[Dict[str, Any]],
    speaker: str = "",
    opponent: str = "",
) -> Optional[Dict[str, Any]]:
    seen_career_signatures: Dict[str, Dict[str, Any]] = {}
    seen_policy_evidence_signatures: Dict[str, Dict[str, Any]] = {}

    for section_index, section in enumerate(sections, start=1):
        heading_text = _normalize_text(section.get("heading"))
        paragraphs = section.get("paragraphs") if isinstance(section, dict) else []
        if not isinstance(paragraphs, list):
            continue
        for paragraph in paragraphs:
            for sentence in split_sentences(paragraph):
                signature = _extract_career_fact_signature(
                    sentence,
                    speaker=speaker,
                    opponent=opponent,
                )
                policy_signature = extract_policy_evidence_signature(sentence)
                if policy_signature:
                    prior_policy = seen_policy_evidence_signatures.get(policy_signature)
                    if prior_policy:
                        return {
                            "code": "duplicate_policy_evidence_fact",
                            "message": "같은 정책 근거 문장을 다른 섹션에서 반복했습니다. 동일한 정책 사례/검증 근거는 한 번만 쓰고, 다음 섹션에서는 실행 계획이나 효과만 이어가십시오.",
                            "sentence": sentence,
                            "sectionIndex": section_index,
                            "sectionHeading": heading_text,
                            "firstSectionIndex": prior_policy.get("sectionIndex"),
                            "firstSectionHeading": prior_policy.get("sectionHeading"),
                        }
                    seen_policy_evidence_signatures[policy_signature] = {
                        "sectionIndex": section_index,
                        "sectionHeading": heading_text,
                    }
                if not signature:
                    continue
                prior = seen_career_signatures.get(signature)
                if prior:
                    return {
                        "code": "duplicate_career_fact",
                        "message": "같은 경력 나열이 다른 섹션에 반복되었습니다. 경력 문장은 원고 전체에서 한 번만 씁니다.",
                        "sentence": sentence,
                        "sectionIndex": section_index,
                        "sectionHeading": heading_text,
                        "firstSectionIndex": prior.get("sectionIndex"),
                        "firstSectionHeading": prior.get("sectionHeading"),
                    }
                seen_career_signatures[signature] = {
                    "sectionIndex": section_index,
                    "sectionHeading": heading_text,
                }

    return None


def should_apply_cross_section_contracts(category: Any) -> bool:
    return _normalize_text(category).lower() in _CROSS_SECTION_CONTRACT_CATEGORIES


_SECTION_LANE_CATEGORIES = frozenset({"activity-report", "policy-proposal"})
_SECTION_LANE_HEADING_KEYWORDS = {
    "achievement": (
        "성과",
        "입법",
        "조례",
        "예산",
        "의정활동",
        "실적",
        "기여",
        "확보",
    ),
    "future": (
        "미래",
        "비전",
        "과제",
        "방향",
        "계획",
        "약속",
        "로드맵",
        "청사진",
        "조성",
        "추진",
        "완성",
    ),
    "context": (
        "역할",
        "경험",
        "헌신",
        "이해",
        "배경",
        "걸어온",
        "발자취",
    ),
}
_FUTURE_POLICY_MODAL_RE = re.compile(
    r"(?:하겠습니다|하겠으며|할 것입니다|힘쓰겠습니다|노력하겠습니다|추진하겠습니다|완성하겠습니다|"
    r"유치하겠습니다|검토하겠습니다|만들겠습니다|나서겠습니다|챙기겠습니다|집중하겠습니다|"
    r"가시화하겠습니다|마련하겠습니다)"
)
_FUTURE_POLICY_TOPIC_RE = re.compile(
    r"(?:추진|조성|유치|완성|계획|지정|설치|확보|가시화|도입|재배치|개편|정비|개정|"
    r"산단|산업단지|철도|교통망|캠퍼스|스타트업|RE100|지역화폐|기본소득|연금|플랫폼)"
)


def should_apply_section_lane_contracts(category: Any) -> bool:
    return _normalize_text(category).lower() in _SECTION_LANE_CATEGORIES


def infer_section_semantic_lane(heading: Any) -> str:
    heading_text = _normalize_text(heading)
    if not heading_text:
        return ""

    scores = {
        lane: sum(1 for token in keywords if token in heading_text)
        for lane, keywords in _SECTION_LANE_HEADING_KEYWORDS.items()
    }
    future_score = scores.get("future", 0)
    achievement_score = scores.get("achievement", 0)
    context_score = scores.get("context", 0)

    if future_score > 0 and future_score >= max(achievement_score, context_score):
        return "future"
    if achievement_score > 0 and achievement_score >= context_score:
        return "achievement"
    if context_score > 0:
        return "context"
    return ""


def is_future_policy_agenda_sentence(sentence: Any) -> bool:
    sentence_text = _normalize_text(sentence)
    if not sentence_text:
        return False
    return bool(
        _FUTURE_POLICY_MODAL_RE.search(sentence_text)
        and _FUTURE_POLICY_TOPIC_RE.search(sentence_text)
    )


def find_section_semantic_mismatch(
    *,
    sections: Sequence[Dict[str, Any]],
    category: Any = "",
) -> Optional[Dict[str, Any]]:
    if not should_apply_section_lane_contracts(category):
        return None

    normalized_sections: List[Dict[str, Any]] = []
    for section in sections:
        heading_text = _normalize_text(section.get("heading"))
        paragraphs = section.get("paragraphs") if isinstance(section, dict) else []
        if not heading_text or not isinstance(paragraphs, list):
            continue
        paragraph_list = [_normalize_text(item) for item in paragraphs if _normalize_text(item)]
        if not paragraph_list:
            continue
        normalized_sections.append(
            {
                "heading": heading_text,
                "paragraphs": paragraph_list,
            }
        )

    if len(normalized_sections) < 2:
        return None

    future_target_indices = [
        index
        for index, section in enumerate(normalized_sections, start=1)
        if infer_section_semantic_lane(section.get("heading")) == "future"
    ]
    if not future_target_indices:
        return None

    target_section_index = future_target_indices[-1]
    target_heading = _normalize_text(
        normalized_sections[target_section_index - 1].get("heading")
    )

    for section_index, section in enumerate(normalized_sections, start=1):
        if section_index >= target_section_index:
            continue
        lane = infer_section_semantic_lane(section.get("heading"))
        if lane not in {"achievement", "context"}:
            continue
        for paragraph in section.get("paragraphs") or []:
            for sentence in split_sentences(paragraph):
                if not is_future_policy_agenda_sentence(sentence):
                    continue
                return {
                    "code": "section_topic_drift",
                    "message": "성과/맥락 섹션에 앞으로의 실행 과제가 섞여 있습니다.",
                    "sentence": sentence,
                    "sectionIndex": section_index,
                    "sectionHeading": _normalize_text(section.get("heading")),
                    "targetSectionIndex": target_section_index,
                    "targetSectionHeading": target_heading,
                    "lane": lane,
                }

    return None


def validate_section_contract(
    *,
    heading: Any,
    paragraphs: Iterable[Any],
    contract: Optional[Dict[str, Any]],
    speaker: str = "",
    opponent: str = "",
) -> Optional[Dict[str, Any]]:
    if not isinstance(contract, dict):
        return None

    heading_text = _normalize_text(heading)
    paragraph_list = [_normalize_text(item) for item in paragraphs if _normalize_text(item)]
    if not heading_text or not paragraph_list:
        return None

    if _normalize_text(contract.get("headingStyle")).lower() == "declarative" and not is_declarative_heading(heading_text):
        return {
            "code": "heading_not_declarative",
            "message": f"소제목은 질문형이 아니라 선언형/명사형이어야 합니다 ('{heading_text}').",
        }

    sentences: List[str] = []
    for paragraph in paragraph_list:
        sentences.extend(split_sentences(paragraph))
    if not sentences:
        return None

    first_sentence = sentences[0]
    first_role = infer_sentence_role(first_sentence, speaker=speaker, opponent=opponent)
    forbidden_lead_roles = set(contract.get("forbiddenLeadRoles") or [])
    if first_role in forbidden_lead_roles:
        return {
            "code": "first_sentence_forbidden_role",
            "message": f"첫 문장이 금지된 역할({first_role})로 시작했습니다.",
            "sentence": first_sentence,
        }

    allowed_first_roles = set(contract.get("firstSentenceRoles") or [])
    answer_lead = _normalize_text(contract.get("answerLead"))
    min_overlap = float(contract.get("minLeadOverlap") or 0.0)
    alignment_score = _answer_lead_alignment_score(first_sentence, answer_lead)
    if allowed_first_roles and first_role not in allowed_first_roles and alignment_score < min_overlap:
        return {
            "code": "first_sentence_role_mismatch",
            "message": f"첫 문장이 소제목에 직접 답하지 않습니다 ('{heading_text}').",
            "sentence": first_sentence,
            "role": first_role,
            "score": alignment_score,
        }

    allowed_sentence_roles = set(contract.get("allowedSentenceRoles") or [])
    for sentence in sentences:
        role = infer_sentence_role(sentence, speaker=speaker, opponent=opponent)
        if role in _SECTION_WIDE_FORBIDDEN_ROLES and role not in allowed_sentence_roles:
            return {
                "code": "section_disallowed_role",
                "message": "허용 문장 유형에 없는 역할(타인 반응 해석형 또는 경험→역량 인증형)이 섹션에 들어갔습니다.",
                "sentence": sentence,
                "role": role,
            }

    allowed_followups = set(contract.get("experienceFollowupRoles") or [])
    forbidden_followups = set(contract.get("forbiddenAfterExperienceRoles") or [])
    for index, sentence in enumerate(sentences[:-1]):
        current_role = infer_sentence_role(sentence, speaker=speaker, opponent=opponent)
        if current_role != "experience_fact":
            continue
        next_sentence = sentences[index + 1]
        next_role = infer_sentence_role(next_sentence, speaker=speaker, opponent=opponent)
        if next_role in forbidden_followups:
            return {
                "code": "experience_followup_disallowed",
                "message": "경험 문장 다음에 자기 역량 인증 또는 청중 반응 해설이 붙었습니다.",
                "sentence": next_sentence,
                "role": next_role,
            }
        if allowed_followups and next_role not in allowed_followups:
            return {
                "code": "experience_followup_role_mismatch",
                "message": "경험 문장 다음에는 사실·행동·구체 결과·해법 연결만 올 수 있습니다.",
                "sentence": next_sentence,
                "role": next_role,
            }

    return None


__all__ = [
    "build_matchup_allowed_h2_kinds",
    "build_shared_contract_rules",
    "extract_career_fact_signature",
    "find_section_semantic_mismatch",
    "get_matchup_section_contracts",
    "get_section_contract_sequence",
    "infer_sentence_role",
    "infer_section_semantic_lane",
    "is_future_policy_agenda_sentence",
    "is_declarative_heading",
    "should_apply_section_lane_contracts",
    "split_sentences",
    "should_apply_cross_section_contracts",
    "validate_cross_section_contracts",
    "validate_section_contract",
]
