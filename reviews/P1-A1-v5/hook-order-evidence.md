# 钩子顺序证据（v5，可复核扫描）

> 结论：AstrBot 的 handler 按 `-priority` 排序（priority **大**的先执行）。
> v5 把 `tool_xml_guard` 改成 **-1000000**，部署后它在 8 个静态注册点里排最后。
> 下面给出：可复核扫描脚本、线上/部署后两张表、AstrBot 排序实现与版本、以及**覆盖边界**。

## 一、复现方式

```bash
docker cp scan_hooks.py astrbot:/tmp/scan_hooks.py
docker exec -w /AstrBot -e PYTHONPATH=/AstrBot astrbot \
    python3 /tmp/scan_hooks.py --root /AstrBot/data/plugins --json /tmp/hook-scan.json
```

脚本输出每个注册点的插件名、priority、源码行号、`main.py` 的 sha256；同一份 JSON 在 `hook-scan.json`。

## 二、线上现状（部署前，8 个注册点）

| 序 | 插件 | priority | 行号 | main.py sha256(前12) |
|---|---|---|---|---|
| 1 | `astrbot_plugin_meme_manager` | 99999 | 357 | `dd6616ca31ee` |
| 2 | `astrbot_plugin_tool_xml_guard` | 100 | 79 | `665eabb4ccf3` |
| 3 | `astrbot_plugin_style_strip` | 90 | 84 | `bb2e99845f01` |
| 4 | `astrbot_plugin_face_map` | 80 | 63 | `15b733c9b9f3` |
| 5 | `astrbot_plugin_rule_guard` | 80 | 454 | `fe69f983026d` |
| 6 | `astrbot_plugin_recall_guard` | 70 | 97 | `3d2519ad4d8a` |
| 7 | `astrbot_plugin_quote_reply` | 60 | 29 | `979b4bfa9ee2` |
| 8 | `astrbot_plugin_chuanhuatong` | -10 | 390 | `7f6baa86449d` |

线上 `tool_xml_guard` 位次 = [2]（第 2 个执行，因为还是旧 priority=100）

## 三、部署后预期（把 snapshot 的 -1000000 代入同一排序）

| 序 | 插件 | priority | 来源 |
|---|---|---|---|
| 1 | `astrbot_plugin_meme_manager` | 99999 | 线上 |
| 2 | `astrbot_plugin_style_strip` | 90 | 线上 |
| 3 | `astrbot_plugin_face_map` | 80 | 线上 |
| 4 | `astrbot_plugin_rule_guard` | 80 | 线上 |
| 5 | `astrbot_plugin_recall_guard` | 70 | 线上 |
| 6 | `astrbot_plugin_quote_reply` | 60 | 线上 |
| 7 | `astrbot_plugin_chuanhuatong` | -10 | 线上 |
| 8 | `astrbot_plugin_tool_xml_guard` | -1000000 | snapshot(v5) |

部署后 `tool_xml_guard` 位次 = 8 / 8（最后执行）。

## 四、AstrBot 排序实现

- 版本：**4.29.4**
- `star_handler.py` sha256：`0e84e9cf028632661cfd07cdcdcaba4fe4134e140320a23f2f617280e9ccf1df`
- 排序语句：`self._handlers.sort(key=lambda h: -h.extras_configs["priority"])`

`get_handlers_by_event_type()` 直接按 `_handlers` 顺序返回（不再排序），
`ResultDecorateStage.process` 按该顺序依次 `await handler.handler(event)`。
⇒ 执行顺序 = priority 降序；最小 priority 最后执行。

## 五、覆盖边界（必须如实告知）

- 只扫 astrbot_plugin_*/main.py 的静态装饰器
- 不覆盖动态注册、别名导入、其它文件里的注册、内置 handler

因此本证据能证明：**静态可见的 8 个注册点里，部署后清理钩子最后执行**。
不能证明：运行时集合里没有通过动态注册/别名/其它文件注册的装饰钩子——
当前 AstrBot 版本没有暴露注册表读取接口，无法 dump 线上进程内的完整集合。
若审查要求「运行时完整集合」，需要先在 AstrBot 加一个只读诊断口（本轮未做）。
