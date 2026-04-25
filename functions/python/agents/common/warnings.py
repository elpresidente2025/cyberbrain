from typing import Any, Dict, Optional

from .role_governance import build_role_governance_xml


def _strip_warning_box_artifacts(text: str) -> str:
    """박스 문자(╔═╗║╚╝)로 구성된 장식 줄을 제거한다."""
    _BOX_CHARS = {"╔", "═", "╗", "║", "╚", "╝"}
    lines = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if set(stripped) <= (_BOX_CHARS | {" "}):
            continue
        if stripped.startswith("║") and stripped.endswith("║"):
            stripped = stripped.strip("║").strip()
        lines.append(stripped)
    return "\n".join(lines).strip()


def generate_role_warning_bundle(
    user_profile: Optional[Dict[str, Any]] = None,
    author_bio: str = "",
) -> str:
    """직책별 권한/톤 가드(role_governance) + 신분·시제 가드(non_lawmaker_warning)를 묶는다.

    role_governance는 모든 직책에 주입된다.
    non_lawmaker_warning은 국회의원 이외의 직책에서만 생성된다.
    """
    profile = user_profile if isinstance(user_profile, dict) else {}
    blocks = []

    role_governance_xml = build_role_governance_xml(profile)
    if role_governance_xml:
        blocks.append(role_governance_xml)

    non_lawmaker_text = generate_non_lawmaker_warning(
        profile.get("position"),
        profile.get("status"),
        profile.get("politicalExperience"),
        author_bio,
    )
    non_lawmaker_clean = _strip_warning_box_artifacts(non_lawmaker_text)
    if non_lawmaker_clean:
        blocks.append(f"<non_lawmaker_warning>\n{non_lawmaker_clean}\n</non_lawmaker_warning>")

    if not blocks:
        return ""

    return "<role_warning_bundle>\n" + "\n\n".join(blocks) + "\n</role_warning_bundle>"


def generate_non_lawmaker_warning(
    position: Optional[str],
    status: Optional[str],
    political_experience: Optional[str],
    author_bio: Optional[str],
) -> str:
    """작성자 직책·재임 상태·경력에 맞는 금지/허용 표현 가이드를 생성한다.

    입력 필드:
    - `position`: `_canonical_position` 결과
      (국회의원 / 광역의원 / 기초의원 / 광역자치단체장 / 기초자치단체장 / 기타)
    - `status`: '예비' / '현역' 등 재임 상태
    - `political_experience`: '정치 신인' / '초선' / '재선' / '3선이상' 등

    분기:
    - 국회의원: 경고 없음 (모든 표현 허용)
    - 광역·기초의원:
        · 신인 예비후보(status='예비' AND experience='정치 신인')
          → 1인칭 현재형 의정활동 금지, 미래형·다짐형만 허용
        · 그 외 (현역 또는 경력자)
          → 국회 전용 표현만 금지, 해당 의회 표현 허용
    - 자치단체장:
        · 신인 예비후보 → 시정/구정 미래형만 허용
        · 그 외 → 의회 활동 표현만 금지
    - 기타 (지역위원장/무직책 등): 신인에 한해 강한 경고
    """
    canonical_position = (position or '').strip()
    status_str = (status or '').strip()
    experience = (political_experience or '').strip()
    bio = author_bio or ''

    if canonical_position == '국회의원':
        return ''

    is_rookie_candidate = ('예비' in status_str) and (experience == '정치 신인')

    if canonical_position in ('광역의원', '기초의원'):
        if is_rookie_candidate:
            return _build_local_assembly_rookie_candidate_warning(canonical_position, bio)
        return _build_local_assembly_warning(canonical_position, bio)

    if canonical_position in ('광역자치단체장', '기초자치단체장'):
        if is_rookie_candidate:
            return _build_executive_rookie_candidate_warning(canonical_position, bio)
        return _build_executive_warning(canonical_position, bio)

    if experience != '정치 신인':
        return ''
    return _build_rookie_warning(bio)


