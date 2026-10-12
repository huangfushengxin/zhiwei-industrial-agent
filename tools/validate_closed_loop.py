#!/usr/bin/env python3
"""智维 (ZhiWei) 闭环验证脚本.

验证三组场景：
  A. 正常设备        -> 不应触发维修闭环（healthy）
  B. 4 类故障 e=1.0  -> 应一次修好（repaired, attempts=1）
  C. 故障 + 维修失败 -> 第 1 次验证不通过，重新规划后第 2 次成功（attempts=2）

用法:
    python validate_closed_loop.py
    python validate_closed_loop.py --json ../evidence/day3/closed-loop-report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from closed_loop import run as run_loop  # noqa: E402
from simulate_repair import DEFAULT_OUT_DIR  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FAULTS = ["bearing_wear", "misalignment", "overload", "cavitation"]


def main() -> int:
    parser = argparse.ArgumentParser(description="智维闭环验证")
    parser.add_argument("--data", default=str(ROOT / "data"))
    parser.add_argument("--json", dest="json_out")
    args = parser.parse_args()

    data_dir = Path(args.data)
    out_dir = Path(DEFAULT_OUT_DIR)
    results = []
    failed = 0

    # A. 正常设备
    rec = run_loop(data_dir / "sensor_normal.csv", 1.0, 3, 20261009, out_dir)
    ok = rec["status"] == "healthy" and not rec["attempts"]
    failed += 0 if ok else 1
    results.append({"case": "A_正常设备", "scenario": "normal", "effectiveness": 1.0,
                    "status": rec["status"], "attempts": len(rec["attempts"]),
                    "health_after": rec["health_index"], "expected": "healthy / 0 次",
                    "correct": ok, "verdict": rec["verdict"]})

    # B. 4 类故障，一次修好
    for name in FAULTS:
        rec = run_loop(data_dir / f"sensor_{name}.csv", 1.0, 3, 20261009, out_dir)
        ok = rec["status"] == "repaired" and len(rec["attempts"]) == 1
        failed += 0 if ok else 1
        results.append({"case": "B_一次修好", "scenario": name, "effectiveness": 1.0,
                        "status": rec["status"], "attempts": len(rec["attempts"]),
                        "health_after": rec["health_index_after"], "expected": "repaired / 1 次",
                        "correct": ok, "verdict": rec["verdict"]})

    # C. 维修失败 -> 重新规划 -> 成功
    rec = run_loop(data_dir / "sensor_overload.csv", 0.5, 3, 20261009, out_dir)
    ok = (rec["status"] == "repaired" and len(rec["attempts"]) == 2
          and rec["attempts"][0]["verify_status"] != "success"
          and rec["attempts"][1]["verify_status"] == "success")
    failed += 0 if ok else 1
    results.append({"case": "C_失败重规划", "scenario": "overload", "effectiveness": 0.5,
                    "status": rec["status"], "attempts": len(rec["attempts"]),
                    "health_after": rec["health_index_after"], "expected": "第1次失败 / 第2次成功",
                    "correct": ok, "verdict": rec["verdict"],
                    "attempt_detail": [
                        {"attempt": a["attempt"], "effectiveness": a["effectiveness"],
                         "verify": a["verify_status"], "residual_sigma": a["worst_residual_sigma"]}
                        for a in rec["attempts"]
                    ]})

    total = len(results)
    passed = total - failed
    report = {"tool": "validate_closed_loop", "total": total, "passed": passed,
              "accuracy": round(passed / total, 3) if total else 0.0, "results": results}

    print(f"{'用例':<14}{'场景':<15}{'期望':<26}{'实际':<30}{'结果'}")
    print("-" * 100)
    for r in results:
        actual = f"{r['status']} / {r['attempts']} 次"
        print(f"{r['case']:<14}{r['scenario']:<15}{r['expected']:<26}{actual:<30}{'PASS' if r['correct'] else 'FAIL'}")
    print("-" * 100)
    print(f"通过率: {passed}/{total} = {report['accuracy'] * 100:.1f}%")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入: {out}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())