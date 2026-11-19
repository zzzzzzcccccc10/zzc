# reviews/P1-A2-v8

P1-A2（裸 DSML 清理）审查材料。基于 `p1-a1-v6` @ `bc04462`。

## 这一轮做了什么

按 `DECISIONS/P1-A2-裸DSML清理规范.md`（v7 定稿）与 `DECISIONS/P1-A2-施工方案.md`（v4 复审通过 @ `4efbfc140e757ef8e2b14928e8633907d33be3f8`）重写 `tool_xml_guard` 的清理核心：

- 保护区扩为 CODE（围栏 + 行内代码）与 QUOTE（同段落成对引号），叠加 SYNTAX 区间排除属性引号；
- R1 改成严格栈式配对，七种异常状态各有独立行为；
- R2/R3 按显式形态匹配（双竖线 / 单竖线、带尖括号 / 裸标记）；
- 属性扫描三状态（`FOUND_END` / `UNTERMINATED_ATTRIBUTE` / `MISSING_END`）；
- fail-closed 沿用：清洗异常 → `_stop(event, …)`，发送次数 0。

`multi_bubble` 未动。

## 文件

| 文件 | 作用 |
|---|---|
| `交付报告.md` | 实现结构、测试、旧期望调整、**复审重点**、范围与 SHA |
| `v6到v8-代码.patch` | 源码增量 diff（+505 / −54） |
| `v6到v8-测试.patch` | 测试增量 diff（+121 / −6） |
| `完整diff.patch` | 代码 + 测试的完整 diff（897 行） |
| `测试日志.txt` | 命令、环境、退出码、26 组逐项输出（142 项） |
| `snapshot/` | 新源码、新测试 |
| `baseline/` | v6 源码、v6 测试 |

## 复现

```bash
docker cp snapshot/astrbot_plugin_tool_xml_guard/main.py astrbot:/tmp/rbtest_p1a/tool_xml_guard.py
docker cp snapshot/测试/test_out_guard.py                astrbot:/tmp/test_out_guard.py
docker exec -w /AstrBot -e PYTHONPATH=/AstrBot -e RB_DIR=/tmp/rbtest_p1a \
    astrbot timeout 120 python -u /tmp/test_out_guard.py
```

## 状态

**未部署、未重启。** 本材料只包含源码、测试与日志；不含密钥、数据库、真实聊天内容。
