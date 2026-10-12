#!/usr/bin/env python3
"""智维 (ZhiWei) 维修结果验证工具.

对比「维修前」与「维修后复测」两段数据，判断维修是否成功：

  * 维修后数据以【维修前数据的基线】为参照（跨文件基线），
    否则"从第一秒就存在的残留故障"会被当成正常基线而漏判。
  * 成功判据：维修后无持续异常，且各测点尾部偏移 |z| < 4。
  * 失败时给出残留故障候选，供智能体重新规划维修方案。

只依赖 Python 标准库。

用法:
    python verify_repair.py ../data/sensor_x.csv ../data/repairs/x_repair_e1.00_a1.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_detect import SENSOR_LABELS, SENSOR_UNITS, detect  # noqa: E402
from fault_diagnose import diagnose  # noqa: E402

TOLERANCE_Z = 4.0          # 单测点允许的残留偏移
PARTIAL_IMPROVEMENT = 0.30  # 判定"部分修复"所需的最低改善幅度


def _max_shift(report: dict) -> float:
    return float(report["summary"]["max_abs_shift_z"])


def verify(before_path: Path, after_path: Path, baseline_s: float, z_threshold: float) -> dict:
    before_anomaly = detect(before_path, baseline_s, 61, z_threshold, 5, 6.0)
    before_diag = diagnose(before_path, baseline_s, z_threshold)

    # 关键：维修后数据用维修前数据的基线做对比
    after_anomaly = detect(after_path, baseline_s, 61, z_threshold, 5, 6.0, before_path)
    after_diag = diagnose(after_path, baseline_s, z_threshold, before_path)

    comparison = []
    residual_shifts: dict[str, float] = {}
    before_shifts: dict[str, float] = {}
    worst_residual = 0.0
    for name in before_anomaly["sensors"]:
        b = float(before_anomaly["sensors"][name].get("tail_shift_sigma", 0.0))
        a = float(after_anomaly["sensors"][name].get("tail_shift_sigma", 0.0))
        label = SENSOR_LABELS.get(name, name)
        before_shifts[label] = round(b, 2)
        residual_shifts[label] = round(a, 2)
        worst_residual = max(worst_residual, abs(a))
        improvement = None
        if abs(b) > 0.01:
            improvement = round((abs(b) - abs(a)) / abs(b), 3)
        comparison.append({
            "sensor": name,
            "label": label,
            "unit": SENSOR_UNITS.get(name, ""),
            "before_shift_sigma": round(b, 2),
            "after_shift_sigma": round(a, 2),
            "improvement": improvement,
            "within_tolerance": abs(a) < TOLERANCE_Z,
        })

    persistent_after = int(after_anomaly["summary"]["persistent_anomaly_points"])
    healthy_after = persistent_after == 0 and worst_residual < TOLERANCE_Z
    before_max = _max_shift(before_anomaly)
    after_max = _max_shift(after_anomaly)

    if healthy_after:
        status, verdict, label = "success", "维修成功：设备已恢复到健康基线", "维修成功"
    else:
        improved = before_max > 0 and (before_max - after_max) / before_max >= PARTIAL_IMPROVEMENT
        if improved:
            status, verdict, label = "partial", "部分修复：异常显著减轻但仍有残留故障", "部分修复"
        else:
            status, verdict, label = "failed", "维修失败：异常未改善或仍然严重", "维修失败"

    residual_primary = after_diag.get("primary_diagnosis")
    residual_fault = None
    if status != "success" and residual_primary:
        residual_fault = {
            "fault": residual_primary["fault"],
            "name": residual_primary["name"],
            "confidence": residual_primary["confidence"],
            "evidence": residual_primary["evidence"],
        }

    if status == "success":
        next_step = "闭环完成：维修结果已通过数据验证，可归档本次执行记录"
    else:
        next_step = (
            "维修未通过验证：请重新规划维修方案（例如提高处理彻底度或增加排查项），"
            "再次调用 simulate_repair（提高 effectiveness）并用 verify_repair 复验"
        )

    return {
        "tool": "verify_repair",
        "status": status,
        "verdict": verdict,
        "verdict_label": label,
        "health_index": after_diag["health_index"],
        "before": {
            "file": before_path.name,
            "status": before_anomaly["summary"]["status"],
            "severity": before_anomaly["summary"]["severity"],
            "persistent_anomaly_points": int(before_anomaly["summary"]["persistent_anomaly_points"]),
            "max_abs_shift_z": round(before_max, 2),
            "health_index": before_diag["health_index"],
            "diagnosis": before_diag.get("primary_diagnosis", {}).get("name") if before_diag.get("primary_diagnosis") else None,
        },
        "after": {
            "file": after_path.name,
            "status": after_anomaly["summary"]["status"],
            "severity": after_anomaly["summary"]["severity"],
            "persistent_anomaly_points": persistent_after,
            "max_abs_shift_z": round(after_max, 2),
            "health_index": after_diag["health_index"],
        },
        "tolerance_z": TOLERANCE_Z,
        "before_shifts_sigma": before_shifts,
        "residual_shifts_sigma": residual_shifts,
        "worst_residual_sigma": round(worst_residual, 2),
        "comparison": comparison,
        "residual_fault": residual_fault,
        "next_step": next_step,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="验证工业设备维修结果")
    parser.add_argument("before", help="维修前 CSV")
    parser.add_argument("after", help="维修后复测 CSV")
    parser.add_argument("--baseline-s", type=float, default=120.0)
    parser.add_argument("--z-threshold", type=float, default=4.0)
    parser.add_argument("--json", dest="json_out")
    args = parser.parse_args()

    before_path, after_path = Path(args.before), Path(args.after)
    for p in (before_path, after_path):
        if not p.exists():
            raise SystemExit(f"file not found: {p}")

    report = verify(before_path, after_path, args.baseline_s, args.z_threshold)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())