import pathlib
import sys
from textwrap import dedent


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from handlers.generate_posts_pkg.pipeline import _restore_terminal_output_addons_once


def test_terminal_output_addons_restore_missing_tail_blocks() -> None:
    content = dedent(
        """
        <p>The opening frames why this race matters to everyday life.</p>
        <h2>Why this race still deserves attention</h2>
        <p>The conclusion should connect execution, trust, and visible results.</p>
        """
    ).strip()

    restored = _restore_terminal_output_addons_once(
        content,
        output_options={
            "slogan": "Busan can grow again",
            "sloganEnabled": True,
            "donationInfo": "Support account 100-200-300",
            "donationEnabled": True,
            "pollCitation": "Agency: Example Research\\nSample: 1,000 voters",
            "embedPollCitation": True,
        },
        content_meta={
            "pollCitation": "Agency: Example Research\\nSample: 1,000 voters",
            "pollCitationForced": True,
        },
    )
    updated = str(restored.get("content") or "")

    assert restored.get("edited") is True
    assert "terminal_donation_info" in (restored.get("actions") or [])
    assert "terminal_slogan" in (restored.get("actions") or [])
    assert "terminal_poll_citation" in (restored.get("actions") or [])
    assert updated.count('font-size: 0.9em; color: #666; margin: 1em 0;') == 1
    assert updated.count('font-weight: bold; margin: 1.5em 0;') == 1
    assert updated.count('border-top: 1px solid #ddd; padding-top: 0.8em;') == 1


def test_terminal_output_addons_do_not_duplicate_existing_blocks() -> None:
    content = dedent(
        """
        <p>The opening frames why this race matters to everyday life.</p>
        <h2>Why this race still deserves attention</h2>
        <p>The conclusion should connect execution, trust, and visible results.</p>
        """
    ).strip()
    options = {
        "slogan": "Busan can grow again",
        "sloganEnabled": True,
        "donationInfo": "Support account 100-200-300",
        "donationEnabled": True,
        "pollCitation": "Agency: Example Research\\nSample: 1,000 voters",
        "embedPollCitation": True,
    }
    meta = {
        "pollCitation": "Agency: Example Research\\nSample: 1,000 voters",
        "pollCitationForced": True,
    }

    once = _restore_terminal_output_addons_once(
        content,
        output_options=options,
        content_meta=meta,
    )
    twice = _restore_terminal_output_addons_once(
        str(once.get("content") or ""),
        output_options=options,
        content_meta=meta,
    )
    updated = str(twice.get("content") or "")

    assert updated.count('font-size: 0.9em; color: #666; margin: 1em 0;') == 1
    assert updated.count('font-weight: bold; margin: 1.5em 0;') == 1
    assert updated.count('border-top: 1px solid #ddd; padding-top: 0.8em;') == 1


def main() -> None:
    tests = [
        (
            "terminal_output_addons_restore_missing_tail_blocks",
            test_terminal_output_addons_restore_missing_tail_blocks,
        ),
        (
            "terminal_output_addons_do_not_duplicate_existing_blocks",
            test_terminal_output_addons_do_not_duplicate_existing_blocks,
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