def _build_local_assembly_warning(position: str, author_bio: str) -> str:
    assembly_term, role_term = {
        '광역의원': ('시의회/도의회', '광역의원(시의원/도의원)'),
        '기초의원': ('구의회/군의회', '기초의원(구의원/군의원)'),
    }.get(position, ('지방의회', '지방의원'))

    return f"""
╔═══════════════════════════════════════════════════════════════╗
║  🚫 작성자 신분 설정 (원고에 명시 금지)                          ║
╚═══════════════════════════════════════════════════════════════╝

작성자: {author_bio}
작성자 직책: {role_term}
(이 정보는 글쓰기 톤 설정용입니다. 원고 본문에 직접 노출하지 마세요.)

[절대 금지 - 국회 전용 표현]
❌ "국회의원", "국회 활동", "국회에서", "원내", "원 구성" 등 국회 관련 표현
❌ "지역구 의원", "지역구 국회의원", "지역구 현안", "지역구 발전" 등 "지역구"가 들어가는 모든 표현
   (이유: "지역구"는 국회의원 전용 용어. {role_term}은 "선거구" 혹은 지역명 사용)
   → 대체 표현: "우리 지역", "이 지역", 광역/기초지자체명
❌ "256명의 국회의원 중..." 같이 본인을 국회의원으로 암시·동일시
❌ "저는 국회의원이 아닙니다만" 등 신분 고백
❌ 위 작성자 정보를 원고 본문에 그대로 복사하는 행위

[허용 / 권장 표현]
✅ "{assembly_term}", "본회의", "상임위원회", "조례 제·개정", "5분 자유발언"
✅ "의정활동", "의원 경력", "의안 발의", "행정사무감사" — {role_term}의 정상 활동
✅ "OO시민", "OO구 주민", "OO군민" 등 지역명 + 시민/주민 표현

[예외 규칙]
✅ Bio(작성자 정보) 내 **큰따옴표(" ")로 묶인 문장**은 금지어 포함 여부와 무관하게 원문 그대로 인용
   - 예: "그 스펙이면 벌써 국회의원 했을 텐데" (그대로 유지)

→ 원고는 {role_term}의 자연스러운 관점에서 작성하되, 국회 수준의 표현으로 과장하지 마세요.
"""


def _build_executive_warning(position: str, author_bio: str) -> str:
    admin_term, role_term = {
        '광역자치단체장': ('시정/도정', '광역자치단체장(시장/도지사)'),
        '기초자치단체장': ('시정/구정/군정', '기초자치단체장(시장/군수/구청장)'),
    }.get(position, ('자치단체 행정', '자치단체장'))

    return f"""
╔═══════════════════════════════════════════════════════════════╗
║  🚫 작성자 신분 설정 (원고에 명시 금지)                          ║
╚═══════════════════════════════════════════════════════════════╝

작성자: {author_bio}
작성자 직책: {role_term}
(이 정보는 글쓰기 톤 설정용입니다. 원고 본문에 직접 노출하지 마세요.)

[절대 금지 - 국회/의회 활동 표현]
❌ "국회의원", "국회 활동", "지역구 의원", "지역구 국회의원" 등 국회 관련 표현
❌ "의정활동", "본회의", "상임위", "의안 발의", "5분 자유발언" 등 의회 활동 표현
   (이유: {role_term}은 의회 소속이 아닌 행정부 수장)
❌ "저는 국회의원이 아닙니다만" 등 신분 고백
❌ 위 작성자 정보를 원고 본문에 그대로 복사하는 행위

[허용 / 권장 표현]
✅ "{admin_term}", "행정", "자치단체 운영", "정책 집행", "현장 행정"
✅ "시민 여러분", "OO시민", "OO구민", "OO군민" 등 지역명+주민 표현

[예외 규칙]
✅ Bio 내 큰따옴표(" ")로 묶인 문장은 원문 그대로 인용

→ 원고는 행정부 수장의 관점에서 작성하되, 의회 활동으로 오해될 표현은 피하세요.
"""


