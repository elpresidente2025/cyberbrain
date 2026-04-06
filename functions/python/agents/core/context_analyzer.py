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

        return normalized_analysis

    async def analyze(self, stance_text: str, news_data_text: str, author_name: str) -> Optional[Dict[str, Any]]:
        from ..common.gemini_client import generate_content_async

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

        context_prompt = f"""
<context_analyzer_prompt version="xml-v1">
  <role>정치 콘텐츠 전략가로서 입장문과 뉴스/데이터를 분리 분석해 실행 가능한 글쓰기 설계를 만듭니다.</role>
  <inputs>
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
    <must_include_from_stance max_items="3">
      <rule>반드시 stance_text에서만 추출하고 news_or_data 문구를 topic에 넣지 말 것.</rule>
      <rule>핵심 주장/문제의식만 추출하고 기사 메타 문구(입력, 기자명, 연합뉴스)는 배제.</rule>
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
