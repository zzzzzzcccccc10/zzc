# reviews/P1-A1-v5

P1-A1（统一输出清洗）v5 审查材料。基于 `p1-a1-v4` @ `25e1fed1ff00808220143a75fcc268c10f703e66`。

## 这一轮改了什么

| 项 | 内容 |
|---|---|
| R1 | 修 `_tidy_deleted()` 的全局行尾空格删除；改为只丢弃「删除后整行只剩空白」的行，其余逐字保留 |
| R2 | 新增 4 项「同一条消息部分清洗、其余逐字保留」测试 |
| R3 | 新增 5 项围栏边界测试（3/4 反引号交叉、反引号 vs 波浪线、关闭行带非空白、未闭合围栏假提案） |
| R4 | 提供可复核的 `scan_hooks.py` + 完整扫描 JSON + 两张顺序表 + 覆盖边界说明 |

只改 `tool_xml_guard/main.py` 与测试；`multi_bubble` 未动。

## 文件

| 文件 | 作用 |
|---|---|
| `交付报告.md` | R1–R4 逐条对应、空白规范、待裁定项、范围与遗留 |
| `完整diff.patch` | 相对原始 baseline 的完整 diff |
| `v4到v5-*.patch` | 相对 v4 的增量 diff（源码 / 测试） |
| `测试日志.txt` | 运行命令、环境、退出码、逐组数量、84 项原始输出 |
| `snapshot/` | v5 两个插件源码 + 测试源码 |
| `baseline/` | 修改前两个插件源码 |
| `scan_hooks.py` | hook 注册点扫描脚本（可复现） |
| `hook-scan.json` / `hook-scan-live.md` | 扫描结果（含每个 `main.py` 的 sha256） |
| `hook-order-evidence.md` | 线上表、部署后预期表、AstrBot 排序实现与版本、覆盖边界 |

## 复现

```bash
docker cp scan_hooks.py astrbot:/tmp/scan_hooks.py
docker exec -w /AstrBot -e PYTHONPATH=/AstrBot astrbot \
    python3 /tmp/scan_hooks.py --root /AstrBot/data/plugins --json /tmp/hook-scan.json

docker exec -w /AstrBot -e PYTHONPATH=/AstrBot -e RB_DIR=/tmp/rbtest_p1a \
    astrbot timeout 120 python -u /tmp/test_out_guard.py
```

## 说明

- 目录名用真实插件名 `astrbot_plugin_*`。
- 未部署、未重启；材料不含密钥、数据库、真实聊天内容。
- 待审查方裁定：标签位置的行尾空格是否也要修剪（见 `交付报告.md` 第一节末尾）。
