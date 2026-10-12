#!/usr/bin/env python3
"""智维 (ZhiWei) Day 5：运行三个测试案例（正常 / 边界 / 失败）并产出展示数据.

  A 正常案例：健康设备 -> 不应误报，不触发维修
  B 边界案例：早期轻微故障（刚越过阈值，warning 级）-> 发现并处置成功
  C 失败案例：故意错误诊断 -> 验证失败 -> 重新规划 -> 维修成功

输出 evidence/day5/demo-cases.json，供展示页与演示视频使用。

用法:
    python run_demo_cases.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from closed_loop import run as run_loop  # noqa: E402
from demo_misdiagnosis import run_demo  # noqa: E402
from fault_library import FAULT_LIBRARY  # noqa: E402
from simulate_repair import DEFAULT_OUT_DIR  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
SEED = 20261010


def case_normal(out_dir: Path) -> dict:
    rec = run_loop(DATA / "sensor_normal.csv", 1.0, 3, SEED, out_dir)
    return {
        "id": "A",
        "name": "正常案例",
        "dataset": "sensor_normal.csv",
        "goal": "健康设备不应误报，也不应触发维修",
        "severity": "normal",
        "status": rec["status"],
        "health": {"before": rec["health_index"], "after": rec["health_index"]},
        "attempts": len(rec["attempts"]),
        "verdict": rec["verdict"],
        "timeline": rec["trace"],
        "pass": rec["status"] == "healthy" and not rec["attempts"],
        "note": "设备处于健康基线，未产生任何维修动作",
    }


def case_boundary(out_dir: Path) -> dict:
    rec = run_loop(DATA / "sensor_boundary_bearing_early.csv", 1.0, 3, SEED, out_dir)
    detect_step = next((s for s in rec["trace"] if s["step"] == "detect_anomalies"), {})
    severity = (detect_step.get("detail") or {}).get("severity", "unknown")
    return {
        "id": "B",
        "name": "边界案例",
        "dataset": "sensor_boundary_bearing_early.csv",
        "goal": "早期轻微故障（刚越过检测阈值）应被检出并成功处置",
        "severity": severity,
        "status": rec["status"],
        "health": {"before": rec["health_index_before"], "after": rec["health_index_after"]},
        "attempts": len(rec["attempts"]),
        "verdict": rec["verdict"],
        "timeline": rec["trace"],
        "pass": rec["status"] == "repaired" and severity == "warning",
        "note": "故障幅度约为满强度的 25%，检测结果为 warning 而非 critical，验证了早期发现能力",
    }


def case_failure(out_dir: Path) -> dict:
    rep = run_demo(DATA / "sensor_overload.csv", out_dir)
    a1, a2 = rep["attempts"][0], rep["attempts"][1]
    timeline = [
        {"step": "diagnose_fault", "status": "diagnosed",
         "detail": {"primary": rep["true_fault"], "misdiagnosis": rep["misdiagnosis"]["fault"]}},
        {"step": "simulate_repair", "status": "simulated",
         "detail": {"attempt": 1, "repair_target": a1["diagnosed_as"],
                    "note": "故意按错误诊断维修"}},
        {"step": "verify_repair", "status": a1["verify_status"],
         "detail": {"worst_residual_sigma": a1["worst_residual_sigma"],
                    "residual_fault": a1["residual_fault"]}},
        {"step": "replan", "status": "replanned", "detail": {"reason": rep["replan"]}},
        {"step": "simulate_repair", "status": "simulated",
         "detail": {"attempt": 2, "repair_target": a2["diagnosed_as"],
                    "note": "按正确主判重新维修"}},
        {"step": "verify_repair", "status": a2["verify_status"],
         "detail": {"worst_residual_sigma": a2["worst_residual_sigma"]}},
    ]
    return {
        "id": "C",
        "name": "失败案例（错误诊断与恢复）",
        "dataset": "sensor_overload.csv",
        "goal": "故意按错误诊断维修 -> 验证失败 -> 重新规划 -> 维修成功",
        "severity": "critical",
        "status": rep["status"],
        "health": {"before": rep["health_index"]["before"],
                   "after": rep["health_index"]["after_correct_repair"],
                   "after_misrepair": rep["health_index"]["after_misrepair"]},
        "attempts": len(rep["attempts"]),
        "verdict": rep["verdict"],
        "timeline": timeline,
        "misdiagnosis": rep["misdiagnosis"],
        "true_fault": rep["true_fault"],
        "true_fault_name": rep["true_fault_name"],
        "replan": rep["replan"],
        "pass": rep["status"] == "recovered",
        "note": "第 1 次维修目标错误导致验证未通过，Agent 依据残留测点纠正诊断后第二次维修通过",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="运行智维演示案例")
    parser.add_argument("--out", default=str(ROOT / "evidence" / "day5" / "demo-cases.json"))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    cases = [case_normal(out_dir), case_boundary(out_dir), case_failure(out_dir)]
    passed = sum(1 for c in cases if c["pass"])
    payload = {
        "tool": "run_demo_cases",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "asset": "离心泵机组 P-101（电机 + 联轴器 + 离心泵 + 轴承座）",
        "model": "Agnes 3.0 Flash（agnes-3.0-flash）",
        "runtime": "Agnes Harness (AGH)",
        "summary": {"total": len(cases), "passed": passed,
                    "accuracy": round(passed / len(cases), 3)},
        "cases": cases,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'案例':<26}{'数据':<40}{'等级':<10}{'状态':<12}{'健康度':<14}{'结果'}")
    print("-" * 118)
    for c in cases:
        h = f"{c['health'].get('before')}->{c['health'].get('after')}"
        print(f"{c['name']:<26}{c['dataset']:<40}{c['severity']:<10}{c['status']:<12}{h:<14}"
              f"{'PASS' if c['pass'] else 'FAIL'}")
    print("-" * 118)
    print(f"三案例通过率: {passed}/{len(cases)} = {payload['summary']['accuracy'] * 100:.1f}%")
    print(f"数据已写入: {out}")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())