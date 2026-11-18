# 钩子顺序证据：`tool_xml_guard` 是否最后执行

> 结论：**是**。AstrBot 的 handler 按 `-priority` 排序（priority 大的先执行），
> `tool_xml_guard` 的 priority 是 **-1000000**，在全部 `on_decorating_result` 注册点里最小，
> 因此降序执行时排最后。下面三层证据。

## 一、静态全量枚举（所有 `on_decorating_result(...)` 写法，含无 priority / 跨行，默认 0）

| 插件 | priority | 来源 | 源码行号 | 匹配到的原文 |
|---|---|---|---|---|
| `astrbot_plugin_meme_manager` | 99999 | 线上(部署前) | `main.py:357` | `on_decorating_result(priority=99999)` |
| `astrbot_plugin_style_strip` | 90 | 线上(部署前) | `main.py:84` | `on_decorating_result(priority=90)` |
| `astrbot_plugin_face_map` | 80 | 线上(部署前) | `main.py:63` | `on_decorating_result(priority=80)` |
| `astrbot_plugin_rule_guard` | 80 | 线上(部署前) | `main.py:454` | `on_decorating_result(priority=80)` |
| `astrbot_plugin_recall_guard` | 70 | 线上(部署前) | `main.py:97` | `on_decorating_result(priority=70)` |
| `astrbot_plugin_quote_reply` | 60 | 线上(部署前) | `main.py:29` | `on_decorating_result(priority=60)` |
| `astrbot_plugin_chuanhuatong` | -10 | 线上(部署前) | `main.py:390` | `on_decorating_result(priority=-10)` |
| `astrbot_plugin_tool_xml_guard` | -1000000 | snapshot(v4) | `main.py:280` | `on_decorating_result(priority=-1000000)` |

共 8 个注册点。**以 v4 snapshot 为准**（`tool_xml_guard` 改成了 -1000000），部署后按 priority 降序执行时最后一个 = `astrbot_plugin_tool_xml_guard`；线上未部署前它仍是 100。

## 二、AstrBot 源码的排序规则（`core/star/star_handler.py`）

```python
        self.star_handlers_map: dict[str, StarHandlerMetadata] = {}
        self._handlers: list[StarHandlerMetadata] = []

    def append(self, handler: StarHandlerMetadata) -> None:
        """添加一个 Handler，并保持按优先级有序"""
        if "priority" not in handler.extras_configs:
            handler.extras_configs["priority"] = 0

        self.star_handlers_map[handler.handler_full_name] = handler
        self._handlers.append(handler)
        self._handlers.sort(key=lambda h: -h.extras_configs["priority"])

    def _print_handlers(self) -> None:
        for handler in self._handlers:
            print(handler.handler_full_name)

    @overload
```

`append()` 每次都 `sort(key=-priority)`；`get_handlers_by_event_type()` 直接按 `_handlers` 顺序返回、
不做二次排序；`ResultDecorateStage.process` 按返回顺序依次 `await handler.handler(event)`。
⇒ 执行顺序 = priority **降序**，priority 最小的最后执行。

## 三、运行时实验（真实 `star_handlers_registry`）

测试里向 registry 追加两个假 handler（priority 1 和 1000000）与一个不写 priority 的，
再调 `get_handlers_by_event_type(OnDecoratingResultEvent, only_activated=False)`：

```text
PASS  运行时：registry 按 priority 降序返回（大的先执行）   ['probe_high', 'data.plugins.astrbot_plugin_tool_xml_guard.main_guard', 'data.plugins.astrbot_plugin_face_map.main_on_decorating', 'probe_low', 'probe_default']
PASS  运行时：默认优先级按 0 处理
```

实际返回顺序里 `probe_high` 在 `probe_low` 之前，证明「大 priority 先返回、先执行」；
不写 priority 的那个被 `append()` 补成 0。

## 四、局限（如实说明）

线上进程内的 registry 没有对外读取接口，无法直接 dump；但它是 star_manager 逐个 `append()` 的结果，
priority 写在源码装饰器里、加载过程不改写，所以静态枚举（8 个）与运行时注册集合一致。
若审查方要求「线上进程内 dump」，需要额外加一个只读诊断口，当前未做。
