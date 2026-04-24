"""LLM 프롬프트에 주입할 화자 정체성 XML 블록 생성 helper.

StructureAgent 의 7 개 글쓰기 템플릿(activity_report, policy_proposal,
daily_communication, current_affairs(critical/diagnostic), local_issues,
bipartisan_cooperation, offline_engagement) 이 모두 같은 블록을 공유하도록
단일 진실로 둔다.

블록의 목적:
  1. 화자가 누구인지 LLM 에 구조화된 앵커로 명시 (full_name·position·region).
  2. 1인칭 시점, 본인 이름 사용 제한, 타인은 3인칭 같은 일반 룰을 일관 적용.
  3. 같은 지역 다른 직책 후보(러닝메이트) 가 stanceText 에 등장해도 그
     사람의 직책으로 본인을 묘사하지 못하게 하는 ally 룰 (Phase 1·2 의
     TitleAgent / ContextAnalyzer 룰과 짝꿍).

position 라벨은 agents/common/profile_label.resolve_speaker_position_label
로 만든다 — TitleAgent / ContextAnalyzer 와 같은 표기 규칙을 공유한다.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .profile_label import resolve_speaker_position_label


def build_speaker_identity_xml(
    *,
    full_name: str,
    author_bio: str,
    user_profile: Optional[Dict[str, Any]] = None,
) -> str:
    """화자 정체성 XML 블록을 만든다. 빈 필드는 출력에서 생략.

    핵심 요구: position·region 구조화 필드 + ally 룰. 이 두 가지가 없으면
    LLM 은 stanceText 안에 더 빈도 높은 다른 정치인의 직책을 화자에게
    잘못 귀속시킨다 (조사 보고서 가설 1 의 결함).
    """
    profile = user_profile if isinstance(user_profile, dict) else {}
    name = (full_name or "").strip()
    bio = (author_bio or "").strip()
    position = resolve_speaker_position_label(profile)
    region_metro = str(profile.get("regionMetro") or "").strip()
    region_local = str(profile.get("regionLocal") or "").strip()
    electoral_district = str(profile.get("electoralDistrict") or "").strip()

    if not (name or bio or position or region_metro or region_local or electoral_district):
        return ""

    field_lines = []
    if name:
        field_lines.append(f"  <full_name>{name}</full_name>")
    if position:
        field_lines.append(f"  <position>{position}</position>")
    if region_metro:
        field_lines.append(f"  <region_metro>{region_metro}</region_metro>")
    if region_local:
        field_lines.append(f"  <region_local>{region_local}</region_local>")
    if electoral_district:
        field_lines.append(f"  <electoral_district>{electoral_district}</electoral_district>")
    if bio:
        field_lines.append(f"  <bio>{bio}</bio>")

    name_token = name or "(이름 미상)"
    rule_lines = [
        f'  <declaration>당신은 위 인물이며 이 글의 유일한 1인칭 화자입니다.</declaration>',
        f'  <rule id="first_person">이 글은 철저히 1인칭으로 작성합니다. "저는", "제가"를 사용하세요.</rule>',
        f'  <rule id="name_usage_limit">본인 이름("{name_token}")은 서론에서 1회, 결론에서 1회만 사용하세요. 본문에서는 "저는", "제가", "본 의원은" 등 대명사를 사용하세요.</rule>',
        '  <rule id="others_third_person" priority="critical">참고 자료에 등장하는 다른 정치인은 관찰·평가 대상(3인칭)입니다. 절대 다른 정치인의 입장에서 공약을 내거나 다짐하지 마세요. 칭찬할 대상이 있으면 "같은 팀 동행 후보로서 훌륭하다", "경쟁자이지만 이 점은 인정한다"처럼 화자와의 관계를 명시하세요.</rule>',
        '  <rule id="ally_role_anchor" priority="critical">stanceText·참고 자료에 같은 지역의 다른 직책 후보(러닝메이트) 가 등장해도 그 사람의 직책으로 본인을 묘사하지 마세요. 본인 직책은 위 <position> 이며, 그 사람과 함께 활동하는 사실은 적을 수 있으나 본인 직책을 그 사람의 직책으로 바꿔 적지 마세요.</rule>',
        '  <rule id="own_election_specificity" priority="critical">화자 본인의 선거를 언급할 때는 반드시 직책 기반 선거 유형을 명시하세요. 예: "시의원 선거", "구의원 선거", "도지사 선거". 같은 문단에 다른 사람의 선거(경선 포함)가 언급된 경우 특히 의무입니다.</rule>',
    ]

    body = "\n".join(field_lines + rule_lines)
    return (
        '<speaker_identity priority="critical" description="화자 정체성 - 절대 혼동 금지">\n'
        f"{body}\n"
        "</speaker_identity>"
    )


__all__ = ["build_speaker_identity_xml"]
