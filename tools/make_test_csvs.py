#!/usr/bin/env python3
"""生成三份演示/测试用 CSV（电机运行数据）.

  1) test_01_normal.csv          正常设备（健康基线，无异常）
  2) test_02_bearing_fault.csv   模拟轴承异常（轴承磨损，满强度）
  3) test_03_repair_failed.csv   模拟维修失败（按 40% 修复度维修后的复测数据，
                                 残留下 60% 的故障特征，验证必然不通过）

用法:
    python make_test_csvs.py
    python make_test_csvs.py --out-dir ../data/test
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_sensor_data import SCENARIOS, generate_rows, write_csv  # noqa: E402
from simulate_repair import simulate  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

NORMAL_SPEC = {"onset_s": None, "ramp_s": None, "delta": {}, "noise_gain": {}}
FAILED_REPAIR_EFFECTIVENESS = 0.4   # 只修好了 40%，剩下 60% 残留


def main() -> int:
    parser = argparse.ArgumentParser(description="生成三份测试 CSV")
    parser.add_argument("--out-dir", default=str(ROOT / "data" / "test"))
    parser.add_argument("--samples", type=int, default=600)
    args = parser.parse_args()

    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    # 1) 正常设备
    normal_path = out / "test_01_normal.csv"
    write_csv(normal_path, generate_rows(NORMAL_SPEC, args.samples, 20261011,
                                         datetime.fromisoformat("2026-10-11T08:00:00")))

    # 2) 轴承异常（轴承磨损，满强度）
    bearing_path = out / "test_02_bearing_fault.csv"
    write_csv(bearing_path, generate_rows(SCENARIOS["bearing_wear"], args.samples, 20261012,
                                          datetime.fromisoformat("2026-10-11T09:30:00")))

    # 3) 模拟维修失败：对轴承异常数据按 40% 修复度做"不彻底维修"，取复测数据
    tmp = out / "_tmp_repair"
    sim = simulate(bearing_path, FAILED_REPAIR_EFFECTIVENESS, "bearing_wear", 1, 20261013,
                   tmp, args.samples, "bearing_wear")
    failed_path = out / "test_03_repair_failed.csv"
    shutil.copyfile(sim["output_csv"], failed_path)
    shutil.rmtree(tmp, ignore_errors=True)

    manifest = {
        "asset": SCENARIOS["bearing_wear"].get("description", "离心泵机组 P-101"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sampling_hz": 1.0,
        "files": [
            {"file": normal_path.name, "case": "正常设备",
             "description": "健康基线，无故障",
             "expected_detect": "normal", "expected_diagnosis": None,
             "expected_verify": "无需维修"},
            {"file": bearing_path.name, "case": "模拟轴承异常",
             "description": "轴承磨损（滚动体/滚道损伤），满强度，第 180 秒起故障显现",
             "expected_detect": "critical", "expected_diagnosis": "bearing_wear",
             "expected_verify": "维修后应 success"},
            {"file": failed_path.name, "case": "模拟维修失败",
             "description": f"对「模拟轴承异常」数据按 {FAILED_REPAIR_EFFECTIVENESS:.0%} 修复度维修后的复测数据，"
                            f"残留 {(1-FAILED_REPAIR_EFFECTIVENESS):.0%} 故障特征",
             "expected_detect": "critical（以 test_02 为基线对比）",
             "expected_diagnosis": "bearing_wear（残留）",
             "expected_verify": "failed / partial（未通过）",
             "paired_before": bearing_path.name},
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                       encoding="utf-8")

    for item in manifest["files"]:
        p = out / item["file"]
        rows = len(p.read_text(encoding="utf-8").strip().splitlines()) - 1
        print(f"[ok] {item['file']:<28} {rows} 行  <- {item['case']}")
    print(f"\n输出目录: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())