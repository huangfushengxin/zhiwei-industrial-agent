#!/usr/bin/env python3
"""智维 (ZhiWei) Day 4 演示：错误诊断 -> 验证失败 -> 重新规划 -> 再次维修 -> 验证成功.

流程：
  1. 诊断，得到主判故障与次选候选
  2. 【故意制造错误诊断】按"次选候选"去维修（修错地方）
  3. 验证 -> 不通过（仍有残留异常），并给出残留故障
  4. 重新规划：改为按正确的主判故障维修
  5. 再次维修 -> 验证 -> 成功

用法:
    python demo_misdiagnosis.py ../data/sensor_overload.csv
    python demo_misdiagnosis.py ../data/sensor_overload.csv --json out.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fault_diagnose import diagnose  # noqa: E402
from fault_library import FAULT_LIBRARY  # noqa: E402
from simulate_repair import DEFAULT_OUT_DIR, simulate  # noqa: E402
from verify_repair import verify  # noqa: E402

SEED = 20261009


def run_demo(path: Path, out_dir: Path, wrong_target: str | None = None) -> dict:
    diag = diagnose(path, 120.0, 4.0)
    primary = diag.get("primary_diagnosis")
    if primary is None:
        return {
            "tool": "demo_misdiagnosis",
            "file": path.name,
            "status": "normal",
            "verdict": "设备健康，未触发诊断与维修",
            "health_index": diag["health_index"],
            "next_step": "保持状态监测",
        }

    candidates = diag.get("candidates", [])
    true_fault = primary["fault"]
    runner_up = next((c for c in candidates if c["fault"] != true_fault), None)

    # 故意用"次选候选"当诊断结论（模拟一次误判）
    mis_fault = wrong_target or (runner_up["fault"] if runner_up else None)
    if not mis_fault or mis_fault == true_fault:
        mis_fault = next((k for k in FAULT_LIBRARY if k != true_fault), None)
    if not mis_fault:
        raise SystemExit("无法构造错误诊断：故障库中只有一个故障")

    attempts: list[dict] = []

    # --- 第 1 次：按错误诊断维修 ---
    sim1 = simulate(path, 1.0, true_fault, 1, SEED + 1, out_dir, None, mis_fault)
    ver1 = verify(path, Path(sim1["output_csv"]), 120.0, 4.0)
    attempts.append({
        "attempt": 1,
        "stage": "misdiagnosis",
        "diagnosed_as": mis_fault,
        "diagnosed_as_name": FAULT_LIBRARY[mis_fault]["name"],
        "repair_csv": sim1["output_csv"],
        "verify_status": ver1["status"],
        "verdict": ver1["verdict"],
        "worst_residual_sigma": ver1["worst_residual_sigma"],
        "health_index": ver1["health_index"],
        "residual_shifts_sigma": ver1["residual_shifts_sigma"],
        "residual_fault": ver1["residual_fault"]["name"] if ver1["residual_fault"] else None,
        "pass": ver1["status"] == "success",
    })

    # --- 重新规划 ---
    replan = (
        f"第 1 次维修未通过验证（残留 {ver1['worst_residual_sigma']}σ，"
        f"残留故障指向「{attempts[0]['residual_fault'] or '未知'}」）。"
        f"复盘：维修目标是「{FAULT_LIBRARY[mis_fault]['name']}」，与残留特征不符；"
        f"改为按主判「{primary['name']}」重新规划维修。"
    )

    # --- 第 2 次：按正确诊断维修 ---
    sim2 = simulate(path, 1.0, true_fault, 2, SEED + 2, out_dir, None, true_fault)
    ver2 = verify(path, Path(sim2["output_csv"]), 120.0, 4.0)
    attempts.append({
        "attempt": 2,
        "stage": "replanned",
        "diagnosed_as": true_fault,
        "diagnosed_as_name": FAULT_LIBRARY[true_fault]["name"],
        "repair_csv": sim2["output_csv"],
        "verify_status": ver2["status"],
        "verdict": ver2["verdict"],
        "worst_residual_sigma": ver2["worst_residual_sigma"],
        "health_index": ver2["health_index"],
        "residual_shifts_sigma": ver2["residual_shifts_sigma"],
        "residual_fault": ver2["residual_fault"]["name"] if ver2["residual_fault"] else None,
        "pass": ver2["status"] == "success",
    })

    recovered = (not attempts[0]["pass"]) and attempts[1]["pass"]
    return {
        "tool": "demo_misdiagnosis",
        "file": path.name,
        "asset": diag["asset"],
        "status": "recovered" if recovered else "unresolved",
        "verdict": (
            f"错误诊断已被发现并纠正：先按「{FAULT_LIBRARY[mis_fault]['name']}」维修未通过验证，"
            f"重新规划后按「{primary['name']}」维修，验证通过"
            if recovered else "错误诊断后的恢复流程未收敛，需人工介入"
        ),
        "true_fault": true_fault,
        "true_fault_name": primary["name"],
        "diagnosis_confidence": primary["confidence"],
        "misdiagnosis": {
            "fault": mis_fault,
            "name": FAULT_LIBRARY[mis_fault]["name"],
            "picked_because": "选用了诊断候选中的次选（模拟一次误判）",
        },
        "replan": replan,
        "health_index": {
            "before": diag["health_index"],
            "after_misrepair": attempts[0]["health_index"],
            "after_correct_repair": attempts[1]["health_index"],
        },
        "attempts": attempts,
        "next_step": (
            "归档错误诊断与恢复的完整证据链"
            if recovered else "扩大排查范围或更换失效部件后重跑"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="错误诊断 -> 重新规划 -> 修复成功 演示")
    parser.add_argument("csv", help="传感器 CSV")
    parser.add_argument("--wrong-target", default=None, help="指定错误的维修目标故障（默认取诊断次选）")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--json", dest="json_out")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"file not found: {path}")
    report = run_demo(path, Path(args.out_dir), args.wrong_target)
    if args.compact:
        report.pop("attempts", None)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["status"] in ("recovered", "normal") else 1


if __name__ == "__main__":
    raise SystemExit(main())