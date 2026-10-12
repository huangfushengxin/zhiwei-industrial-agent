# Day 2 记录 —— 工业数据 + 工具 + AGH 调用打通（智维 · AI 工业设备智能运维 Agent）

日期：2026-10-09

## 一、Day 2 目标

| # | 任务 | 状态 |
|---|---|---|
| 1 | 生成工业设备传感器 CSV | 完成 |
| 2 | 做异常检测工具 | 完成 |
| 3 | 做故障诊断工具 | 完成 |
| 4 | 让 AGH 成功调用这些工具 | 完成 |

## 二、被监测对象

离心泵机组 P-101（电机 + 联轴器 + 离心泵 + 轴承座），采样 1 Hz，每场景 600 点。

| 测点 | 单位 | 正常基线 |
|---|---|---|
| 轴承温度 temperature_c | °C | 62.0 |
| 振动速度 vibration_mm_s | mm/s | 2.10 |
| 转速 speed_rpm | rpm | 2980 |
| 电机电流 current_a | A | 42.0 |
| 出口压力 pressure_mpa | MPa | 0.620 |
| 出口流量 flow_m3h | m³/h | 55.0 |

生成 5 个工况数据集：`normal`、`bearing_wear`（轴承磨损）、`misalignment`（不对中/不平衡）、
`overload`（过载/卡涩）、`cavitation`（气蚀/入口堵塞）。故障在第 180 秒开始、按斜坡增强，
模拟真实缓变故障。

## 三、工具设计

### 3.1 异常检测 `tools/anomaly_detect.py`

- 方法：**基线比对 + 局部滚动中位数 + 鲁棒 z 分数（中位数 / MAD）**
- 为什么要滚动中位数：真实工况本身有周期性缓慢波动（负载、环境温度）。
  第一版直接用全局基线，把正常波动误判成了异常（误报）；改用局部滚动中位数
  先吸收周期趋势后，正常场景误报降为 0。
- 区分两类异常：**持续偏移**（缓变故障，要求连续 ≥5 点）与**瞬时尖峰**（噪声/冲击）。
- 输出：异常测点、时间区间、偏移倍率、严重等级、预期区间。

### 3.2 故障诊断 `tools/fault_diagnose.py`

- 方法：把各测点「持续偏移的方向 + 相对强度」组成特征向量，与故障特征库做**余弦相似度**匹配。
- 关键设计：只有被判为持续偏移的测点才进入特征向量；偏移强度保留相对大小（饱和 50σ），
  因此能区分「振动暴涨但温度只微升」（不对中）与「振动/温度同步上升」（轴承磨损）。
- 输出：排序后的故障候选、置信度、判据证据、推荐维修动作、涉及部件、健康度指数。

### 3.3 MCP 工具服务 `agent/mcp/zhiwei_mcp_server.py`

用官方 MCP Python SDK（mcp 2.3.0）把上述能力暴露为 5 个 MCP 工具：

| 工具 | 作用 |
|---|---|
| `list_scenarios` | 列出可用工况数据集 |
| `read_sensor_summary` | 传感器统计摘要 |
| `detect_anomalies` | 异常检测 |
| `diagnose_fault` | 故障诊断 |
| `analyze_equipment` | 一键：异常检测 + 故障诊断 |

所有工具声明 `readOnlyHint: true`（只读取/分析，不修改文件）。

## 四、AGH 集成过程（含踩坑）

1. 注册服务：
   `agh mcp add zhiwei-ops --name "智维工业运维工具" --stdio <python.exe> --arg <zhiwei_mcp_server.py> --allow-tool ...`
2. 安全信任审核：`agh mcp trust zhiwei-ops --expected-revision <rev>`
3. 启用：`agh mcp enable zhiwei-ops --expected-revision <rev>`
4. 检查：`agh mcp status` → `connection=ready tools=5`；`agh mcp tools` 能看到 5 个工具。

**踩坑记录：** 第一次让 Agent 调用工具时被拒绝，原因是当前 profile `approvals.mode = manual`，
非交互（`-p`）模式下无人可审批。排查 AGH 源码后确认：**MCP 工具必须声明 `readOnlyHint: true`
才会被识别为只读并免于写入类审批**。给工具补上注解并 `mcp reconnect` 后，调用即成功。

## 五、验证结果

流水线验证（`tools/validate_pipeline.py`，诊断结果与真值比对）：

| 场景 | 期望 | 诊断 | 置信度 | 健康度 | 结果 |
|---|---|---|---|---|---|
| normal | normal | normal | - | 100 | PASS |
| bearing_wear | bearing_wear | bearing_wear | 0.993 | 25 | PASS |
| misalignment | misalignment | misalignment | 1.0 | 25 | PASS |
| overload | overload | overload | 0.933 | 20 | PASS |
| cavitation | cavitation | cavitation | 0.946 | 10 | PASS |

**准确率 5/5 = 100%**（报告见 `validation-report.json`）。

## 六、AGH 实跑证据

会话 ID：`agnes:local:local-dev:cli:workspace:b065f67285df612d`

给 Agent 的指令：

> 离心泵机组 P-101 的在线监测系统刚刚报警。请使用你可用的工业运维工具，对
> data/sensor_overload.csv 完成异常检测与故障诊断，并给出：1) 设备健康度
> 2) 故障结论与判据 3) 建议的维修动作。

Agent 行为（工具调用链）：

    - tool mcp_zhiwei_ops_ce653d54_analyze_equipment
    - tool mcp_zhiwei_ops_ce653d54_analyze_equipment · ok · 320ms

Agent 结论：健康度 20/100，严重异常，诊断为「负载过大 / 转动部件卡涩」（置信度 0.933，
特征匹配 4/4），并给出三条维修动作与涉及部件。**这证明 AGH 不只是文本回答，而是真正调用了工具。**

## 七、目录结构

    AI-Industrial-Agent/
      data/                      传感器数据（5 场景 + scenarios.json）
      tools/                     工业工具（生成/异常检测/诊断/验证）
      agent/mcp/                 MCP 工具服务 + 协议自检客户端
      evidence/day1/             Day 1 记录
      evidence/day2/             Day 2 记录（本文 + 执行记录 + 验证报告）

## 八、已知边界

- 故障特征库目前为 4 类规则化特征，后续可扩展；
- 异常检测阈值（4σ / 饱和 50σ）基于当前数据标定，换设备需重新标定；
- 当前为离线数据回放，尚无真实传感器/PLC 接入。

## 九、下一步（Day 3）

打通完整闭环：数据读取 → 异常检测 → 故障诊断 → 维修方案 → 模拟维修 → 维修后数据验证。