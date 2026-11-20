# reviews/P1-A2-v13

P1-A2（裸 DSML 清理）第六版审查材料。v12 复审提出最小返修，v13 修复；v8–v12 原包均保留。

基线：`p1-a1-v6` @ `bc04462`；修订基线：`p1-a2-v12` @ `54ae3a9`。

## 这一轮改了什么

1. **修 `_syntax_regions()` 普通 XML 第二轮扫描**：起始标签改用 `_scan_attrs()`，
   单/双引号属性里的 `>` 不再截断 SYNTAX 区间；闭合标签用匹配末尾。
2. **补 6 项回归**：单引号/双引号属性伪候选、单/双引号属性含 `>`、DSML 单引号属性伪候选、
   属性伪候选 + 后续合法结构；断言整段清理结果为 `""`（INNER 随普通 XML 一起删）。
3. **回归**：v12 的 5 项、v11 的 KEEP_ME 案例、v7 的 31 条规范案例全部继续 PASS。

`multi_bubble` 未修改。

## 文件

| 文件 | 作用 |
|---|---|
| `交付报告.md` | 修复、测试、证据边界、SHA |
| `v12到v13-代码.patch` | 源码增量 diff（相对 v12，+21 / −12） |
| `v12到v13-测试.patch` | 测试增量 diff（相对 v12，+17 / 0） |
| `v6到v13-代码.patch` | 源码完整 diff（相对 v6） |
| `完整diff.patch` | 源码 + 测试完整 diff（v6 → v13） |
| `测试日志.txt` | 命令、环境、退出码、逐项输出（201 项） |
| `snapshot/` | v13 源码、v13 测试 |
| `baseline/` | v6 源码、v6 测试、**multi_bubble 线上副本** |

## 复现

以下命令都在 **`reviews/P1-A2-v13/` 目录下**执行（`snapshot/`、`baseline/` 都是相对路径）：

```bash
cd reviews/P1-A2-v13
docker exec astrbot mkdir -p /tmp/rbtest_p1a
docker cp snapshot/astrbot_plugin_tool_xml_guard/main.py astrbot:/tmp/rbtest_p1a/tool_xml_guard.py
docker cp baseline/astrbot_plugin_multi_bubble/main.py    astrbot:/tmp/rbtest_p1a/multi_bubble.py
docker cp snapshot/测试/test_out_guard.py                  astrbot:/tmp/test_out_guard.py
docker exec -w /AstrBot -e PYTHONPATH=/AstrBot -e RB_DIR=/tmp/rbtest_p1a \
    astrbot timeout 120 python -u /tmp/test_out_guard.py
```

`multi_bubble.py` 来源：`/opt/astrbot/data/plugins/astrbot_plugin_multi_bubble/main.py`，
SHA256 `5e2519320edac1da19c6c9a2930c4ac1ffe032f485bb63a0ac2c863fe1f33f4c`，未修改。

## 测试计数

- v12 新增 5 项 → 190 → 195。
- v13 新增 6 项 → 195 → **201**。
- 当前：**31 组 201 项 ALL PASS**。

## 证据边界

`GuardEv` / `MBCtx` 是隔离测试替身，不是真实 QQ 发送管道；未部署，无真机 E2E。详见交付报告第五节。

## 状态

**未部署、未重启。** 线上仍是 P1-A1 v6，`tool_xml_guard/main.py` SHA256 前缀 `c4497e04…`。
P1-A1 三条 PENDING 不变；P1-A2 另外九个直发点也没有因此解决。
