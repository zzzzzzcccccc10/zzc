# reviews/P1-A2-v9

P1-A2（裸 DSML 清理）第二版审查材料。v8 复审**不通过**；v9 按 2026-11-20 裁定增加第二种闭合形式。
v8 原提交与审查包保留在 `p1-a2-v8` / `reviews/P1-A2-v8/`，未改动。

基线：`p1-a1-v6` @ `bc04462`；修订基线：`p1-a2-v8` @ `67b2f15`。

## 这一轮改了什么

按裁定新增受限闭合形式 `<｜｜DSML｜｜ /name>`，并把它接入原有严格栈式配对：

- 新形态必须带尖括号、双竖线；标记后至少一个空格/Tab；`/` 后紧跟完整白名单标签名；
  标签名后只允许空格/Tab 和 `>`（不允许属性或额外内容）。
- 错名仍按 R1-a 处理：不猜、不删。
- 标准闭合 `</｜｜DSML｜｜ name>` 同步收紧：标签名到 `>` 之间只允许空格/Tab；带属性的闭合按异常处理。
- `</<｜｜DSML｜｜ name>` 叠加形态保持 v8 兼容。
- 完整 LEAK 现在整段清理；DSML 提案（`/parameter>`、`/invoke>`）完整清理并入箱，消息不泄漏控制标记。

`multi_bubble` 未修改。

## 文件

| 文件 | 作用 |
|---|---|
| `交付报告.md` | v9 改动、测试、证据边界、SHA |
| `v8到v9-代码.patch` | 源码增量 diff（相对 v8） |
| `v8到v9-测试.patch` | 测试增量 diff（相对 v8） |
| `v6到v9-代码.patch` | 源码完整 diff（相对 v6） |
| `完整diff.patch` | 源码 + 测试完整 diff（v6 → v9） |
| `测试日志.txt` | 命令、环境、退出码、逐项输出（171 项） |
| `snapshot/` | v9 源码、v9 测试 |
| `baseline/` | v6 源码、v6 测试、**multi_bubble 线上副本** |

## 复现

`multi_bubble.py` 不依赖旧测试目录遗留文件；材料里带了线上副本，来源与 SHA 如下：

- 来源：`/opt/astrbot/data/plugins/astrbot_plugin_multi_bubble/main.py`
- SHA256：`5e2519320edac1da19c6c9a2930c4ac1ffe032f485bb63a0ac2c863fe1f33f4c`
- 未修改；`baseline/astrbot_plugin_multi_bubble/main.py` 与之逐字节一致。

```bash
docker cp snapshot/astrbot_plugin_tool_xml_guard/main.py astrbot:/tmp/rbtest_p1a/tool_xml_guard.py
docker cp baseline/astrbot_plugin_multi_bubble/main.py    astrbot:/tmp/rbtest_p1a/multi_bubble.py
docker cp snapshot/测试/test_out_guard.py                  astrbot:/tmp/test_out_guard.py
docker exec -w /AstrBot -e PYTHONPATH=/AstrBot -e RB_DIR=/tmp/rbtest_p1a \
    astrbot timeout 120 python -u /tmp/test_out_guard.py
```

## 证据边界

测试里的 `GuardEv` 是隔离构造的假事件：`stop_event()` 只置布尔并清空 `chain`，证明的是
「清洗器异常时会调用 stop_event 并清空链」，**不是真实发送管道**；`multi_bubble` 的 `MBCtx.sent`
也是假 Context 的记录。真实 QQ 端到端未做（未部署）。详见交付报告第五节。

## 状态

**未部署、未重启。** 材料不含密钥、数据库、真实聊天内容。
