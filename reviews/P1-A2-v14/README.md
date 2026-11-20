# reviews/P1-A2-v14

P1-A2（裸 DSML 清理）第七版审查材料。v13 复审阻断项已修，v8–v13 原包均保留。

基线：`p1-a1-v6` @ `bc04462`；修订基线：`p1-a2-v13` @ `6ae856c`。

## 这一轮改了什么

1. **修 `_syntax_regions()` 第二轮不尊重第一轮 DSML SYNTAX**：第二轮开始前保存第一轮区间；
   命中的 `<invoke` / `</invoke>` 若落在已有 DSML 区间内，直接跳到区间末尾，不再生成伪普通 XML 区间。
2. **修 `_xml_deletions()` 的保护集合**：只把 DSML 的 SYNTAX 传给它，不把普通 XML 自身的 SYNTAX
   也保护进去，否则后面的合法 `<invoke>X</invoke>` 不会被清理。
3. **新增 3 项回归**：复审触发输入、触发输入 + 后续合法结构、单引号属性内伪 `<invoke>`。

`multi_bubble` 未修改。

## 文件

| 文件 | 作用 |
|---|---|
| `交付报告.md` | 修复、测试、证据边界、SHA |
| `v13到v14-代码.patch` | 源码增量 diff（相对 v13，+28 / −4） |
| `v13到v14-测试.patch` | 测试增量 diff（相对 v13，+16 / 0） |
| `v6到v14-代码.patch` | 源码完整 diff（相对 v6） |
| `完整diff.patch` | 源码 + 测试完整 diff（v6 → v14） |
| `测试日志.txt` | 命令、环境、退出码、逐项输出（204 项） |
| `snapshot/` | v14 源码、v14 测试 |
| `baseline/` | v6 源码、v6 测试、**multi_bubble 线上副本** |

## 复现

以下命令都在 **`reviews/P1-A2-v14/` 目录下**执行（`snapshot/`、`baseline/` 都是相对路径）：

```bash
cd reviews/P1-A2-v14
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

- v13：201 项 → v14：**204**（新增 3 项）。
- 当前：**32 组 204 项 ALL PASS**。

## 证据边界

`GuardEv` / `MBCtx` 是隔离测试替身，不是真实 QQ 发送管道；未部署，无真机 E2E。详见交付报告第五节。

## 状态

**未部署、未重启。** 线上仍是 P1-A1 v6，`tool_xml_guard/main.py` SHA256 前缀 `c4497e04…`。
P1-A1 三条 PENDING 不变；P1-A2 另外九个直发点也没有因此解决。
