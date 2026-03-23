import pathlib
import sys
from textwrap import dedent


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from agents.core.structure_normalizer import _plain_len, _split_into_sections
from handlers.generate_posts_pkg.pipeline import _apply_terminal_section_length_backstop_once


def test_terminal_section_length_backstop_pads_underfilled_body_section() -> None:
    content = dedent(
        """
    <p>We need a clear explanation of the economic direction before asking voters to compare competing plans.</p>
    <p>The opening should frame why the policy choice matters to daily life and local jobs.</p>
    <h2>Why the challenger moved ahead</h2>
    <p>Voters saw a simple contrast.</p>
    <p>The implementation gap became visible.</p>
    <h2>Why this race still deserves attention</h2>
    <p>The local economy needs a practical growth plan with visible results.</p>
    <p>The conclusion should connect that plan to daily life and public trust.</p>
        """
    ).strip()
    before_sections = _split_into_sections(content)
    before_body_len = _plain_len(before_sections[1]["html"])
    assert before_body_len < 320

    repaired = _apply_terminal_section_length_backstop_once(
        content,
        length_spec={
            "per_section_min": 320,
            "per_section_max": 470,
        },
    )
    updated = str(repaired.get("content") or "")
    after_sections = _split_into_sections(updated)
    after_body_len = _plain_len(after_sections[1]["html"])

    assert repaired.get("edited") is True
    assert any(str(action).startswith("section_length_backstop:2:") for action in repaired.get("actions") or [])
    assert after_body_len >= 320


def test_terminal_section_length_backstop_keeps_short_but_valid_conclusion() -> None:
    content = dedent(
        """
    <p>The city needs a plain explanation of what changes now and why the timing matters.</p>
    <p>The opening has to tie policy choices to outcomes residents can actually feel.</p>
    <h2>Why the challenger moved ahead</h2>
    <p>The contrast was easy to grasp because one side offered a simpler sequence of actions, a clearer order of execution, and a more direct economic message that linked public spending, local jobs, and transport reform into one narrative.</p>
    <p>The campaign also showed how verified local experience can become a measurable plan instead of a slogan, with milestones, agencies, and accountability points that voters could compare without guessing what each promise meant in practice.</p>
    <h2>Why this race still deserves attention</h2>
    <p>The next administration will be judged on whether it can turn that contrast into execution, restore confidence, and show visible results without delay.</p>
        """
    ).strip()
    before_sections = _split_into_sections(content)
    before_conclusion_len = _plain_len(before_sections[-1]["html"])
    assert 130 <= before_conclusion_len < 320

    repaired = _apply_terminal_section_length_backstop_once(
        content,
        length_spec={
            "per_section_min": 320,
            "per_section_max": 470,
        },
    )

    assert repaired.get("edited") is False
    assert list(repaired.get("actions") or []) == []


def main() -> None:
    tests = [
        (
            "terminal_section_length_backstop_pads_underfilled_body_section",
            test_terminal_section_length_backstop_pads_underfilled_body_section,
        ),
        (
            "terminal_section_length_backstop_keeps_short_but_valid_conclusion",
            test_terminal_section_length_backstop_keeps_short_but_valid_conclusion,
        ),
    ]
    passed = 0
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
        passed += 1
    print(f"OK {passed}")


if __name__ == "__main__":
    main()
