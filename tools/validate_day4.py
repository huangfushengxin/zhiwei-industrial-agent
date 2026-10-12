#!/usr/bin/env python3
"""智维 (ZhiWei) Day 4 验收：异常恢复能力.

对全部故障场景验证「故意错误诊断 -> 验证不通过 -> 重新规划 -> 再次维修 -> 验证成功」：
  A. 维修前后数据对比可用（verify_repair 给出前后偏移、改善率、残留）
  B. 错误诊断的维修必须【不通过】验证
  C. 重新规划后的第二次维修必须【通过】验证
  D. 结果可复现（同 seed）

用法:
    python validate_day4.py
    python validate_day4.py --json ../evidence/day4/day4-report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_misdiagnosis import run_demo  # noqa: E402
from simulate_repair import DEFAULT_OUT_DIR  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FAULTS = ["bearing_wear", "misalignment", "overload", "cavitation"]


def main() -> int:
    parser = argparse.ArgumentParser(description="智维 Day 4 异常恢复验收")
    parser.add_argument("--data", default=str(ROOT / "data"))
    parser.add_argument("--json", dest="json_out")
    args = parser.parse_args()

    data_dir = Path(args.data)
    out_dir = Path(DEFAULT_OUT_DIR)
    results = []
    passed = 0

    for name in FAULTS:
        rep = run_demo(data_dir / f"sensor_{name}.csv", out_dir)
        a1, a2 = rep["attempts"][0], rep["attempts"][1]
        checks = {
            "错误诊断的维修未通过验证": a1["verify_status"] != "success",
            "重新规划后的维修通过验证": a2["verify_status"] == "success",
            "健康度恢复到 100": a2["health_index"] == 100,
            "残留故障指向真实故障": (a1["residual_fault"] is not None),
        }
        ok = all(checks.values()) and rep["status"] == "recovered"
        passed += 1 if ok else 0
        results.append({
            "scenario": name,
            "true_fault": rep["true_fault"],
            "misdiagnosed_as": rep["misdiagnosis"]["fault"],
            "attempt1_status": a1["verify_status"],
            "attempt1_residual_sigma": a1["worst_residual_sigma"],
            "attempt2_status": a2["verify_status"],
            "attempt2_residual_sigma": a2["worst_residual_sigma"],
            "health": rep["health_index"],
            "checks": checks,
            "correct": ok,
        })

    total = len(results)
    report = {
        "tool": "validate_day4",
        "total": total,
        "passed": passed,
        "accuracy": round(passed / total, 3) if total else 0.0,
        "case": "错误诊断 -> 验证失败 -> 重新规划 -> 维修成功",
        "results": results,
    }

    print(f"{'场景':<15}{'真实故障':<15}{'误判为':<15}{'第1次':<10}{'残留σ':<9}{'第2次':<10}{'健康度':<12}{'结果'}")
    print("-" * 104)
    for r in results:
        print(f"{r['scenario']:<15}{r['true_fault']:<15}{r['misdiagnosed_as']:<15}"
              f"{r['attempt1_status']:<10}{r['attempt1_residual_sigma']:<9}"
              f"{r['attempt2_status']:<10}"
              f"{str(r['health']['before']) + '->' + str(r['health']['after_correct_repair']):<12}"
              f"{'PASS' if r['correct'] else 'FAIL'}")
    print("-" * 104)
    print(f"异常恢复通过率: {passed}/{total} = {report['accuracy'] * 100:.1f}%")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入: {out}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())