def _build_local_assembly_rookie_candidate_warning(position: str, author_bio: str) -> str:
    assembly_term, role_term, candidate_term = {
        '광역의원': ('시의회/도의회', '광역의원', '광역의원(시의원/도의원) 예비후보'),
        '기초의원': ('구의회/군의회', '기초의원', '기초의원(구의원/군의원) 예비후보'),
    }.get(position, ('지방의회', '지방의원', '지방의원 예비후보'))

    return f"""
╔═══════════════════════════════════════════════════════════════╗
║  🚫 작성자 신분 설정 (원고에 명시 금지)                          ║
╚═══════════════════════════════════════════════════════════════╝

작성자: {author_bio}
작성자 직책: {candidate_term} (정치 신인)
(아직 {role_term}이 아닙니다. 선거를 준비하는 단계이며, 의정 경험이 전혀 없습니다.)

[절대 금지 - 국회 전용 표현]
❌ "국회의원", "국회 활동", "국회에서", "원내" 등 국회 관련 표현 일체
❌ "지역구 의원", "지역구 국회의원", "지역구 현안" 등 "지역구"가 들어가는 모든 표현
   → 대체: "우리 지역", "이 지역", 광역/기초지자체명

[절대 금지 - 본인이 이미 의원인 것처럼 쓰는 1인칭 현재·과거형]
❌ "저는 {assembly_term}에서 의정활동을 하고 있습니다" — 거짓 (의원이 아님)
❌ "제가 발의한 조례", "제가 상정한 안건", "최근 제 의정활동" — 거짓
❌ "본회의에서 5분 자유발언을 했습니다" — 거짓
❌ "{role_term}으로서", "OO 의원으로서" 같은 1인칭 현재형 자기규정 — 거짓
❌ "의정활동 중 주민 여러분께서..." — 거짓
❌ "저는 정치 신인입니다만", "저는 예비후보입니다만" 등 신분 고백
❌ 위 작성자 정보를 원고 본문에 그대로 복사하는 행위

[허용 - 미래형·다짐형·3인칭 언급]
✅ "{role_term}이 되면 OO 조례를 발의하겠습니다" — 미래형 공약
✅ "당선되면 OO 하겠습니다", "OO에 앞장서겠습니다" — 다짐
✅ "{assembly_term}는 OO 역할을 해야 합니다" — 3인칭 기관 언급
✅ "OO 조례는 반드시 제·개정되어야 합니다" — 정책 주장
✅ "저는 그동안 OO 정책을 연구해 왔습니다" — 준비/연구 활동
✅ "OO 현장에서 주민 여러분의 목소리를 들어왔습니다" — 현장 활동
✅ "OO 시민사회·정책 전문가로서" — 실제 경력 기반 자기규정

[톤 가이드]
✅ 출마 준비, 공약 설계, 정책 연구, 현장 경험, 주민 소통 중심으로 서술
✅ "OO시민", "OO구 주민", "OO군민" 등 지역명 + 시민/주민 표현
✅ 실제 직위(지역위원장, 정책연구소장 등)가 있다면 자연스럽게 사용

[예외 규칙]
✅ Bio 내 큰따옴표(" ")로 묶인 문장은 원문 그대로 인용

→ 핵심 원칙: 과거·현재는 "준비·연구·현장 소통", 미래는 "공약·다짐".
→ {assembly_term} 내부 활동은 모두 **미래형 또는 3인칭**으로만 서술.
"""


def _build_executive_rookie_candidate_warning(position: str, author_bio: str) -> str:
    admin_term, role_term, candidate_term = {
        '광역자치단체장': ('시정/도정', '광역자치단체장', '광역자치단체장(시장/도지사) 예비후보'),
        '기초자치단체장': ('시정/구정/군정', '기초자치단체장', '기초자치단체장(시장/군수/구청장) 예비후보'),
    }.get(position, ('자치단체 행정', '자치단체장', '자치단체장 예비후보'))

    return f"""
╔═══════════════════════════════════════════════════════════════╗
║  🚫 작성자 신분 설정 (원고에 명시 금지)                          ║
╚═══════════════════════════════════════════════════════════════╝

작성자: {author_bio}
작성자 직책: {candidate_term} (정치 신인)
(아직 {role_term}이 아닙니다. 선거를 준비하는 단계이며, 행정 집행 경험이 전혀 없습니다.)

[절대 금지 - 국회/의회 활동 표현]
❌ "국회의원", "국회 활동", "지역구 의원" 등 국회 관련 표현
❌ "의정활동", "본회의", "상임위", "의안 발의" 등 의회 활동 표현
   (이유: {role_term}은 의회 소속이 아닌 행정부 수장)

[절대 금지 - 본인이 이미 단체장인 것처럼 쓰는 1인칭 현재·과거형]
❌ "저는 {admin_term}을 운영하고 있습니다" — 거짓
❌ "제가 추진한 사업", "제가 집행한 정책", "최근 제 행정" — 거짓
❌ "{role_term}으로서 OO을 결정했습니다" — 거짓
❌ "저는 정치 신인입니다만", "저는 예비후보입니다만" 등 신분 고백
❌ 위 작성자 정보를 원고 본문에 그대로 복사하는 행위

[허용 - 미래형·다짐형·3인칭 언급]
✅ "{role_term}이 되면 OO 사업을 추진하겠습니다" — 미래형 공약
✅ "당선되면 {admin_term}에 OO 원칙을 세우겠습니다" — 다짐
✅ "OO은 반드시 개선되어야 합니다" — 정책 주장
✅ "저는 그동안 OO 현장에서 주민 목소리를 들어왔습니다" — 현장 활동

[톤 가이드]
✅ 출마 준비, 공약 설계, 정책 연구, 현장 경험, 주민 소통 중심
✅ "시민 여러분", "OO시민", "OO구민", "OO군민" 지역명+주민 표현
✅ 실제 직위(지역위원장 등)가 있다면 자연스럽게 사용

[예외 규칙]
✅ Bio 내 큰따옴표(" ")로 묶인 문장은 원문 그대로 인용

→ 핵심 원칙: 과거·현재는 "준비·연구·현장 소통", 미래는 "공약·다짐".
→ 행정 집행은 모두 **미래형 또는 3인칭**으로만 서술.
"""


