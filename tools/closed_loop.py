#!/usr/bin/env python3
"""智维 (ZhiWei) 智能运维闭环编排.

一条命令走完完整闭环：

    数据读取 -> 异常检测 -> 故障诊断 -> 维修方案 -> 模拟维修 -> 维修后验证
                                                        ^                |
                                                        |  失败则重新规划  |
                                                        +----------------+

验证不通过时按 escalation 提高修复彻底度（每次 +0.5，上限 1.0）重新规划并再修，
最多尝试 max_attempts 次；全过程写入 trace，可作为"Agent 执行时间线"证据。

只依赖 Python 标准库。

用法:
    python closed_loop.py ../data/sensor_overload.csv
    python closed_loop.py ../data/sensor_overload.csv --repair-effectiveness 0.5
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_detect import detect  # noqa: E402
from fault_diagnose import diagnose  # noqa: E402
from repair_plan import build_plan  # noqa: E402
from simulate_repair import DEFAULT_OUT_DIR, simulate  # noqa: E402
from verify_repair import verify  # noqa: E402

def _display_path(value) -> str:
    try:
        return str(Path(value).resolve().relative_to(Path(__file__).resolve().parents[1]))
    except Exception:
        return Path(value).name


ESCALATION_STEP = 0.5   # 每次重新规划提高的修复彻底度（唯一的调参点）
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_SEED = 20261009


def run(csv_path: Path, repair_effectiveness: float = 1.0,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS, seed: int = DEFAULT_SEED,
        out_dir: Path | None = None) -> dict:
    out_dir = out_dir or DEFAULT_OUT_DIR
    trace: list[dict] = []
    started = datetime.now()

    def note(step: str, status: str, detail) -> None:
        trace.append({
            "step": step,
            "status": status,
            "detail": detail,
            "at": datetime.now().isoformat(timespec="seconds"),
        })

    # 1) 数据读取
    try:
        from anomaly_detect import read_series
        timestamps, series = read_series(csv_path)
        note("read_data", "ok", {"file": csv_path.name, "samples": len(timestamps)})
    except Exception as exc:  # noqa: BLE001
        note("read_data", "failed", str(exc))
        return {"tool": "closed_loop", "status": "error", "verdict": f"数据读取失败：{exc}",
                "trace": trace, "next_step": "检查数据文件路径与格式"}

    # 2) 异常检测
    anomaly = detect(csv_path, 120.0, 61, 4.0, 5, 6.0)
    note("detect_anomalies", anomaly["summary"]["status"], {
        "severity": anomaly["summary"]["severity"],
        "affected_sensors": anomaly["summary"]["affected_sensors"],
        "max_abs_shift_z": anomaly["summary"]["max_abs_shift_z"],
    })

    # 3) 故障诊断
    diag = diagnose(csv_path, 120.0, 4.0)
    note("diagnose_fault", diag["status"], {
        "verdict": diag["verdict"],
        "confidence": diag["primary_diagnosis"]["confidence"] if diag["primary_diagnosis"] else None,
    })

    if diag["status"] == "normal":
        note("plan_repair", "skipped", "设备健康，无需维修")
        return {
            "tool": "closed_loop",
            "status": "healthy",
            "verdict": "设备健康，未触发维修闭环",
            "health_index": diag["health_index"],
            "input_file": csv_path.name,
            "attempts": [],
            "trace": trace,
            "next_step": "保持状态监测",
            "started_at": started.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }

    # 4) 维修方案
    plan = build_plan(csv_path, 120.0, 4.0)
    note("plan_repair", "planned", {
        "fault": plan["fault"],
        "downtime": plan["downtime"],
        "steps": len(plan["steps"]),
        "estimated_hours": plan["estimated_hours"],
    })

    # 5/6) 模拟维修 -> 验证（失败则重新规划）
    attempts: list[dict] = []
    final_status = "unresolved"
    for attempt in range(1, max_attempts + 1):
        effectiveness = min(1.0, repair_effectiveness + (attempt - 1) * ESCALATION_STEP)
        replan_reason = None
        if attempt > 1:
            prev = attempts[-1]
            replan_reason = (
                f"第 {attempt - 1} 次验证未通过（残留 {prev['worst_residual_sigma']}σ），"
                f"重新规划：提高维修彻底度至 effectiveness={effectiveness:.2f}"
            )
            note("replan", "replanned", replan_reason)

        sim = simulate(csv_path, effectiveness, plan["fault"], attempt, seed + attempt, out_dir, None)
        note("simulate_repair", "simulated", {
            "attempt": attempt, "effectiveness": effectiveness,
            "output_csv": sim.get("output_csv_rel", sim["output_csv"]),
        })

        ver = verify(csv_path, Path(sim["output_csv"]), 120.0, 4.0)
        note("verify_repair", ver["status"], {
            "attempt": attempt,
            "verdict": ver["verdict"],
            "worst_residual_sigma": ver["worst_residual_sigma"],
            "health_index": ver["health_index"],
        })

        attempts.append({
            "attempt": attempt,
            "effectiveness": effectiveness,
            "replan_reason": replan_reason,
            "repair_csv": sim.get("output_csv_rel", sim["output_csv"]),
            "verify_status": ver["status"],
            "verdict": ver["verdict"],
            "worst_residual_sigma": ver["worst_residual_sigma"],
            "health_index": ver["health_index"],
            "residual_fault": ver["residual_fault"]["name"] if ver["residual_fault"] else None,
            "residual_shifts_sigma": ver["residual_shifts_sigma"],
        })

        if ver["status"] == "success":
            final_status = "repaired"
            break

    last = attempts[-1]
    if final_status == "repaired":
        verdict = f"闭环完成：经过 {len(attempts)} 次维修，设备已恢复健康（健康度 {last['health_index']}）"
        next_step = "归档本次闭环记录（trace 可作为 Agent 执行时间线）"
    else:
        verdict = f"闭环未收敛：{len(attempts)} 次尝试后仍存在残留故障（最差 {last['worst_residual_sigma']}σ）"
        next_step = "需人工介入：扩大排查范围或更换失效部件后重新运行闭环"

    record = {
        "tool": "closed_loop",
        "status": final_status,
        "verdict": verdict,
        "input_file": csv_path.name,
        "asset": plan["asset"],
        "fault": plan["fault"],
        "fault_name": plan["verdict"],
        "health_index_before": diag["health_index"],
        "health_index_after": last["health_index"],
        "repair_plan": {
            "downtime": plan["downtime"],
            "downtime_label": plan["downtime_label"],
            "estimated_hours": plan["estimated_hours"],
            "steps": plan["steps"],
            "parts": plan["parts"],
            "safety": plan["safety"],
        },
        "attempts": attempts,
        "trace": trace,
        "next_step": next_step,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    record_path = out_dir / f"{csv_path.stem}_closed_loop.json"
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    record["record_json"] = _display_path(record_path)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="智维智能运维闭环")
    parser.add_argument("csv", help="传感器 CSV 路径")
    parser.add_argument("--repair-effectiveness", type=float, default=1.0,
                        help="首次维修的修复彻底度 0~1（1=完全修复）")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--json", dest="json_out")
    parser.add_argument("--summary", action="store_true", help="只打印摘要与 trace")
    args = parser.parse_args()

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"file not found: {path}")

    record = run(path, args.repair_effectiveness, args.max_attempts, args.seed, Path(args.out_dir))
    if args.summary:
        record = {k: v for k, v in record.items() if k != "repair_plan"}

    text = json.dumps(record, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if record["status"] in ("repaired", "healthy") else 1


if __name__ == "__main__":
    raise SystemExit(main())