#!/usr/bin/env python3
"""智维 (ZhiWei) 维修方案生成工具.

输入传感器 CSV（内部先跑异常检测 + 故障诊断），依据命中故障从共享知识库
取出结构化维修方案：是否停机、预计工时、安全措施、分步工序、备件、复检验收标准。

只依赖 Python 标准库。

用法:
    python repair_plan.py ../data/sensor_bearing_wear.csv
    python repair_plan.py ../data/x.csv --json out.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fault_diagnose import diagnose  # noqa: E402
from fault_library import repair_plan_for  # noqa: E402

DOWNTIME_LABEL = {
    "offline": "需停机检修",
    "online": "可在线处理",
    "conditional": "先在线降载排查，必要时停机",
}


def build_plan(path: Path, baseline_s: float, z_threshold: float,
               baseline_csv: Path | None = None) -> dict:
    """baseline_csv：以另一个文件（如维修前数据）为基线做诊断，用于分析维修后复测数据。"""
    diag = diagnose(path, baseline_s, z_threshold, baseline_csv)
    primary = diag.get("primary_diagnosis")

    if diag["status"] == "normal" or primary is None:
        return {
            "tool": "repair_plan",
            "file": path.name,
            "asset": diag["asset"],
            "status": "normal",
            "verdict": "设备健康，无需维修",
            "health_index": diag["health_index"],
            "plan": None,
            "next_step": "保持状态监测，无需维修",
        }

    plan = repair_plan_for(primary["fault"])
    return {
        "tool": "repair_plan",
        "file": path.name,
        "asset": diag["asset"],
        "status": "planned",
        "verdict": primary["name"],
        "fault": primary["fault"],
        "diagnosis_confidence": primary["confidence"],
        "severity": diag["anomaly_summary"]["severity"] if diag.get("anomaly_summary") else None,
        "health_index": diag["health_index"],
        "downtime": plan["downtime"],
        "downtime_label": DOWNTIME_LABEL.get(plan["downtime"], plan["downtime"]),
        "estimated_hours": plan["estimated_hours"],
        "safety": plan["safety"],
        "steps": plan["steps"],
        "parts": plan["parts"],
        "verification_criteria": plan["verification"],
        "plan": plan,
        "next_step": "调用 simulate_repair 模拟执行该方案，再调用 verify_repair 验证效果",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成工业设备维修方案")
    parser.add_argument("csv", help="传感器 CSV 路径")
    parser.add_argument("--baseline-s", type=float, default=120.0)
    parser.add_argument("--z-threshold", type=float, default=4.0)
    parser.add_argument("--baseline-csv", dest="baseline_csv", default=None,
                        help="以另一个文件为基线（如维修前数据）")
    parser.add_argument("--json", dest="json_out")
    parser.add_argument("--compact", action="store_true", help="省略重复嵌套的 plan 字段")
    args = parser.parse_args()

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"file not found: {path}")
    report = build_plan(path, args.baseline_s, args.z_threshold,
                        Path(args.baseline_csv) if args.baseline_csv else None)
    if args.compact:
        report.pop("plan", None)

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())