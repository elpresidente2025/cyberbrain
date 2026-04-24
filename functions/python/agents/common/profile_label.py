"""사용자 프로필을 읽어 LLM 프롬프트에 주입할 화자 직책 라벨을 만드는 helper.

`position` 은 Firestore 저장 시 `_canonical_position` 으로
국회의원 / 광역의원 / 기초의원 / 광역자치단체장 / 기초자치단체장
중 하나로 정규화돼 있다. 이 함수는 그 정규화 라벨에 region 을 합쳐
LLM 이 자연스럽게 읽는 직함 한 줄을 만든다 (예: "인천광역시의원").

TitleAgent / ContextAnalyzer / StructureAgent 가 같은 라벨 표기를
공유하도록 하나의 함수에 단일 진실로 둔다.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def format_position_with_region(user_profile: Optional[Dict[str, Any]]) -> str:
    """canonical position + region 을 합친 표시용 직함 라벨.

    - 광역의원 + regionMetro → "{regionMetro}의원"
    - 기초의원 + regionLocal → "{regionLocal}의원" (없으면 regionMetro)
    - 광역자치단체장 + regionMetro → "{regionMetro}장"
    - 기초자치단체장 + regionLocal → "{regionLocal}장"
    - 그 외 (국회의원 등) → position 원본 그대로

    region 이 비어 있으면 position 원본을 반환한다.
    """
    if not isinstance(user_profile, dict):
        return ""
    position = (user_profile.get("position") or "").strip()
    region_metro = (user_profile.get("regionMetro") or "").strip()
    region_local = (user_profile.get("regionLocal") or "").strip()

    if position == "광역의원" and region_metro:
        return f"{region_metro}의원"
    if position == "기초의원":
        if region_local:
            return f"{region_local}의원"
        if region_metro:
            return f"{region_metro}의원"
    if position == "광역자치단체장" and region_metro:
        return f"{region_metro}장"
    if position == "기초자치단체장" and region_local:
        return f"{region_local}장"

    return position


def resolve_speaker_position_label(user_profile: Optional[Dict[str, Any]]) -> str:
    """사용자가 customTitle 을 명시했으면 그것을 우선 사용하고,
    아니면 format_position_with_region 으로 fallback.

    customTitle 은 사용자가 직접 적은 자기 직함이므로
    canonical position 보다 사용자 의도를 더 정확히 반영한다.
    """
    if not isinstance(user_profile, dict):
        return ""
    custom = (user_profile.get("customTitle") or "").strip()
    if custom:
        return custom
    return format_position_with_region(user_profile)


__all__ = [
    "format_position_with_region",
    "resolve_speaker_position_label",
]
