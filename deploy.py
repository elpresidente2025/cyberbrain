#!/usr/bin/env python3
"""Firebase deploy helper.

Modes:
- hosting-only: build frontend + deploy hosting
- functions-only: deploy functions only (no frontend build)
- full: build frontend + deploy all
- both: build frontend + deploy functions then hosting
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"


def run_command(command: list[str], cwd: Path | None = None) -> None:
    working_dir = cwd or ROOT_DIR
    print(f"$ {' '.join(command)}")
    subprocess.run(
        command,
        cwd=str(working_dir),
        check=True,
        shell=(os.name == "nt"),
    )


def maybe_setup_functions_config() -> None:
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    election_mode = os.getenv("ELECTION_MODE", "off").strip() or "off"

    if not gemini_key:
        print("skip functions:config:set (GEMINI_API_KEY is not set)")
        return

    print("setting firebase functions config: gemini.key, election.mode")
    run_command(
        [
            "firebase",
            "functions:config:set",
            f"gemini.key={gemini_key}",
            f"election.mode={election_mode}",
        ]
    )


def deploy(mode: str, *, skip_build: bool, skip_config: bool) -> None:
    print("start firebase deploy")
    print(f"mode: {mode}")

    if not skip_config:
        maybe_setup_functions_config()
    else:
        print("skip functions:config:set by --skip-config")

    needs_frontend_build = mode in {"hosting-only", "full", "both"}
    if needs_frontend_build and not skip_build:
        print("building frontend")
        run_command(["npm", "run", "build"], cwd=FRONTEND_DIR)
    elif needs_frontend_build and skip_build:
        print("skip frontend build by --skip-build")
    else:
        print("skip frontend build for functions-only mode")

    if mode == "hosting-only":
        run_command(["firebase", "deploy", "--only", "hosting", "--force"])
    elif mode == "functions-only":
        run_command(["firebase", "deploy", "--only", "functions", "--force"])
    elif mode == "full":
        run_command(["firebase", "deploy", "--force"])
    elif mode == "both":
        run_command(["firebase", "deploy", "--only", "functions", "--force"])
        run_command(["firebase", "deploy", "--only", "hosting", "--force"])
    else:
        raise ValueError(f"unsupported mode: {mode}")

    print("deploy completed")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Firebase deploy helper")
    parser.add_argument(
        "mode",
        nargs="?",
        default="hosting-only",
        choices=["hosting-only", "functions-only", "full", "both"],
        help="deploy mode",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="skip frontend build even for hosting/full/both modes",
    )
    parser.add_argument(
        "--skip-config",
        action="store_true",
        help="skip firebase functions:config:set",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        deploy(
            args.mode,
            skip_build=bool(args.skip_build),
            skip_config=bool(args.skip_config),
        )
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"deploy failed (exit={exc.returncode})")
        return int(exc.returncode or 1)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"deploy failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
