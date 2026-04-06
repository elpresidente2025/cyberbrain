from __future__ import annotations

import ast
import pathlib
import re


TEST_ROOT = pathlib.Path(__file__).resolve().parent
PLACEHOLDER_RE = re.compile(r"\{[a-z_][a-z0-9_]*\}")
KOREAN_FULL_NAME_TOKEN = (
    r"(?:남궁|황보|제갈|선우|독고|사공|서문)[가-힣]{2}"
    r"|(?:김|이|박|최|정|강|조|윤|장|임|한|오|서|신|권|황|안|송|전|홍|고|문|양|손|배|백|허|유|남|심|노|하|곽|성|차|주|우)[가-힣]{2}"
)
IDENTITY_CONTEXT_PATTERNS = (
    re.compile(rf'full_name\s*=\s*["\'](?P<name>{KOREAN_FULL_NAME_TOKEN})["\']'),
    re.compile(rf'fullName["\']?\s*:\s*["\'](?P<name>{KOREAN_FULL_NAME_TOKEN})["\']'),
    re.compile(rf'user_keywords\s*=\s*\[\s*["\'](?P<name>{KOREAN_FULL_NAME_TOKEN})["\']'),
    re.compile(rf'userKeywords["\']?\s*:\s*\[\s*["\'](?P<name>{KOREAN_FULL_NAME_TOKEN})["\']'),
    re.compile(
        rf'["\'](?P<name>{KOREAN_FULL_NAME_TOKEN})(?:,|\s+(?:의원|후보|시장|지사|대통령|국회의원|시의원|광역의원|위원장))'
    ),
)


def _iter_test_files() -> list[pathlib.Path]:
    return sorted(
        path
        for path in TEST_ROOT.glob("*.py")
        if path.name != pathlib.Path(__file__).name
    )


def _collect_leading_comments(lines: list[str], lineno: int) -> list[str]:
    comments: list[str] = []
    index = int(lineno) - 2
    while index >= 0:
        stripped = lines[index].strip()
        if not stripped:
            index -= 1
            continue
        if not stripped.startswith("#"):
            break
        comments.append(stripped)
        index -= 1
    comments.reverse()
    return comments


def _iter_marked_synthetic_fixtures() -> list[dict[str, object]]:
    marked: list[dict[str, object]] = []
    for path in _iter_test_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        lines = source.splitlines()
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            comments = _collect_leading_comments(lines, int(node.lineno))
            if "# synthetic_fixture" not in comments:
                continue
            start = int(node.lineno) - 1
            end = int(getattr(node, "end_lineno", node.lineno))
            segment = "\n".join(lines[start:end])
            marked.append(
                {
                    "path": path,
                    "name": node.name,
                    "segment": segment,
                    "real_fixture_ok": any(
                        comment.startswith("# real_fixture_ok:") for comment in comments
                    ) or "# real_fixture_ok:" in segment,
                }
            )
    return marked


def test_marked_synthetic_fixtures_use_slot_placeholders() -> None:
    missing_placeholders: list[str] = []
    for fixture in _iter_marked_synthetic_fixtures():
        segment = str(fixture.get("segment") or "")
        if not PLACEHOLDER_RE.search(segment):
            path = pathlib.Path(str(fixture.get("path") or ""))
            missing_placeholders.append(f"{path.name}:{fixture.get('name')}")

    assert not missing_placeholders, (
        "synthetic_fixture 표식이 있는 테스트는 {user_name} 같은 슬롯 플레이스홀더를 포함해야 합니다: "
        + ", ".join(missing_placeholders)
    )


def test_marked_synthetic_fixtures_avoid_hardcoded_real_names_without_override() -> None:
    violations: list[str] = []
    for fixture in _iter_marked_synthetic_fixtures():
        if bool(fixture.get("real_fixture_ok")):
            continue
        segment = str(fixture.get("segment") or "")
        matched_name = ""
        for pattern in IDENTITY_CONTEXT_PATTERNS:
            match = pattern.search(segment)
            if match:
                matched_name = str(match.group("name") or "").strip()
                break
        if matched_name:
            path = pathlib.Path(str(fixture.get("path") or ""))
            violations.append(f"{path.name}:{fixture.get('name')}:{matched_name}")

    assert not violations, (
        "synthetic_fixture 표식이 있는 테스트에는 실명 대신 슬롯을 사용해야 합니다. "
        "실명이 꼭 필요하면 # real_fixture_ok: 사유 를 명시하세요: "
        + ", ".join(violations)
    )
