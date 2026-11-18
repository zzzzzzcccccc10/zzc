root = /AstrBot/data/plugins
注册点数量 = 8

| 序 | 插件 | priority | 行号 | main.py sha256(前12) | 源码行 |
|---|---|---|---|---|---|
| 1 | `astrbot_plugin_meme_manager` | 99999 | 357 | `dd6616ca31ee` | `@filter.on_decorating_result(priority=99999)` |
| 2 | `astrbot_plugin_tool_xml_guard` | 100 | 79 | `665eabb4ccf3` | `@filter.on_decorating_result(priority=100)` |
| 3 | `astrbot_plugin_style_strip` | 90 | 84 | `bb2e99845f01` | `@filter.on_decorating_result(priority=90)` |
| 4 | `astrbot_plugin_face_map` | 80 | 63 | `15b733c9b9f3` | `@filter.on_decorating_result(priority=80)` |
| 5 | `astrbot_plugin_rule_guard` | 80 | 454 | `fe69f983026d` | `@filter.on_decorating_result(priority=80)` |
| 6 | `astrbot_plugin_recall_guard` | 70 | 97 | `3d2519ad4d8a` | `@filter.on_decorating_result(priority=70)` |
| 7 | `astrbot_plugin_quote_reply` | 60 | 29 | `979b4bfa9ee2` | `@filter.on_decorating_result(priority=60)` |
| 8 | `astrbot_plugin_chuanhuatong` | -10 | 390 | `7f6baa86449d` | `@filter.on_decorating_result(priority=-10)` |

astrbot_plugin_tool_xml_guard 的执行位次（降序 = 执行顺序）= [2]，共 8 个注册点
它是最后一个吗：否

AstrBot 排序实现： self._handlers.sort(key=lambda h: -h.extras_configs["priority"])
star_handler.py sha256： 0e84e9cf028632661cfd07cdcdcaba4fe4134e140320a23f2f617280e9ccf1df
astrbot 版本： 4.29.4

JSON 已写入 /tmp/hook-scan.json
