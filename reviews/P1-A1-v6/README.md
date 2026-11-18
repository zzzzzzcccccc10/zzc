# reviews/P1-A1-v6

P1-A1（统一输出清洗）v6 审查材料。基于 `p1-a1-v5` @ `9a84dc71246c1d8b34da59417b82158dc9709ce3`。

## 这一轮只有一处代码修复

| 项 | 内容 |
|---|---|
| R5 | CRLF 下闭围栏识别失败：`close` 正则加 `\r?`，否则 `\r\n` 行尾匹配不到闭合行，围栏外控制标记逃过清洗 |
| 测试 | 新增 4 项 CRLF 回归（反引号 / 波浪线 / 代码块逐字保真 / 闭合行带空格） |

R1 逐字保真规范保持上一轮裁定；`multi_bubble` 未动。

## 文件

| 文件 | 作用 |
|---|---|
| `交付报告.md` | R5 根因、改法、测试、范围与遗留 |
| `v5到v6-*.patch` | **本轮增量 diff**（源码 640B、测试 1687B） |
| `完整diff.patch` | 相对原始 baseline 的完整 diff |
| `测试日志.txt` | 命令、环境、退出码、逐组数量、88 项原始输出 |
| `snapshot/`、`baseline/` | v6 源码、修改前源码 |
| `scan_hooks.py`、`hook-scan.json`、`hook-order-evidence.md` | hook 顺序证据（v6 未改 priority，沿用 v5） |

## 复现

```bash
docker cp snapshot/astrbot_plugin_tool_xml_guard/main.py astrbot:/tmp/rbtest_p1a/tool_xml_guard.py
docker cp snapshot/astrbot_plugin_multi_bubble/main.py   astrbot:/tmp/rbtest_p1a/multi_bubble.py
docker cp snapshot/测试/test_out_guard.py                astrbot:/tmp/test_out_guard.py
docker exec -w /AstrBot -e PYTHONPATH=/AstrBot -e RB_DIR=/tmp/rbtest_p1a \
    astrbot timeout 120 python -u /tmp/test_out_guard.py
```

未部署、未重启；材料不含密钥、数据库、真实聊天内容。
