"""Install the workspace SOP; optionally register the MCP process with AGH."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ("list_scenarios", "read_sensor_summary", "detect_anomalies", "diagnose_fault",
         "analyze_equipment", "plan_repair", "simulate_repair", "verify_repair", "run_closed_loop")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agh-home", type=Path, required=True, help="AGH source checkout, not AGH_HOME data directory")
    parser.add_argument("--profile", default="local-dev")
    parser.add_argument("--register-mcp", action="store_true")
    args = parser.parse_args()
    entry = args.agh_home.resolve() / "packages/cli/dist/local/agnes.mjs"
    if not entry.is_file() or not shutil.which("node"):
        parser.error("Build AGH and put Node.js on PATH first; see docs/RUNNING.md")
    target = ROOT / ".agh/skills/zhiwei-closed-loop"
    source = ROOT / "agent/skills/zhiwei-closed-loop/SKILL.md"
    if target.exists() and (target / "SKILL.md").read_bytes() != source.read_bytes():
        parser.error("Existing workspace Skill differs; review it before replacing it manually")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target / "SKILL.md")
    print(f"Workspace Skill installed: {target}")
    if args.register_mcp:
        env = {**os.environ, "AGNES_PROFILE": args.profile}
        subprocess.run(["node", str(entry), "daemon", "start"], env=env, check=True)
        command = ["node", str(entry), "mcp", "add", "zhiwei-ops", "--name", "zhiwei-ops",
                   "--stdio", sys.executable, "--arg", str(ROOT / "agent/mcp/zhiwei_mcp_server.py")]
        for tool in TOOLS:
            command.extend(["--allow-tool", tool])
        result = subprocess.run(command, env=env)
        if result.returncode:
            return result.returncode
    print("Next: in the AGH Web workspace, refresh and enable this Skill and the zhiwei-ops MCP service.")
    print("Verify Skill actual=ready and MCP connection=ready/tools=9; registration alone is insufficient.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
