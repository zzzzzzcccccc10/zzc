# reviews/P1-A2-v10

P1-A2（裸 DSML 清理）第三版审查材料。v9 复审提出三条实现/复现问题，v10 修复；v8、v9 原包均保留。

基线：`p1-a1-v6` @ `bc04462`；修订基线：`p1-a2-v9` @ `a280025`。

## 这一轮改了什么

1. **标准闭合异常分支改为引号感知扫描**：`text.find(">")` 换成 `_scan_attrs()`，
   属性值里的 `>` 不再截断 `skip_to`。同时覆盖 `_syntax_regions` 的闭合区间和主循环的孤立闭合跳点。
2. **非法新闭合候选整体跳过**：标记后以 `/` 开头但没通过严格校验的候选，在 R1 扫描里
   直接跳到候选终点（引号感知），不再从 `m["end"]` 逐字符继续扫描。
3. **README 复现步骤补 `mkdir -p /tmp/rbtest_p1a`**，并继续提供 `multi_bubble.py` 的来源与 SHA。

`multi_bubble` 未修改。

## 文件

| 文件 | 作用 |
|---|---|
| `交付报告.md` | 三条修复、测试、证据边界、SHA |
| `v9到v10-代码.patch` | 源码增量 diff（相对 v9，+17 / −7） |
| `v9到v10-测试.patch` | 测试增量 diff（相对 v9，+25 / 0） |
| `v6到v10-代码.patch` | 源码完整 diff（相对 v6） |
| `完整diff.patch` | 源码 + 测试完整 diff（v6 → v10） |
| `测试日志.txt` | 命令、环境、退出码、逐项输出（179 项） |
| `snapshot/` | v10 源码、v10 测试 |
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
