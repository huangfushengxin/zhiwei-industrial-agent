#!/usr/bin/env python3
"""生成第 4 份测试 CSV：模拟维修成功（对 test_02 做 100% 修复后的复测数据）.

与 test_03_repair_failed.csv 形成对照：
    test_02(维修前) + test_04(维修后, 100% 修复)  -> 验证通过
    test_02(维修前) + test_03(维修后,  40% 修复)  -> 验证未通过
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from simulate_repair import simulate  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data" / "test"


def main() -> int:
    before = OUT / "test_02_bearing_fault.csv"
    if not before.exists():
        raise SystemExit(f"缺少 {before}（先运行 make_test_csvs.py）")

    tmp = OUT / "_tmp_repair_ok"
    sim = simulate(before, 1.0, "bearing_wear", 1, 20261014, tmp, None, "bearing_wear")
    dst = OUT / "test_04_repair_success.csv"
    shutil.copyfile(sim["output_csv"], dst)
    shutil.rmtree(tmp, ignore_errors=True)
    rows = len(dst.read_text(encoding="utf-8").strip().splitlines()) - 1
    print(f"[ok] {dst.name}  {rows} 行  <- 模拟维修成功（100% 修复）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())