from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RoleGovernance:
    role: str
    role_label: str
    authority_scope: List[str]
    voice_and_manner: List[str]
    preferred_frames: List[str]
    forbidden_direct_claims: List[str]
    forbidden_tone: List[str]
    rewrite_rules: List[Dict[str, str]]


ROLE_GOVERNANCE: Dict[str, RoleGovernance] = {
    "기초의원": RoleGovernance(
        role="기초의원",
        role_label="구의원/군의원/기초의원",
        authority_scope=[
            "조례 제정·개정 제안",
            "예산 심의와 우선순위 조정",
            "행정사무감사와 구청·군청 집행부 견제",
            "자료 요구, 상임위 질의, 5분 자유발언",
            "시·구·군·관계기관 협의 촉구",
            "생활밀착형 시범사업 제안",
            "공공시설 운영 개선",
            "취약계층 지원 조례와 지역 복지 사업 개선",
        ],
        voice_and_manner=[
            "주민 생활 가까이에서 말한다.",
            "거대 담론보다 생활 문제와 제도 개선을 연결한다.",
            "직접 집행보다 감시·제안·조례·예산 심의로 표현한다.",
            "낮은 자세와 실무적 어조를 유지한다.",
        ],
        preferred_frames=[
            "조례로 검토하겠습니다",
            "예산 심의에서 따지겠습니다",
            "구청 집행부에 개선을 요구하겠습니다",
            "관계기관 협의를 촉구하겠습니다",
            "생활밀착형 시범사업으로 시작하겠습니다",
        ],
        forbidden_direct_claims=[
            "국가 제도를 직접 도입하겠습니다",
            "전국 단위 기본소득을 시행하겠습니다",
            "증세 합의를 이끌겠습니다",
            "조세 구조를 바꾸겠습니다",
            "국가 재정을 재편하겠습니다",
            "전국적 복지 체계를 개편하겠습니다",
            "중앙정부와 헌법적 권한을 다투겠습니다",
            "전면 무상복지를 시행하겠습니다",
        ],
        forbidden_tone=[
            "국가 개조형",
            "중앙정부 대체형",
            "전국 제도 설계자형",
            "국회 입법자형",
        ],
        rewrite_rules=[
            {
                "source_pattern": "기본소득, 기본소득제, BI, 보편 지급, 전 국민 지급",
                "target_frame": "생활비 부담을 줄이는 지역형 지원 조례 검토",
            },
            {
                "source_pattern": "증세, 조세 합의, 조세 구조 개편",
                "target_frame": "예산 우선순위 조정과 불필요한 지출 점검",
            },
            {
                "source_pattern": "국가 복지 확대, 전국 복지체계 개편",
                "target_frame": "구민에게 직접 닿는 생활 복지 사업 개선",
            },
            {
                "source_pattern": "전면 시행, 전국 시행, 전면 무상복지",
                "target_frame": "시범사업, 조례, 예산 심의, 관계기관 협의",
            },
            {
                "source_pattern": "중앙정부 권한, 헌법적 권한 다툼",
                "target_frame": "구의회가 할 수 있는 감시·제안·조례 발의",
            },
        ],
    ),

    "광역의원": RoleGovernance(
        role="광역의원",
        role_label="시의원/도의원/광역의원",
        authority_scope=[
            "광역 조례 제정·개정",
            "시·도 예산 심의",
            "시·도 산하기관 견제",
            "상임위 질의와 행정사무감사",
            "교통·복지·교육·환경 등 광역 사무 점검",
            "시·군·구 간 정책 조정 촉구",
        ],
        voice_and_manner=[
            "기초 현장과 광역 정책을 연결하는 조정자처럼 말한다.",
            "시·도 예산과 산하기관 운영을 감시하는 어조를 사용한다.",
            "지역 간 균형과 광역 단위 실행 가능성을 함께 본다.",
        ],
        preferred_frames=[
            "광역 조례로 뒷받침하겠습니다",
            "시·도 예산 심의에서 따지겠습니다",
            "산하기관 운영을 점검하겠습니다",
            "시·군·구 협의를 이끌겠습니다",
            "광역 차원의 개선안을 제안하겠습니다",
        ],
        forbidden_direct_claims=[
            "국세 체계를 바꾸겠습니다",
            "국가 재정을 재편하겠습니다",
            "전국 복지 체계를 직접 개편하겠습니다",
            "중앙정부 정책을 단독으로 시행하겠습니다",
        ],
        forbidden_tone=[
            "국회 입법자형",
            "중앙정부 대체형",
            "기초 민원만 다루는 축소형",
        ],
        rewrite_rules=[
            {
                "source_pattern": "국가 복지 확대, 전국 복지체계",
                "target_frame": "광역 복지 예산과 전달체계 개선",
            },
            {
                "source_pattern": "전국 시행, 전국 도입",
                "target_frame": "광역 단위 시범사업과 시·군·구 협의",
            },
            {
                "source_pattern": "조세 구조 개편, 국가 재정 재편",
                "target_frame": "시·도 예산 배분과 재정 운용 점검",
            },
        ],
    ),

    "국회의원": RoleGovernance(
        role="국회의원",
        role_label="국회의원",
        authority_scope=[
            "법률 제정·개정",
            "국정감사",
            "국가 예산 심의",
            "조세·복지·산업 제도 논의",
            "중앙부처 견제",
            "전국 단위 제도 개선",
        ],
        voice_and_manner=[
            "국가 의제 책임자이자 입법자처럼 말한다.",
            "정책 방향과 법률·예산 수단을 함께 제시한다.",
            "지방 현안도 국가 제도와 예산의 언어로 연결한다.",
            "단정하되 출처 없는 성과·수치를 만들지 않는다.",
        ],
        preferred_frames=[
            "법안을 발의하겠습니다",
            "국정감사에서 따지겠습니다",
            "예산 심의로 바로잡겠습니다",
            "제도 개선을 추진하겠습니다",
            "정부에 책임을 묻겠습니다",
        ],
        forbidden_direct_claims=[
            "지방정부 사업을 제가 직접 집행하겠습니다",
            "구청 행정을 직접 운영하겠습니다",
            "시·도 산하기관을 직접 지휘하겠습니다",
        ],
        forbidden_tone=[
            "지방 단체장형 직접 집행 톤",
            "기초의회 민원 처리자형 축소 톤",
            "근거 없는 전국 성과 단정",
        ],
        rewrite_rules=[
            {
                "source_pattern": "구청 운영, 시정 직접 집행",
                "target_frame": "법률과 예산으로 지방정부 실행을 지원",
            },
            {
                "source_pattern": "지역 시설 직접 운영",
                "target_frame": "중앙정부·지방정부 협력 구조와 예산 지원",
            },
        ],
    ),

    "기초자치단체장": RoleGovernance(
        role="기초자치단체장",
        role_label="시장/군수/구청장",
        authority_scope=[
            "구정·시정·군정 운영",
            "지방정부 예산 편성",
            "행정 집행",
            "공공서비스 개선",
            "구·시·군 산하기관 운영",
            "생활 행정과 지역 인프라 관리",
        ],
        voice_and_manner=[
            "행정 책임자처럼 구체적 실행을 말한다.",
            "주민 불편을 행정 절차와 예산으로 해결하는 톤을 쓴다.",
            "의회와 협력하되 의회 권한을 본인이 행사하는 것처럼 쓰지 않는다.",
        ],
        preferred_frames=[
            "추진하겠습니다",
            "집행하겠습니다",
            "개선하겠습니다",
            "현장 점검하겠습니다",
            "예산에 반영하겠습니다",
            "행정 절차를 정비하겠습니다",
        ],
        forbidden_direct_claims=[
            "국세 구조를 바꾸겠습니다",
            "국가 재정을 재편하겠습니다",
            "법률을 직접 개정하겠습니다",
            "국정감사를 하겠습니다",
            "조례를 제가 발의하겠습니다",
        ],
        forbidden_tone=[
            "국회의원형 입법 톤",
            "의회 의원형 발의 톤",
            "중앙정부 대체형",
        ],
        rewrite_rules=[
            {
                "source_pattern": "법안 발의, 법률 개정",
                "target_frame": "정부와 국회에 제도 개선을 건의",
            },
            {
                "source_pattern": "조례 발의",
                "target_frame": "의회와 협의해 조례 제·개정을 추진",
            },
            {
                "source_pattern": "국가 재정 재편, 조세 구조 개편",
                "target_frame": "지방정부 재정 운용과 예산 우선순위 정비",
            },
        ],
    ),

    "광역자치단체장": RoleGovernance(
        role="광역자치단체장",
        role_label="시장/도지사",
        authority_scope=[
            "광역 행정 운영",
            "시·도 예산 편성",
            "광역 교통·산업·복지·환경 정책 집행",
            "시·군·구 협력 조정",
            "광역 산하기관 운영",
            "중앙정부와의 재정·정책 협의",
        ],
        voice_and_manner=[
            "광역 행정 책임자이자 조정자처럼 말한다.",
            "큰 비전을 말하되 실행 수단은 시·도 행정과 협의 구조로 연결한다.",
            "중앙정부와 협의·건의·공동 추진의 표현을 사용한다.",
        ],
        preferred_frames=[
            "광역 차원에서 추진하겠습니다",
            "시·군·구와 함께 조정하겠습니다",
            "중앙정부와 협의하겠습니다",
            "시·도 예산에 반영하겠습니다",
            "산하기관 운영을 정비하겠습니다",
        ],
        forbidden_direct_claims=[
            "국세 체계를 직접 바꾸겠습니다",
            "헌법적 권한을 직접 다투겠습니다",
            "국가 재정을 단독으로 재편하겠습니다",
            "국회 입법을 제가 직접 처리하겠습니다",
        ],
        forbidden_tone=[
            "국회 입법자형",
            "중앙정부 대체형",
            "기초 민원만 다루는 축소형",
        ],
        rewrite_rules=[
            {
                "source_pattern": "국가 재정 재편, 국세 체계 개편",
                "target_frame": "중앙정부와 재정 협의를 통해 광역 사업 재원을 확보",
            },
            {
                "source_pattern": "전국 제도 시행",
                "target_frame": "광역 단위 선도 모델로 추진",
            },
            {
                "source_pattern": "조세 구조 개편",
                "target_frame": "정부와 국회에 제도 개선을 건의",
            },
        ],
    ),
}


