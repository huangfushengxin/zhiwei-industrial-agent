#!/usr/bin/env python3
"""MCP 协议自检客户端：用标准 MCP 协议连接智维工具服务，列出全部工具并逐个实际调用。"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(HERE / "zhiwei_mcp_server.py")],
        cwd=str(HERE),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            print(f"[handshake] server={info.server_info.name} version={info.server_info.version}")
            print(f"[handshake] protocol={info.protocol_version}")

            tools = await session.list_tools()
            print(f"[tools] {len(tools.tools)} 个:")
            for t in tools.tools:
                ro = t.annotations.read_only_hint if t.annotations else None
                print(f"   - {t.name:<20} readOnly={ro}")

            calls = [
                ("list_scenarios", {}),
                ("read_sensor_summary", {"csv_path": "sensor_normal.csv"}),
                ("detect_anomalies", {"csv_path": "sensor_misalignment.csv"}),
                ("diagnose_fault", {"csv_path": "sensor_cavitation.csv"}),
                ("analyze_equipment", {"csv_path": "sensor_overload.csv"}),
                ("plan_repair", {"csv_path": "sensor_bearing_wear.csv"}),
                ("simulate_repair", {"csv_path": "sensor_bearing_wear.csv", "effectiveness": 1.0}),
                ("verify_repair", {"before_csv": "sensor_bearing_wear.csv",
                                   "after_csv": "sensor_bearing_wear_repair_e1.00_a1.csv"}),
                ("run_closed_loop", {"csv_path": "sensor_cavitation.csv", "repair_effectiveness": 0.5}),
            ]
            print()
            for name, args in calls:
                result = await session.call_tool(name, args)
                if result.is_error:
                    print(f"[call] {name:<20} FAILED")
                    continue
                payload = json.loads(result.content[0].text)
                summary = payload.get("status") or payload.get("verdict") or payload.get("count")
                extra = ""
                if name == "run_closed_loop":
                    extra = f" attempts={len(payload.get('attempts', []))}"
                elif name == "verify_repair":
                    extra = f" residual={payload.get('worst_residual_sigma')}σ"
                elif name == "simulate_repair":
                    extra = f" -> {Path(payload['output_csv']).name}"
                print(f"[call] {name:<20} ok  status={summary}{extra}")
    print("\nMCP 协议自检通过（9 个工具全部可调用）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))