# reviews/P1-A2-v12

P1-A2（裸 DSML 清理）第五版审查材料。v11 复审提出最小返修范围，v12 修复；v8–v11 原包均保留。

基线：`p1-a1-v6` @ `bc04462`；修订基线：`p1-a2-v11` @ `f066cf9`。

## 这一轮改了什么

1. **修 `_candidate_regions()` 对 QUOTE / SYNTAX 的误识别**：
   - 跳过 CODE 与 QUOTE，引号内的伪候选不再被当成独立候选；
   - 被外层合法标签的 SYNTAX 区间包含的标记（属性值里的伪候选）不再被当成独立候选。
2. **修 `_syntax_regions()` 的过度生成**：只给合法语法单元生成 SYNTAX；
   非法候选、裸标记、非标签标记、异常闭合都不生成，避免没有 `>` 的候选把后面的引号全部吞掉。
3. **补两类回归**：引用内伪候选（有/无 `>`）、属性内伪候选（完整结构/无闭合），
   精确断言引用内容、属性正文和后续合法结构。
4. **README 补工作目录说明**，并统一新增测试数量。

`multi_bubble` 未修改。

## 文件

| 文件 | 作用 |
|---|---|
| `交付报告.md` | 修复、测试、计数更正、证据边界、SHA |
| `v11到v12-代码.patch` | 源码增量 diff（相对 v11，+40 / −12） |
| `v11到v12-测试.patch` | 测试增量 diff（相对 v11，+21 / 0） |
| `v6到v12-代码.patch` | 源码完整 diff（相对 v6） |
| `完整diff.patch` | 源码 + 测试完整 diff（v6 → v12） |
| `测试日志.txt` | 命令、环境、退出码、逐项输出（195 项） |
| `snapshot/` | v12 源码、v12 测试 |
| `baseline/` | v6 源码、v6 测试、**multi_bubble 线上副本** |

## 复现

以下命令都在 **`reviews/P1-A2-v12/` 目录下**执行（`snapshot/`、`baseline/` 都是相对路径）：

```bash
cd reviews/P1-A2-v12
docker exec astrbot mkdir -p /tmp/rbtest_p1a
docker cp snapshot/astrbot_plugin_tool_xml_guard/main.py astrbot:/tmp/rbtest_p1a/tool_xml_guard.py
docker cp baseline/astrbot_plugin_multi_bubble/main.py    astrbot:/tmp/rbtest_p1a/multi_bubble.py
docker cp snapshot/测试/test_out_guard.py                  astrbot:/tmp/test_out_guard.py
docker exec -w /AstrBot -e PYTHONPATH=/AstrBot -e RB_DIR=/tmp/rbtest_p1a \
    astrbot timeout 120 python -u /tmp/test_out_guard.py
```

`multi_bubble.py` 来源：`/opt/astrbot/data/plugins/astrbot_plugin_multi_bubble/main.py`，
SHA256 `5e2519320edac1da19c6c9a2930c4ac1ffe032f485bb63a0ac2c863fe1f33f4c`，未修改；
`baseline/astrbot_plugin_multi_bubble/main.py` 与之逐字节一致。

## 测试计数

- v11 的 `二十一` 组实际新增 **11 项**（v11 交付报告误写为 12 项，本版更正）。
- v12 新增 `二十二` 组 **5 项**。
- 当前总数：**30 组 195 项 ALL PASS**。

## 证据边界

`GuardEv` / `MBCtx` 是隔离测试替身：`stop_event()` 只置布尔并清空 `chain`，`send_message()` 只记录文本。
它们证明的是清洗器的调用与链状态，**不是真实 QQ 发送管道**。未部署，无真机 E2E。详见交付报告第五节。

## 状态

**未部署、未重启。** 线上仍是 P1-A1 v6，`tool_xml_guard/main.py` SHA256 前缀 `c4497e04…`。
P1-A1 三条 PENDING 不变；P1-A2 另外九个直发点也没有因此解决。
