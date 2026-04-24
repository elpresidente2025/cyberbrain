import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from ..common.stance_filters import looks_like_hashtag_bullet_line
from .structure_utils import (
    strip_html,
    normalize_context_text,
    _xml_text,
    _xml_cdata,
    material_key,
)


class ContextAnalyzer:
    def __init__(self, model_name: str):
        self.model_name = model_name

    _IMPLEMENTATION_PLAN_TYPES = {
        "implementation_plan",
        "policy_revival_plan",
        "problem_solution_plan",
        "restoration_plan",
    }

    def _sanitize_context_material_text(self, value: Any) -> str:
        text = normalize_context_text(value)
        if not text:
            return ""
        cleaned = re.sub(
            r"^\s*(?:[#>*-]\s*)?(?:\d+[.)]\s*)?"
            r"(?:내\s*입장문|입장문|실제\s*원고|뉴스\s*/?\s*데이터(?:\s*\d+)?|뉴스(?:\s*\d+)?|데이터(?:\s*\d+)?)"
            r"\s*[:：]\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t-•")
        return cleaned

    def _is_noisy_stance_material(self, text: str) -> bool:
        plain = re.sub(r"\s+", " ", strip_html(text or "")).strip()
        if not plain:
            return True
        if looks_like_hashtag_bullet_line(plain):
            return True

        if re.fullmatch(r"(?:관련\s*현안(?:와|은|는|이|가)?|해당\s*현안(?:와|은|는|이|가)?)", plain):
            return True

        hard_patterns = [
            r"입력\s*[:：]\s*\d{4}[-./]\d{1,2}[-./]\d{1,2}",
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            r"연합뉴스",
            r"(?:^|\s)기자(?:\s|$)",
            r"서울\s*중구\s*하나은행",
            r"현황판",
        ]
        if any(re.search(pattern, plain, re.IGNORECASE) for pattern in hard_patterns):
            return True

        stock_markers = (
            "코스피",
            "순매도",
            "장중",
            "역대 최고가",
            "sk하이닉스",
            "삼성전자",
            "두산에너빌리티",
        )
        lowered = plain.lower()
        marker_hits = sum(1 for marker in stock_markers if marker in lowered)
        return marker_hits >= 2

    def _is_noisy_news_material(self, text: str) -> bool:
        plain = re.sub(r"\s+", " ", strip_html(text or "")).strip()
        if not plain:
            return True

        hard_meta_patterns = [
            r"^\s*입력\s*[:：]",
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            r"(?:^|\s)기자(?:\s|$)",
            r"연합뉴스",
            r"현황판",
            r"딜링룸",
            r"하나은행\s*본점",
            r"^\s*가\s*$",
        ]
        return any(re.search(pattern, plain, re.IGNORECASE) for pattern in hard_meta_patterns)

    def _normalize_answer_type(self, value: Any) -> str:
        raw = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", str(value or "").strip().lower()).strip("_")
        aliases = {
            "policy_revival_plan": "implementation_plan",
            "revival_plan": "implementation_plan",
            "restoration_plan": "implementation_plan",
            "problem_solution_plan": "implementation_plan",
            "solution_plan": "implementation_plan",
            "execution_plan": "implementation_plan",
            "실행안": "implementation_plan",
            "부활방안": "implementation_plan",
            "복구계획": "implementation_plan",
            "정책실행안": "implementation_plan",
            "policy_defense": "policy_defense",
            "policy_promotion": "policy_promotion",
            "value_statement": "value_statement",
            "activity_report": "activity_report",
        }
        return aliases.get(raw, raw)

    def _dedupe_execution_items(self, values: List[str], *, max_items: int = 8) -> List[str]:
        items: List[str] = []
        seen: set[str] = set()
        for raw in values:
            item = self._sanitize_context_material_text(raw)
            item = re.sub(r"\s+", " ", item).strip(" \t-•,.;")
            if len(strip_html(item)) < 4:
                continue
            key = material_key(item)
            if not key or key in seen:
                continue
            seen.add(key)
            items.append(item)
            if len(items) >= max_items:
                break
        return items

    def _dedupe_contract_labels(self, values: List[str], *, max_items: int = 12) -> List[str]:
        items: List[str] = []
        seen: set[str] = set()
        for raw in values:
            item = self._sanitize_context_material_text(raw)
            item = re.sub(r"\s+", " ", item).strip(" \t-•,.;")
            if not item:
                continue
            key = material_key(item) or item
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
            if len(items) >= max_items:
                break
        return items

    def _coerce_execution_item_list(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [value]
        return []

    def _extract_primary_policy_surface(self, stance_text: str) -> str:
        text = normalize_context_text(stance_text)
        if not text:
            return ""

        candidates: List[Tuple[int, str]] = []

        quote_pattern = re.compile(r"[\"'“”‘’「『]([^\"'“”‘’」』\n]{2,30})[\"'“”‘’」』]")
        for match in quote_pattern.finditer(text):
            value = normalize_context_text(match.group(1))
            if not value:
                continue
            left = text[max(0, match.start() - 24):match.start()]
            right = text[match.end():min(len(text), match.end() + 24)]
            around = f"{left} {right}"
            score = 3
            if re.search(r"(지역화폐|정책|사업|제도|상품권|조례|지원)", around):
                score += 5
            if re.search(r"[A-Za-z0-9]", value):
                score += 2
            if value in {"도루묵", "포퓰리즘"}:
                score -= 8
            candidates.append((score, value))

        policy_pattern = re.compile(
            r"([가-힣A-Za-z0-9][가-힣A-Za-z0-9·+\-]{1,28})\s*"
            r"(?:지역화폐|정책|사업|제도|상품권)"
        )
        for match in policy_pattern.finditer(text):
            value = normalize_context_text(match.group(1))
            if value and len(value.replace(" ", "")) >= 2:
                candidates.append((4, value))

        if not candidates:
            return ""

        candidates.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
        return candidates[0][1]

    def _extract_execution_items_from_stance(self, stance_text: str, primary_policy: str = "") -> List[str]:
        text = normalize_context_text(stance_text)
        compact = re.sub(r"\s+", "", text)
        if not compact:
            return []

        items: List[str] = []

        def add(condition: bool, item: str) -> None:
            if condition:
                items.append(item)

        add(bool(re.search(r"캐시백.{0,20}(줄|축소|삭감|감소|낮)", text)), "캐시백 요율 회복")
        add(bool(re.search(r"지원책.{0,20}(줄|축소|삭감|감소)", text)) or "각종지원책" in compact, "지원책 복원")
        add(
            bool(re.search(r"담당\s*부서|부서.{0,20}말석|추진\s*체계|전담\s*부서", text)),
            "담당 부서 재정비",
        )
        name_item = f"{primary_policy} 명칭 회복" if primary_policy else "정책 명칭 회복"
        add(
            bool(re.search(r"명칭.{0,20}(사용하지|쓰지|재개|회복)|브랜드|이름.{0,12}(사용하지|재개|회복)", text)),
            name_item,
        )
        add(bool(re.search(r"이용자\s*수|결제액", text)), "이용자 수와 결제액 회복")
        add("연구단체" in compact, "의원 연구단체 구성")
        add(bool(re.search(r"(영향|효과).{0,20}(분석|짚|점검)|분석", text)), "정책 효과 분석")
        add(bool(re.search(r"조례.{0,12}(개정|제정|정비)|관련\s*조례", text)), "관련 조례 개정")
        add(bool(re.search(r"예산.{0,12}(확보|편성|운용)", text)), "예산 확보와 운용 기준 마련")
        add(bool(re.search(r"가맹점.{0,18}(확대|지원|관리)", text)), "가맹점 확대와 현장 지원")
        add(bool(re.search(r"조례.{0,12}제정|조례\s*제정", text)), "조례 제정 추진")
        add("햇빛지도" in compact or bool(re.search(r"일조량.{0,12}(분석|조사)", text)), "햇빛지도 제작과 일조량 분석")
        add(
            bool(re.search(r"공영\s*주차장|공공기관\s*옥상|태양광\s*발전시설", text)),
            "태양광 발전시설 입지 검토",
        )
        add(bool(re.search(r"수익성.{0,12}(분석|검토)|용역", text)), "입지·수익성 분석 용역 추진")
        add(bool(re.search(r"이익.{0,12}(주민|지역\s*주민).{0,20}(나눠|분배|공유)", text)), "개발이익 주민 공유")
        add(bool(re.search(r"이익\s*공유형\s*기본소득|이익공유형\s*기본소득", text)), "이익공유형 기본소득 모델 설계")
        district_match = re.search(r"((?:[가-힣]{2,12}구)|(?:\{region\}))부터.{0,20}(점진|시범|먼저|추진)", text)
        if district_match:
            add(True, f"{district_match.group(1)}부터 점진 추진")

        return self._dedupe_execution_items(items)

    def _extract_required_source_facts_from_stance(self, stance_text: str) -> List[str]:
        text = normalize_context_text(stance_text)
        compact = re.sub(r"\s+", "", text)
        if not compact:
            return []
        primary_policy = self._extract_primary_policy_surface(text)

        facts: List[str] = []

        def add(condition: bool, fact: str) -> None:
            if condition:
                facts.append(fact)

        add(bool(re.search(r"캐시백.{0,20}(줄|축소|삭감|감소|낮)", text)), "캐시백 요율 축소")
        add(bool(re.search(r"지원책.{0,20}(줄|축소|삭감|감소)", text)) or "각종지원책" in compact, "지원책 축소")
        add(bool(re.search(r"담당\s*부서|부서.{0,20}말석", text)), "담당 부서 위상 약화")
        add(bool(re.search(r"명칭.{0,20}(사용하지|쓰지)|브랜드|이름.{0,12}(사용하지|쓰지)", text)), "정책 명칭 미사용")
        add(bool(re.search(r"이용자\s*수.{0,20}급감|결제액.{0,20}급감|이용자\s*수와\s*결제액", text)), "이용자 수와 결제액 급감")
        add("역외" in compact and "소비" in compact, "지역 내 소비와 역외 소비 둔화 효과 약화")
        add("연구단체" in compact, "의원 연구단체 구성")
        add(bool(re.search(r"조례.{0,12}(개정|제정|정비)|관련\s*조례", text)), "관련 조례 개정")
        add(bool(re.search(r"신재생에너지.{0,20}개발이익.{0,12}공유|개발이익\s*공유", text)), "신재생에너지 개발이익 공유")
        add(bool(primary_policy and "연금" in primary_policy), f"{primary_policy} 지역 모델")
        add("햇빛지도" in compact, "햇빛지도 제작")
        add(bool(re.search(r"일조량.{0,12}(분석|조사)", text)), "관내 일조량 분석")
        add(bool(re.search(r"공영\s*주차장|공공기관\s*옥상", text)), "공영주차장·공공기관 옥상 검토")
        add(bool(re.search(r"태양광\s*발전시설", text)), "태양광 발전시설 적합 지역 분석")
        add(bool(re.search(r"수익성.{0,12}(분석|검토)|용역", text)), "수익성 분석 용역")
        add(bool(re.search(r"지역\s*주민.{0,20}(나눠|분배|공유)", text)), "지역 주민 개발이익 공유")
        add(bool(re.search(r"환경친화적|지속가능한\s*시민의\s*연금", text)), "환경친화적이고 지속가능한 시민 연금")

        return self._dedupe_execution_items(facts)

    def _extract_source_sequence_items_from_stance(self, stance_text: str) -> List[str]:
        text = normalize_context_text(stance_text)
        compact = re.sub(r"\s+", "", text)
        if not compact:
            return []

        items: List[str] = []

        def add(condition: bool, item: str) -> None:
            if condition:
                items.append(item)

        add("햇빛지도" in compact or bool(re.search(r"일조량.{0,12}(분석|조사)", text)), "햇빛지도와 일조량 분석")
        add(bool(re.search(r"공영\s*주차장|공공기관\s*옥상|태양광\s*발전시설", text)), "태양광 발전시설 입지 검토")
        add(bool(re.search(r"수익성.{0,12}(분석|검토)|용역", text)), "입지·수익성 분석 용역")
        add(bool(re.search(r"예산.{0,12}(확보|편성|운용)", text)), "관련 예산 확보")
        add(bool(re.search(r"이익.{0,12}(주민|지역\s*주민).{0,20}(나눠|분배|공유)", text)), "개발이익 주민 공유")
        add(bool(re.search(r"이익\s*공유형\s*기본소득|이익공유형\s*기본소득", text)), "이익공유형 기본소득 모델")
        add(bool(re.search(r"조례.{0,12}(제정|개정|정비)", text)), "조례 제정·정비")
        district_match = re.search(r"((?:[가-힣]{2,12}구)|(?:\{region\}))부터.{0,20}(점진|시범|먼저|추진)", text)
        if district_match:
            add(True, f"{district_match.group(1)}부터 점진 추진")
        return self._dedupe_execution_items(items)

    def _build_forbidden_inferred_actions(self, stance_text: str) -> List[str]:
        text = normalize_context_text(stance_text)
        compact = re.sub(r"\s+", "", text)
        candidates = [
            ("10%", ("10%", "10퍼센트")),
            ("수수료 전액 지원", ("수수료전액지원",)),
            ("전담 TF", ("전담tf", "태스크포스")),
            ("정기 간담회", ("정기간담회",)),
            ("맞춤형 프로모션", ("맞춤형프로모션", "프로모션")),
            ("모바일 결제 시스템 고도화", ("모바일결제시스템", "결제시스템고도화")),
            ("온라인 플랫폼 확대", ("온라인플랫폼",)),
            ("예산 확보", ("예산확보", "예산편성")),
            ("10만", ("10만",)),
            ("AI", ("ai",)),
            ("인공지능", ("인공지능",)),
            ("로봇", ("로봇",)),
            ("노동의 종말", ("노동의종말",)),
            ("다니엘 라벤토스", ("다니엘라벤토스", "라벤토스")),
            ("선별복지", ("선별복지",)),
            ("조세 저항", ("조세저항",)),
            ("낙수효과", ("낙수효과",)),
            ("지역화폐형 기본소득", ("지역화폐형기본소득",)),
        ]
        for year in range(2020, 2031):
            candidates.append((f"{year}년", (f"{year}년", str(year))))
        forbidden: List[str] = []
        lowered_compact = compact.lower()
        for label, probes in candidates:
            if not any(str(probe).lower() in lowered_compact for probe in probes):
                forbidden.append(label)
        return forbidden

    def _looks_like_implementation_plan_stance(self, stance_text: str, execution_items: List[str]) -> bool:
        text = normalize_context_text(stance_text)
        if not text:
            return False
        plan_markers = re.search(r"부활|복원|회복|되찾|재정비|개정|마련|모색|활성화|방안|해법", text)
        policy_markers = re.search(r"정책|지역화폐|사업|제도|조례|지원책|캐시백|담당\s*부서", text)
        return bool(plan_markers and (policy_markers or execution_items))

    def _build_source_contract(
        self,
        analysis: Dict[str, Any],
        *,
        stance_text: str = "",
        answer_type: str = "",
        execution_items: Optional[List[str]] = None,
        central_claim: str = "",
    ) -> Dict[str, Any]:
        existing = analysis.get("source_contract")
        contract: Dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}

        primary_policy = normalize_context_text(contract.get("primary_keyword")) or self._extract_primary_policy_surface(stance_text)
        extracted_items = self._extract_execution_items_from_stance(stance_text, primary_policy=primary_policy)
        merged_items = self._dedupe_execution_items(list(execution_items or []) + extracted_items)
        required_facts = self._dedupe_execution_items(
            self._coerce_execution_item_list(contract.get("required_source_facts"))
            + self._extract_required_source_facts_from_stance(stance_text)
        )
        source_sequence_items = self._dedupe_execution_items(
            self._coerce_execution_item_list(contract.get("source_sequence_items"))
            + self._extract_source_sequence_items_from_stance(stance_text)
        )

        normalized_answer_type = self._normalize_answer_type(contract.get("answer_type") or answer_type)
        if normalized_answer_type in self._IMPLEMENTATION_PLAN_TYPES:
            normalized_answer_type = "implementation_plan"
        if normalized_answer_type != "implementation_plan" and self._looks_like_implementation_plan_stance(
            stance_text,
            merged_items,
        ):
            normalized_answer_type = "implementation_plan"

        if normalized_answer_type != "implementation_plan" and not (merged_items or required_facts):
            return {}

        if not central_claim and primary_policy and normalized_answer_type == "implementation_plan":
            central_claim = f"{primary_policy} 부활 방안을 마련하겠다"

        contract.update(
            {
                "answer_type": normalized_answer_type,
                "primary_keyword": primary_policy,
                "central_claim": self._sanitize_context_material_text(
                    contract.get("central_claim") or central_claim
                ),
                "required_source_facts": required_facts,
                "execution_items": merged_items,
                "source_sequence_items": source_sequence_items,
                "forbidden_inferred_actions": self._dedupe_contract_labels(
                    self._coerce_execution_item_list(contract.get("forbidden_inferred_actions"))
                    + self._build_forbidden_inferred_actions(stance_text),
                    max_items=32,
                ),
            }
        )
        return contract

    def _normalize_source_contract(self, value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        contract = dict(value)
        contract["answer_type"] = self._normalize_answer_type(contract.get("answer_type"))
        if contract["answer_type"] in self._IMPLEMENTATION_PLAN_TYPES:
            contract["answer_type"] = "implementation_plan"
        contract["primary_keyword"] = self._sanitize_context_material_text(contract.get("primary_keyword"))
        contract["central_claim"] = self._sanitize_context_material_text(contract.get("central_claim"))
        for key in ("required_source_facts", "execution_items", "source_sequence_items"):
            contract[key] = self._dedupe_execution_items(self._coerce_execution_item_list(contract.get(key)))
        contract["forbidden_inferred_actions"] = self._dedupe_contract_labels(
            self._coerce_execution_item_list(contract.get("forbidden_inferred_actions")),
            max_items=32,
        )
        return contract

    def _augment_execution_plan(self, analysis: Dict[str, Any], *, stance_text: str = "") -> Dict[str, Any]:
        normalized = dict(analysis) if isinstance(analysis, dict) else {}
        answer_type = self._normalize_answer_type(normalized.get("answer_type"))
        execution_items = self._dedupe_execution_items(
            self._coerce_execution_item_list(normalized.get("execution_items"))
        )
        central_claim = self._sanitize_context_material_text(normalized.get("central_claim"))

        source_contract = self._build_source_contract(
            normalized,
            stance_text=stance_text,
            answer_type=answer_type,
            execution_items=execution_items,
            central_claim=central_claim,
        )
        if source_contract:
            normalized["source_contract"] = source_contract
            if source_contract.get("answer_type") == "implementation_plan":
                answer_type = "implementation_plan"
            if not execution_items:
                execution_items = list(source_contract.get("execution_items") or [])
            if not central_claim:
                central_claim = self._sanitize_context_material_text(source_contract.get("central_claim"))

        if answer_type in self._IMPLEMENTATION_PLAN_TYPES:
            answer_type = "implementation_plan"

        if answer_type == "implementation_plan":
            content_strategy = normalized.get("contentStrategy")
            if not isinstance(content_strategy, dict):
                content_strategy = {}
            content_strategy.setdefault("structure", "문제 원인 → 실행 항목 → 제도화와 효과 확인")
            emphasis = content_strategy.get("emphasis")
            if not isinstance(emphasis, list):
                emphasis = []
            for item in ("구체 실행 항목", "제도화", "효과 확인"):
                if item not in emphasis:
                    emphasis.append(item)
            content_strategy["emphasis"] = emphasis[:6]
            normalized["contentStrategy"] = content_strategy

        normalized["answer_type"] = answer_type or ""
        normalized["execution_items"] = execution_items
        normalized["central_claim"] = central_claim
        return normalized

    def _extract_news_fact_candidates(self, news_text: str, *, max_items: int = 6) -> List[str]:
        source = normalize_context_text(news_text, sep="\n")
        if not source:
            return []

        fact_keywords = (
            "디즈니랜드",
            "다대포",
            "감천동",
            "다대동",
            "힐튼",
            "메리어트",
            "송도선",
            "자갈치역",
            "감천문화마을",
            "구평동",
            "장림동",
            "코스피",
            "5800",
            "5806.6",
            "사상 최고치",
            "신규 일자리",
            "연 5조",
        )
        lines = re.split(r"[\r\n]+|(?<=[.!?。])\s+", source)
        candidates: List[str] = []
        seen: set[str] = set()

        for raw_line in lines:
            item = self._sanitize_context_material_text(raw_line)
            if len(strip_html(item)) < 14:
                continue
            if self._is_noisy_news_material(item):
                continue

            has_number = bool(re.search(r"\d", item))
            keyword_hits = sum(1 for keyword in fact_keywords if keyword in item)
            if keyword_hits <= 0 and not has_number:
                continue
            if keyword_hits < 2 and not (has_number and keyword_hits >= 1):
                continue

            key = material_key(item)
            if not key or key in seen:
                continue
            seen.add(key)
            candidates.append(item)
            if len(candidates) >= max_items:
                break

        return candidates

    def _augment_context_analysis_with_news_facts(
        self,
        context_analysis: Optional[Dict[str, Any]],
        news_text: str,
    ) -> Dict[str, Any]:
        analysis = dict(context_analysis) if isinstance(context_analysis, dict) else {}

        normalized_facts: List[str] = []
        seen: set[str] = set()
        raw_facts = analysis.get("mustIncludeFacts")
        if isinstance(raw_facts, list):
            for raw in raw_facts:
                text = self._sanitize_context_material_text(raw)
                if len(strip_html(text)) < 8:
                    continue
                if self._is_noisy_news_material(text):
                    continue
                key = material_key(text)
                if not key or key in seen:
                    continue
                seen.add(key)
                normalized_facts.append(text)
                if len(normalized_facts) >= 8:
                    break

        fallback_facts = self._extract_news_fact_candidates(news_text, max_items=6)
        for fact in fallback_facts:
            key = material_key(fact)
            if not key or key in seen:
                continue
            seen.add(key)
            normalized_facts.append(fact)
            if len(normalized_facts) >= 8:
                break

        analysis["mustIncludeFacts"] = normalized_facts
        if not isinstance(analysis.get("newsQuotes"), list):
            analysis["newsQuotes"] = []
        if not isinstance(analysis.get("mustIncludeFromStance"), list):
            analysis["mustIncludeFromStance"] = []
        return analysis

    def normalize_materials(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(analysis, dict):
            return {}

        normalized_analysis = dict(analysis)

        stance_items: List[Dict[str, str]] = []
        stance_seen: set[str] = set()
        raw_stance = normalized_analysis.get("mustIncludeFromStance")
        if isinstance(raw_stance, list):
            for item in raw_stance:
                if isinstance(item, dict):
                    topic = self._sanitize_context_material_text(item.get("topic"))
                    why_txt = self._sanitize_context_material_text(item.get("expansion_why"))
                    how_txt = self._sanitize_context_material_text(item.get("expansion_how"))
                    effect_txt = self._sanitize_context_material_text(item.get("expansion_effect"))
                else:
                    topic = self._sanitize_context_material_text(item)
                    why_txt = ""
                    how_txt = ""
                    effect_txt = ""

                if len(strip_html(topic)) < 5:
                    continue
                if self._is_noisy_stance_material(topic):
                    continue

                key = material_key(topic)
                if not key or key in stance_seen:
                    continue
                stance_seen.add(key)
                stance_items.append(
                    {
                        "topic": topic,
                        "expansion_why": why_txt,
                        "expansion_how": how_txt,
                        "expansion_effect": effect_txt,
                    }
                )
                if len(stance_items) >= 6:
                    break

        normalized_analysis["mustIncludeFromStance"] = stance_items

        def dedupe_text_list(
            raw_values: Any,
            *,
            blocked_keys: Optional[set[str]] = None,
            max_items: int = 8,
            filter_news_noise: bool = False,
        ) -> Tuple[List[str], set[str]]:
            blocked = blocked_keys or set()
            results: List[str] = []
            keys: set[str] = set()
            if not isinstance(raw_values, list):
                return results, keys

            for raw in raw_values:
                text = self._sanitize_context_material_text(raw)
                if len(strip_html(text)) < 8:
                    continue
                if filter_news_noise and self._is_noisy_news_material(text):
                    continue
                key = material_key(text)
                if not key or key in blocked or key in keys:
                    continue
                keys.add(key)
                results.append(text)
                if len(results) >= max_items:
                    break
            return results, keys

        stance_keys = {material_key(item.get("topic")) for item in stance_items if isinstance(item, dict)}
        stance_keys.discard("")

        facts, fact_keys = dedupe_text_list(
            normalized_analysis.get("mustIncludeFacts"),
            blocked_keys=stance_keys,
            max_items=8,
            filter_news_noise=True,
        )
        normalized_analysis["mustIncludeFacts"] = facts

        quotes, _quote_keys = dedupe_text_list(
            normalized_analysis.get("newsQuotes"),
            blocked_keys=stance_keys.union(fact_keys),
            max_items=8,
            filter_news_noise=True,
        )
        normalized_analysis["newsQuotes"] = quotes

        normalized_analysis["answer_type"] = self._normalize_answer_type(
            normalized_analysis.get("answer_type")
        )
        normalized_analysis["central_claim"] = self._sanitize_context_material_text(
            normalized_analysis.get("central_claim")
        )
        normalized_analysis["execution_items"] = self._dedupe_execution_items(
            self._coerce_execution_item_list(normalized_analysis.get("execution_items"))
        )
        normalized_analysis["source_contract"] = self._normalize_source_contract(
            normalized_analysis.get("source_contract")
        )

        return normalized_analysis

    @staticmethod
    def _render_speaker_profile_xml(
        *,
        full_name: str,
        position_label: str,
        region_metro: str,
        region_local: str,
        electoral_district: str,
    ) -> str:
        """LLM 에 화자 직책 앵커를 주입하는 <speaker_profile> XML 블록.

        TitleAgent 의 동등 헬퍼와 같은 표기를 공유한다 — stance_text 안에
        등장하는 다른 정치인의 직책을 화자에게 귀속시키지 못하도록 하는 게
        목적. 빈 필드는 출력에서 생략한다.
        """
        name = (full_name or "").strip()
        position = (position_label or "").strip()
        metro = (region_metro or "").strip()
        local = (region_local or "").strip()
        district = (electoral_district or "").strip()
        if not (name or position or metro or local or district):
            return ""

        lines = []
        if name:
            lines.append(f"  <full_name>{_xml_text(name)}</full_name>")
        if position:
            lines.append(f"  <position>{_xml_text(position)}</position>")
        if metro:
            lines.append(f"  <region_metro>{_xml_text(metro)}</region_metro>")
        if local:
            lines.append(f"  <region_local>{_xml_text(local)}</region_local>")
        if district:
            lines.append(f"  <electoral_district>{_xml_text(district)}</electoral_district>")
        lines.append(
            "  <rule>이 글의 화자는 위 인물이며, 위 직책의 시점에서 분석한다. "
            "stance_text 에 다른 정치인이 등장해도 그 사람은 화자가 아니다. "
            "화자의 직책·역할을 그 사람의 직책으로 바꿔 추출하지 말 것.</rule>"
        )
        body = "\n".join(lines)
        return f'<speaker_profile priority="critical">\n{body}\n  </speaker_profile>'

    async def analyze(
        self,
        stance_text: str,
        news_data_text: str,
        author_name: str,
        speaker_profile: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        from ..common.gemini_client import generate_content_async
        from ..common.profile_label import resolve_speaker_position_label

        stance_len = len(strip_html(stance_text or ""))
        news_len = len(strip_html(news_data_text or ""))
        if stance_len < 50 and news_len < 80:
            print(
                f"⚠️ [ContextAnalyzer] 입장문/뉴스 모두 짧음 "
                f"(stance={stance_len}자, news={news_len}자) - 분석 스킵"
            )
            return None

        print(
            f"🔍 [ContextAnalyzer] 실행... (입장문: {len(stance_text)}자, 뉴스: {len(news_data_text)}자)"
        )
        start_time = time.time()

        news_preview = (news_data_text or "")[:4000] if news_data_text else "(없음)"
        context_json_example = """{
  "intent": "policy_promotion",
  "answer_type": "implementation_plan",
  "central_claim": "핵심 정책을 되살리는 실행 방안을 마련하겠다",
  "execution_items": [
    "후퇴한 지원책 복원",
    "전담 추진체계 재정비",
    "효과 분석과 조례 개정"
  ],
  "contentStrategy": {
    "tone": "논리적 설득",
    "structure": "문제 제기 → 실행 전략 → 기대 효과",
    "emphasis": ["실행 가능성", "지역경제 효과"]
  },
  "mustIncludeFromStance": [
    {
      "topic": "핵심 주장 1",
      "expansion_why": "배경",
      "expansion_how": "실행",
      "expansion_effect": "효과"
    }
  ],
  "mustIncludeFacts": [
    "감천동·다대동 일대 특급 호텔 유치",
    "송도선 도시철도 유치로 접근성 개선",
    "코스피 5800 돌파"
  ],
  "newsQuotes": [],
  "mustPreserve": {
    "bankName": null,
    "accountNumber": null,
    "accountHolder": null,
    "contactNumber": null,
    "instruction": null,
    "eventDate": null,
    "eventLocation": null,
    "ctaPhrase": null
  }
}"""

        speaker_profile_dict = speaker_profile if isinstance(speaker_profile, dict) else {}
        speaker_position_label = resolve_speaker_position_label(speaker_profile_dict)
        speaker_region_metro = str(speaker_profile_dict.get("regionMetro") or "").strip()
        speaker_region_local = str(speaker_profile_dict.get("regionLocal") or "").strip()
        speaker_electoral_district = str(speaker_profile_dict.get("electoralDistrict") or "").strip()
        speaker_profile_xml = self._render_speaker_profile_xml(
            full_name=author_name,
            position_label=speaker_position_label,
            region_metro=speaker_region_metro,
            region_local=speaker_region_local,
            electoral_district=speaker_electoral_district,
        )

        context_prompt = f"""
<context_analyzer_prompt version="xml-v1">
  <role>정치 콘텐츠 전략가로서 입장문과 뉴스/데이터를 분리 분석해 실행 가능한 글쓰기 설계를 만듭니다.</role>
  <inputs>
    {speaker_profile_xml}
    <stance_text>{_xml_cdata(stance_text[:3000])}</stance_text>
    <news_or_data>{_xml_cdata(news_preview)}</news_or_data>
    <author_name>{_xml_text(author_name)}</author_name>
  </inputs>
  <analysis_tasks>
    <intent_selection>
      <description>의도 하나만 선택</description>
      <option key="donation_request">후원 요청</option>
      <option key="policy_promotion">정책/비전 홍보</option>
      <option key="event_announcement">일정/행사 안내</option>
      <option key="activity_report">활동 보고</option>
      <option key="personal_message">개인 소통/인사</option>
    </intent_selection>
    <content_strategy>
      <field name="tone">톤앤매너</field>
      <field name="structure">전개 구조</field>
      <field name="emphasis">강조 포인트 리스트</field>
    </content_strategy>
    <answer_shape critical="true">
      <field name="answer_type">implementation_plan | policy_defense | value_statement | activity_report 중 하나</field>
      <rule>입장문이 "부활 방안", "복원", "회복", "개정", "마련", "모색"을 말하면 implementation_plan으로 분류.</rule>
      <field name="central_claim">글 전체가 답해야 할 한 문장</field>
      <field name="execution_items">실행 항목 리스트. 문제 원인은 반대로 뒤집어 실행 항목으로 추출.</field>
      <example>캐시백 요율을 줄였다 → 캐시백 요율 회복</example>
      <example>담당 부서를 축소했다 → 전담 추진체계 재정비</example>
    </answer_shape>
    <must_include_from_stance max_items="3">
      <rule>반드시 stance_text에서만 추출하고 news_or_data 문구를 topic에 넣지 말 것.</rule>
      <rule>핵심 주장/문제의식만 추출하고 기사 메타 문구(입력, 기자명, 연합뉴스)는 배제.</rule>
      <rule>화자(speaker_profile.full_name)가 아닌 다른 정치인이 stance_text에 등장하면 그 사람을 central_claim의 주어나 execution_items의 행위자로 삼지 말 것. 화자가 그 사람과 함께 활동한다는 사실은 추출 가능하지만, 화자의 직책을 그 사람의 직책으로 바꿔 적지 말 것.</rule>
      <field name="topic">핵심 주장</field>
      <field name="expansion_why">배경</field>
      <field name="expansion_how">실행</field>
      <field name="expansion_effect">효과</field>
    </must_include_from_stance>
    <must_include_facts max_items="6">
      <rule>news_or_data에서 검증 가능한 사실/수치만 추출.</rule>
      <rule>정책 실행 포인트(시설·교통·경제지표)를 우선.</rule>
      <rule>문장 단편이 아닌 완결된 사실 문장으로 작성.</rule>
      <field name="fact">핵심 사실 1개</field>
    </must_include_facts>
    <news_quotes max_items="3">
      <rule>따옴표 발언이 있을 때만 포함.</rule>
      <field name="quote">직접 인용문</field>
    </news_quotes>
    <must_preserve critical="true">
      <field name="bankName">은행명 (없으면 null)</field>
      <field name="accountNumber">계좌번호 (없으면 null)</field>
      <field name="accountHolder">예금주 (없으면 null)</field>
      <field name="contactNumber">연락처 (없으면 null)</field>
      <field name="instruction">안내 문구 (없으면 null)</field>
      <field name="eventDate">일시 (없으면 null)</field>
      <field name="eventLocation">장소 (없으면 null)</field>
      <field name="ctaPhrase">CTA 문구 (없으면 null)</field>
    </must_preserve>
  </analysis_tasks>
  <output_contract>
    <format>JSON only</format>
    <rules>
      <rule order="1">반드시 JSON 객체 하나만 출력</rule>
      <rule order="2">코드블록, XML, 부가 설명문 출력 금지</rule>
      <rule order="3">키 누락 시 null 또는 빈 배열 사용</rule>
    </rules>
    <json_example>{_xml_cdata(context_json_example)}</json_example>
  </output_contract>
</context_analyzer_prompt>
""".strip()

        try:
            response_text = await generate_content_async(
                context_prompt,
                model_name=self.model_name,
                temperature=0.0,
                response_mime_type="application/json",
            )
            analysis = json.loads(response_text)

            if "mustIncludeFromStance" in analysis and isinstance(analysis["mustIncludeFromStance"], list):
                filtered_list = []
                for item in analysis["mustIncludeFromStance"]:
                    if isinstance(item, str) and len(item.strip()) >= 5:
                        filtered_list.append(
                            {
                                "topic": item,
                                "expansion_why": "",
                                "expansion_how": "",
                                "expansion_effect": "",
                            }
                        )
                    elif isinstance(item, dict) and item.get("topic"):
                        topic = str(item.get("topic") or "").strip()
                        if len(topic) >= 2 and not topic.startswith("⚠️"):
                            filtered_list.append(item)
                analysis["mustIncludeFromStance"] = filtered_list

            analysis = self._augment_execution_plan(analysis, stance_text=stance_text)
            analysis = self._augment_context_analysis_with_news_facts(analysis, news_data_text)
            analysis = self.normalize_materials(analysis)

            elapsed = time.time() - start_time
            print(
                f"✅ [ContextAnalyzer] 완료 ({elapsed:.1f}초) "
                f"stance={len(analysis.get('mustIncludeFromStance') or [])}, "
                f"facts={len(analysis.get('mustIncludeFacts') or [])}, "
                f"quotes={len(analysis.get('newsQuotes') or [])}"
            )
            return analysis
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"⚠️ [ContextAnalyzer] 실패 ({elapsed:.1f}초): {str(e)} - 건너뜀")
            return None
