# reviews/P1-A2-v11

P1-A2（裸 DSML 清理）第四版审查材料。v10 复审提出四条问题，v11 修复；v8–v10 原包均保留。

基线：`p1-a1-v6` @ `bc04462`；修订基线：`p1-a2-v10` @ `ce2b90f`。

## 这一轮改了什么

1. **非法候选隔离贯穿整个扫描**：新增 `_candidate_regions()`，隔离区间并入 `skip`；
   主循环、`_match_r1()` 栈扫描、普通 XML 清理统一跳过，不再只在 R1 里移动局部游标。
2. **UNCLOSED_SINGLE 重扫问题**：删除外层起始标签后，隔离区间仍被跳过；候选之后的普通正文照常处理。
3. **有区分力的测试**：新增 12 项，用 `KEEP_ME`、`INNER`、`TAIL` 等正文断言保留，
   不只断言 DSML 字符串消失。
4. **R1-c / MISMATCH / skip_to 组合**：只删外层起始标签；错名不删正文；skip_to 用引号感知终点。

配套：R1 入口与栈内扫描改为先认标签名、再扫属性；裸标记（无尖括号）不进入 R1 栈。

## 文件

| 文件 | 作用 |
|---|---|
| `交付报告.md` | 四条修复、测试、证据边界、SHA |
| `v10到v11-代码.patch` | 源码增量 diff（相对 v10，+61 / −17） |
| `v10到v11-测试.patch` | 测试增量 diff（相对 v10，+45 / −8） |
| `v6到v11-代码.patch` | 源码完整 diff（相对 v6） |
| `完整diff.patch` | 源码 + 测试完整 diff（v6 → v11） |
| `测试日志.txt` | 命令、环境、退出码、逐项输出（190 项） |
| `snapshot/` | v11 源码、v11 测试 |
| `baseline/` | v6 源码、v6 测试、**multi_bubble 线上副本** |

## 复现

`multi_bubble.py` 不依赖旧测试目录遗留文件；材料里带了线上副本：

- 来源：`/opt/astrbot/data/plugins/astrbot_plugin_multi_bubble/main.py`
- SHA256：`5e2519320edac1da19c6c9a2930c4ac1ffe032f485bb63a0ac2c863fe1f33f4c`
- 未修改；`baseline/astrbot_plugin_multi_bubble/main.py` 与之逐字节一致。

```bash
docker exec astrbot mkdir -p /tmp/rbtest_p1a
docker cp snapshot/astrbot_plugin_tool_xml_guard/main.py astrbot:/tmp/rbtest_p1a/tool_xml_guard.py
docker cp baseline/astrbot_plugin_multi_bubble/main.py    astrbot:/tmp/rbtest_p1a/multi_bubble.py
docker cp snapshot/测试/test_out_guard.py                  astrbot:/tmp/test_out_guard.py
docker exec -w /AstrBot -e PYTHONPATH=/AstrBot -e RB_DIR=/tmp/rbtest_p1a \
    astrbot timeout 120 python -u /tmp/test_out_guard.py
```

## 证据边界

`GuardEv` / `MBCtx` 是隔离测试替身：`stop_event()` 只置布尔并清空 `chain`，`send_message()` 只记录文本。
它们证明的是清洗器的调用与链状态，**不是真实 QQ 发送管道**。未部署，无真机 E2E。详见交付报告第五节。

## 状态

**未部署、未重启。** 材料不含密钥、数据库、真实聊天内容。
