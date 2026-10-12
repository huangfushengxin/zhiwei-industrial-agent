# Day 4 记录 —— 验证与异常恢复（错误诊断 → 验证失败 → 重新规划 → 修复成功）

日期：2026-10-09

## 一、Day 4 目标与完成情况

| # | 任务 | 状态 |
|---|---|---|
| 1 | 比较维修前后数据 | 完成（Day 3 的 `verify_repair`） |
| 2 | 判断维修是否成功 | 完成（success / partial / failed） |
| 3 | **故意制造一次错误诊断** | 完成（新增 `repair_target` 能力） |
| 4 | 验证失败 → Agnes 重新规划 → 再次维修 → 验证成功 | 完成 |
| 5 | 保存 AGH 工具调用链和执行记录 | 完成 |

## 二、新增能力：让「修错地方」真实可验证

### 2.1 `repair_target`：显式指定本次维修针对的故障

`simulate_repair` 新增 `repair_target` 参数（默认等于诊断结论）。若它和真实故障不同，
就等价于"按错误诊断去修"。

### 2.2 修复模型修正（本日关键技术点）

第一版模型是"目标故障特征覆盖的测点全部修复"。实测发现一个真实问题：
**轴承磨损与不对中的特征测点完全相同**（振动 / 温度 / 电流），
于是"把轴承磨损误判成不对中"照样能修好，无法产生失败。

改为按"该故障能解释的幅度"抵消：

    可消除偏移 = min( 实际偏移 , 该故障的典型偏移 )
    残留偏移   = 实际偏移 − effectiveness × 可消除偏移

知识库 `fault_library.py` 因此新增 `typical_delta` 字段（各故障满强度下的典型偏移量）。
含义很直观：**按某个故障去修，只能消除这个故障所能解释的那部分异常。**

修正后：轴承磨损被误判为不对中 → 温度只被消掉 7°C（不对中能解释的量），
残留 12°C 温升仍被检出 → 验证不通过。✅

## 三、验收结果

`tools/validate_day4.py` —— **异常恢复通过率 4/4 = 100%**

| 场景 | 真实故障 | 误判为 | 第 1 次维修 | 残留 | 第 2 次维修 | 健康度 |
|---|---|---|---|---|---|---|
| bearing_wear | 轴承磨损 | 不对中 | partial | 23.92σ | success | 25→100 |
| misalignment | 不对中 | 轴承磨损 | partial | 35.61σ | success | 25→100 |
| overload | 过载 | 轴承磨损 | **failed** | 28.51σ | success | 20→100 |
| cavitation | 气蚀 | 不对中 | partial | 38.90σ | success | 10→100 |

同时回归验证：Day 2 诊断 5/5、Day 3 闭环 6/6 均未受影响。

## 四、AGH 端到端证据

会话：`agnes:local:local-dev:cli:workspace:b1091fd773a74edb`
记录：`agh-day4-misdiagnosis-recovery.{html,json}`

Agent 自主完成的工具调用链：

    detect_anomalies   -> critical，4 测点持续偏移
    diagnose_fault     -> 主判 overload(0.933) / 次选 bearing_wear(0.819)
    simulate_repair    -> repair_target=bearing_wear（故意误判）  [attempt 1]
    verify_repair      -> failed，残留 28.52σ，residual_fault=overload(0.859)
    simulate_repair    -> repair_target=overload（重新规划）      [attempt 2]
    verify_repair      -> success，残留 1.28σ

| 轮次 | repair_target | 验证结果 | 最大残留 | 健康度 |
|---|---|---|---|---|
| 1（误判） | bearing_wear | **failed** | 28.52σ（电机电流） | 50 |
| 2（纠错） | overload | **success** | 1.28σ（转速） | **100** |

Agent 的纠错推理（原文要点）：电流 +28.52σ 与转速 -22.4σ 这两个 overload 独有测点完全没回来，
`residual_fault` 指向 overload → **判定第一轮维修目标错误** → 改回主判候选。
并总结出可操作教训：特征匹配 4/4 与 3/3 应作为硬性权重；电流+转速同时偏移时优先排查负载类故障。

健康度轨迹：**20 → 50 → 100**

## 五、踩坑记录

**AGH 的 MCP 工具 schema 是会话级缓存的。** 修改工具参数后，即使重新连接 MCP 服务、
catalog 哈希也更新了，**已有会话仍看到旧 schema**（Agent 老实报告"没有 repair_target 参数"，
没有编造调用结果）。解决方式：**开启新会话**后立刻生效。

排查路径：先用独立 MCP 客户端确认服务端 schema 确实包含新参数，再定位到 AGH 会话级缓存。

## 六、已知边界

- `typical_delta` 目前取自仿真数据的设定值；接真实设备时需用历史维修案例标定；
- 错误诊断的制造方式是"指定错误的 repair_target"，属于受控演示，
  真实场景中错误诊断来自模型判断，本工具只是提供了可复现的验证手段；
- 仍未接入真实传感器/PLC。

## 七、下一步（Day 5）

展示：简单网页、Agent 执行时间线、正常/边界/失败三个测试案例、
保存 AGH 工具调用链与执行记录、录制 3–5 分钟演示视频。
本日的错误诊断与恢复案例，正好作为 Day 5 的"失败案例"素材。