def _x(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _items(tag: str, values: List[str]) -> str:
    return "\n".join(f"    <{tag}>{_x(v)}</{tag}>" for v in values if v)


def get_role_governance(user_profile: Optional[Dict[str, Any]]) -> Optional[RoleGovernance]:
    if not isinstance(user_profile, dict):
        return None
    position = str(user_profile.get("position") or "").strip()
    return ROLE_GOVERNANCE.get(position)


_NON_INCUMBENT_KEYWORDS = ('예비', '후보', '준비')


def _is_non_incumbent(user_profile: Optional[Dict[str, Any]]) -> bool:
    status = str((user_profile or {}).get('status') or '').strip()
    return any(kw in status for kw in _NON_INCUMBENT_KEYWORDS)


def build_role_governance_xml(user_profile: Optional[Dict[str, Any]]) -> str:
    governance = get_role_governance(user_profile)
    if not governance:
        return ""

    non_incumbent = _is_non_incumbent(user_profile)

    rewrite_lines = "\n".join(
        f'    <rule>'
        f'<source_pattern>{_x(r.get("source_pattern", ""))}</source_pattern>'
        f'<target_frame>{_x(r.get("target_frame", ""))}</target_frame>'
        f'</rule>'
        for r in governance.rewrite_rules
    )

    return (
        f'<role_governance priority="critical" role="{_x(governance.role)}">\n'
        f'  <role_label>{_x(governance.role_label)}</role_label>\n'
        f'\n'
        f'  <authority_scope>\n'
        f'{_items("item", governance.authority_scope)}\n'
        f'  </authority_scope>\n'
        f'\n'
        f'  <voice_and_manner>\n'
        f'{_items("rule", governance.voice_and_manner)}\n'
        f'  </voice_and_manner>\n'
        f'\n'
        f'  <preferred_expression_frames>\n'
        f'{_items("frame", governance.preferred_frames)}\n'
        f'  </preferred_expression_frames>\n'
        f'\n'
        f'  <forbidden_direct_claims>\n'
        f'{_items("claim", governance.forbidden_direct_claims)}\n'
        f'  </forbidden_direct_claims>\n'
        f'\n'
        f'  <forbidden_tone>\n'
        f'{_items("tone", governance.forbidden_tone)}\n'
        f'  </forbidden_tone>\n'
        f'\n'
        f'  <rewrite_rules semantic="true">\n'
        f'    <instruction>아래 source_pattern은 정확히 같은 문자열만 뜻하지 않는다. '
        f'유사어, 축약어, 조사 변화, 동사 변화가 있어도 같은 정책 프레임이면 '
        f'target_frame의 권한 범위로 축소해 표현한다.</instruction>\n'
        f'{rewrite_lines}\n'
        f'  </rewrite_rules>\n'
        f'\n'
        f'  <final_check>\n'
        f'    <rule>본문을 작성한 뒤, 화자가 이 직책으로 직접 할 수 없는 일을 직접 시행 공약처럼 쓴 문장이 있으면 '
        f'반드시 authority_scope 안의 표현으로 고친다.</rule>\n'
        f'    <rule>중앙정부급 정책 사례는 참고 사례, 비교 사례, 재정 불가능론 반박, '
        f'지역형 축소 적용의 맥락에서만 사용한다.</rule>\n'
        + (
        f'    <rule>화자는 아직 당선 전(예비후보·후보·준비 상태) 신분이므로 과거 완료형 사실 표현을 일체 쓰지 않는다. '
        f'"발굴했습니다", "구현했습니다", "마쳤습니다", "확보했습니다", "합의했습니다", '
        f'"확정됐습니다", "끝냈습니다", "반영됐습니다" 등 모든 과거 완료형은 전면 금지한다. '
        f'반드시 미래·절차형으로 쓴다: "추진하겠습니다", "발굴하겠습니다", "마련하겠습니다", '
        f'"확보를 추진하겠습니다", "협의하겠습니다".</rule>\n'
        if non_incumbent else
        f'    <rule>근거 없는 완료형 사실 표현 금지: "확보했습니다", "합의했습니다", "확정됐습니다", '
        f'"끝냈습니다", "반영됐습니다"는 참고자료에 공식 문서·예산안·의결·협약·회의록·보도자료 등 '
        f'검증 가능한 근거가 있을 때만 사용한다.</rule>\n'
        f'    <rule>근거가 없으면 절차형 약속으로 쓴다: "확보를 추진하겠습니다", "협의하겠습니다", '
        f'"반영되도록 요구하겠습니다", "제출하겠습니다", "심의에서 챙기겠습니다".</rule>\n'
        ) +
        f'  </final_check>\n'
        f'</role_governance>'
    )


__all__ = [
    "RoleGovernance",
    "ROLE_GOVERNANCE",
    "get_role_governance",
    "build_role_governance_xml",
]
