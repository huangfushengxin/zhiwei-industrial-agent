#!/usr/bin/env python3
"""智维 (ZhiWei) 模拟维修工具.

根据诊断出的故障类型与修复效果系数，生成一段「维修后复测」的传感器数据：

  残留故障偏移 = (1 - effectiveness) * 估计故障偏移
  估计故障偏移 = 源数据尾段(后 25%)中位数 - 基线(前 120 点)中位数

effectiveness = 1.0 表示完全修复（复测数据回到健康基线）；
effectiveness < 1.0 表示部分修复，会留下可被检测到的残留故障，
这正是「维修失败 -> 重新规划 -> 再维修」演示所需。

输出：
  data/repairs/<源文件>_repair_e<效果>_a<第几次>.csv
  data/repairs/<同名>.json   （元数据：故障、效果、残留偏移、随机种子等）

用法:
    python simulate_repair.py ../data/sensor_bearing_wear.csv --effectiveness 1.0
    python simulate_repair.py ../data/sensor_overload.csv --effectiveness 0.5 --attempt 1
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_detect import read_series  # noqa: E402
from fault_library import FAULT_LIBRARY  # noqa: E402
from generate_sensor_data import BASE, COLUMNS, CYCLE, NOISE, write_csv  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_OUT_DIR = ROOT / "data" / "repairs"
BASELINE_SAMPLES = 120


def _display_path(value) -> str:
    """把路径转成相对项目根的相对路径，避免绝对路径（含用户名）进入证据文件。"""
    try:
        return str(Path(value).resolve().relative_to(ROOT))
    except Exception:
        return Path(value).name


TAIL_FRACTION = 0.25
GAP_SECONDS = 60  # 停机维修后复测，时间轴后移


def estimate_fault_offset(path: Path,
                          baseline_csv: Path | None = None) -> tuple[dict[str, float], list[str]]:
    """估计各测点的故障偏移。

    baseline_csv 给定时，用该文件的前 120 个采样点作为基线——
    这样即使被分析的数据从第 1 秒就带着故障，也能正确估计出残留偏移。
    """
    timestamps, series = read_series(path)
    external: dict[str, list[float]] = {}
    if baseline_csv is not None:
        _, base_series = read_series(Path(baseline_csv))
        external = {k: v[:BASELINE_SAMPLES] for k, v in base_series.items()}
    offsets: dict[str, float] = {}
    for name, values in series.items():
        base = external.get(name) if external else values[:BASELINE_SAMPLES]
        tail = values[int(len(values) * (1 - TAIL_FRACTION)):]
        clean_base = [v for v in base if v == v]
        clean_tail = [v for v in tail if v == v]
        if not clean_base or not clean_tail:
            offsets[name] = 0.0
            continue
        offsets[name] = statistics.median(clean_tail) - statistics.median(clean_base)
    return offsets, timestamps


def simulate(path: Path, effectiveness: float, fault: str | None, attempt: int, seed: int,
             out_dir: Path, samples: int | None, repair_target: str | None = None,
             baseline_csv: Path | None = None):
    effectiveness = max(0.0, min(1.0, float(effectiveness)))
    offsets, timestamps = estimate_fault_offset(path, baseline_csv)
    n = samples or len(timestamps) or 600

    # 复测数据从源数据末点之后 GAP_SECONDS 开始
    last_ts = timestamps[-1] if timestamps else datetime(2026, 10, 9, 8, 0, 0).isoformat()
    try:
        start = datetime.fromisoformat(last_ts) + timedelta(seconds=GAP_SECONDS)
    except ValueError:
        start = datetime.now().replace(microsecond=0)

    # repair_target = 这次维修实际针对的故障（默认等于诊断故障）。
    # 若它与真实故障不同（即"错误诊断"），则只有该故障特征覆盖的测点被修复，
    # 其余测点的偏移原样保留 -> 维修后仍能被检出残留异常。
    target = repair_target if repair_target in FAULT_LIBRARY else fault
    entry = FAULT_LIBRARY.get(target, {})
    addressed = set(entry.get("signature", {}))
    typical = entry.get("typical_delta", {})

    # 本次维修能消除的偏移：取「实际偏移」与「该故障典型偏移」的较小者。
    # 含义：按某个故障去修，只能消除这个故障所能解释的那部分异常。
    # 因此若诊断错了，超出该故障解释能力的偏移会原样残留，验证必然不通过。
    residual = {}
    for name, value in offsets.items():
        if name in addressed and target:
            explainable = typical.get(name)
            restorable = abs(value) if explainable is None else min(abs(value), abs(explainable))
            restorable *= 1.0 if value >= 0 else -1.0
            residual[name] = value - effectiveness * restorable
        else:
            residual[name] = value
    rng = random.Random(seed)

    rows = []
    for i in range(n):
        t = float(i)
        row = {"timestamp": (start + timedelta(seconds=i)).isoformat(timespec="seconds")}
        for key in COLUMNS[1:]:
            amplitude, period = CYCLE[key]
            value = BASE[key] + amplitude * math.sin(2.0 * math.pi * t / period)
            value += residual.get(key, 0.0)
            value += rng.gauss(0.0, NOISE[key])
            row[key] = round(value, 3 if key == "pressure_mpa" else 2)
        rows.append(row)

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem
    csv_name = f"{stem}_repair_e{effectiveness:.2f}_a{attempt}.csv"
    csv_path = out_dir / csv_name
    meta_path = out_dir / f"{stem}_repair_e{effectiveness:.2f}_a{attempt}.json"
    write_csv(csv_path, rows)

    meta = {
        "tool": "simulate_repair",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": _display_path(path),
        "source_name": path.name,
        "baseline_source": _display_path(baseline_csv) if baseline_csv else None,
        "output_csv": _display_path(csv_path),
        "fault": fault,
        "fault_name": FAULT_LIBRARY[fault]["name"] if fault in FAULT_LIBRARY else None,
        "repair_target": repair_target or fault,
        "repair_target_name": (FAULT_LIBRARY[repair_target]["name"]
                               if repair_target in FAULT_LIBRARY else None),
        "addressed_sensors": sorted(addressed),
        "effectiveness": effectiveness,
        "attempt": attempt,
        "seed": seed,
        "samples": n,
        "start_time": start.isoformat(timespec="seconds"),
        "estimated_fault_offset": {k: round(v, 4) for k, v in offsets.items()},
        "residual_offset": {k: round(v, 4) for k, v in residual.items()},
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "tool": "simulate_repair",
        "status": "simulated",
        "source": path.name,
        "fault": fault,
        "fault_name": meta["fault_name"],
        "repair_target": meta["repair_target"],
        "repair_target_name": meta["repair_target_name"],
        "effectiveness": effectiveness,
        "attempt": attempt,
        # output_csv 供下游读写使用（真实可访问路径）；
        # output_csv_rel / metadata_json 是给证据与展示用的相对路径（不含用户名）。
        "output_csv": str(csv_path),
        "output_csv_rel": _display_path(csv_path),
        "metadata_json": _display_path(meta_path),
        "samples": n,
        "start_time": meta["start_time"],
        "estimated_fault_offset": meta["estimated_fault_offset"],
        "residual_offset": meta["residual_offset"],
        "next_step": "调用 verify_repair 对比维修前后数据并判断维修是否成功",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="模拟执行维修并生成复测数据")
    parser.add_argument("csv", help="维修前的传感器 CSV")
    parser.add_argument("--effectiveness", type=float, default=1.0, help="修复效果 0~1（1=完全修复）")
    parser.add_argument("--fault", default=None, help="故障类型（默认自动诊断）")
    parser.add_argument("--attempt", type=int, default=1, help="第几次维修尝试")
    parser.add_argument("--repair-target", default=None,
                        help="本次维修实际针对的故障（用于模拟错误诊断；默认等于诊断故障）")
    parser.add_argument("--seed", type=int, default=20261009)
    parser.add_argument("--samples", type=int, default=None, help="复测采样点数（默认与源数据一致）")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--baseline-csv", dest="baseline_csv", default=None,
                        help="以该文件的前 120 点为基线估计故障偏移（用于分析复测数据）")
    parser.add_argument("--json", dest="json_out")
    args = parser.parse_args()

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"file not found: {path}")

    fault = args.fault
    if fault is None:
        from fault_diagnose import diagnose  # 延迟导入，避免无谓开销
        diag = diagnose(path, 120.0, 4.0)
        primary = diag.get("primary_diagnosis")
        fault = primary["fault"] if primary else None

    report = simulate(path, args.effectiveness, fault, args.attempt, args.seed,
                      Path(args.out_dir), args.samples, args.repair_target,
                      Path(args.baseline_csv) if args.baseline_csv else None)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())