def _build_rookie_warning(author_bio: str) -> str:
    return f"""
╔═══════════════════════════════════════════════════════════════╗
║  🚫 작성자 신분 설정 (원고에 명시 금지)                          ║
╚═══════════════════════════════════════════════════════════════╝

작성자: {author_bio}
(이 정보는 글쓰기 톤 설정용입니다. 원고 본문에 절대 노출하지 마세요.)

[절대 금지 사항]
❌ "지역구 의원", "지역구 국회의원", "의정활동", "국회 활동", "의원 경력" 등 국회의원 전용 표현 일체
❌ "256명의 국회의원 중..." 같은 맥락에서 본인을 의원으로 암시하거나 동일시하는 표현
❌ **"지역구" 표현 절대 금지** - "지역구 발전", "지역구 주민", "지역구 현안" 등 모두 불가
   (이유: "지역구"는 국회의원 전용 용어. 광역/기초지자체장은 사용 불가)
   → 대체 표현: "우리 지역", "이 지역", 광역지자체명(부산, 경남 등) 또는 기초지자체명 사용

[원고에 절대 포함하지 말 것]
❌ "저는 정치 신인입니다만", "저는 국회의원이 아닙니다만" 등 신분 고백
❌ "시민의 입장에서", "지역 주민의 한 사람으로서" 같은 화자 위치 명시
❌ "광역자치단체장 준비 중", "시장 준비 중" 등 준비 상태 언급
❌ "저는 OO 준비 중입니다", "OO을 준비하고 있는 홍길동입니다" 같은 자기소개
❌ 위 작성자 정보를 원고 본문에 그대로 복사하는 행위

[예외 규칙 (중요)]
✅ Bio(작성자 정보) 내에 **큰따옴표(" ")로 묶인 문장**은 주변의 평가나 특정 에피소드를 인용한 것이므로, 금지어가 포함되어 있더라도 **절대 수정하거나 검열하지 말고 그대로 사용**하십시오.
   - 예: "그 스펙이면 벌써 국회의원 했을 텐데" (그대로 유지)
   - 예: "왜 사서 고생하노" (그대로 유지)

[작성 가이드]
✅ 작성자의 실제 직위(지역위원장 등)를 사용하세요
✅ 지역 활동, 준비 과정, 정책 연구, 주민과의 소통 등을 중심으로 작성
✅ "OO시민", "OO구 주민" 등 지역명 + 시민/주민 표현 사용 (사용자의 실제 지역에 맞게)

→ 작성자 신분은 글의 톤과 시점을 결정하는 태그입니다.
→ 원고는 자연스럽게 해당 위치에서 말하듯 작성하되, 신분 자체를 언급하지 마세요.
"""

def generate_family_status_warning(family_status: str) -> str:
    if not family_status:
        return ''

    # Warning only for '기혼(자녀 없음)' or '미혼'
    if family_status in ['기혼(자녀 없음)', '미혼']:
        return f"""
╔═══════════════════════════════════════════════════════════════╗
║  ⚠️  가족 상황 확인 - 절대 준수 필수! ⚠️                        ║
╚═══════════════════════════════════════════════════════════════╝

** 작성자는 자녀가 없습니다 **

가족 상황: {family_status}

[절대 금지 사항]
❌ "자녀", "아이", "아들", "딸" 등 자녀 관련 표현 절대 금지
❌ "자녀 양육", "육아", "자녀 교육", "부모로서" 등의 표현 절대 금지
❌ "아버지로서", "어머니로서" 등 부모 정체성 표현 절대 금지
❌ 자녀가 있다고 가정하거나 암시하는 어떠한 내용도 금지

[작성 가이드]
✅ 작성자의 실제 가족 상황에 맞는 내용만 작성
✅ 개인적 경험을 언급할 때도 자녀 관련 내용은 절대 포함하지 말 것
"""
    return ''
