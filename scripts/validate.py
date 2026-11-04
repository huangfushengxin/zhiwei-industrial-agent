"""Run legacy acceptance cases in a temporary copy, keeping source fixtures intact."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "validation")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    steps = ("validate_pipeline", "validate_closed_loop", "validate_day4", "run_demo_cases")
    with tempfile.TemporaryDirectory(prefix="zhiwei-validation-") as temp:
        sandbox = Path(temp)
        shutil.copytree(ROOT / "tools", sandbox / "tools", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "data", sandbox / "data", ignore=shutil.ignore_patterns("uploads", "repairs"))
        for step in steps:
            result = subprocess.run([sys.executable, str(sandbox / "tools" / f"{step}.py"),
                                     "--out" if step == "run_demo_cases" else "--json",
                                     str(output / f"{step}.json")], env=env,
                                    cwd=sandbox / "tools", timeout=120)
            if result.returncode:
                return result.returncode
        result = subprocess.run([sys.executable, str(sandbox / "tools" / "build_demo_page.py"),
                                 str(output / "run_demo_cases.json"), str(output / "zhiwei-demo.html")],
                                env=env, cwd=sandbox / "tools", timeout=30)
        if result.returncode:
            return result.returncode
    print(f"Acceptance reports: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
