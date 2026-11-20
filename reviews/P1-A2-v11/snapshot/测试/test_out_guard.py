"""P1-A1 回归：统一输出清洗（tool_xml_guard.finalize_text）与多气泡直发通道。

在 astrbot 容器里跑（只读副本，不碰线上文件）：

    docker exec -w /AstrBot -e PYTHONPATH=/AstrBot -e RB_DIR=/tmp/rbtest_p1a \
        astrbot python -u /tmp/test_out_guard.py
"""
import asyncio
import importlib.util
import os
import re
import sys
import types
from pathlib import Path

DIR = Path(os.environ.get("RB_DIR", "/tmp/rbtest_p1a"))
PLUGINS = Path("/AstrBot/data/plugins")
FAILS = []


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS  " if cond else "FAIL  ") + name + (("   " + str(extra)) if extra else ""))


def load(key, path):
    spec = importlib.util.spec_from_file_location(key, str(path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


txg = load("txg_new", DIR / "tool_xml_guard.py")
mb = load("mb_new", DIR / "multi_bubble.py")
mb._finalize_text = txg.finalize_text

DSML = "<｜｜DSML｜｜"
LEAK = f"{DSML} calls>\n{DSML} invoke name=\"reveal_time\">\n{DSML} parameter name=\"x\">1</{DSML} parameter>\n</{DSML} invoke>\n{DSML} /calls>"

print("\n---- 一、残片矩阵 ----")
cases = [
    # 2026-11-20 修订：`<｜｜DSML｜｜ /calls>` 是第二种闭合形式 → 完整结构，整段删
    ("完整 DSML 结构（第二种闭合）", LEAK, ""),
    ("标准 invoke/parameter", '<invoke name="propose_change"><parameter name="scope">背景</parameter></invoke>正文', "正文"),
    ("未闭合 DSML", f"{DSML} calls>", ""),
    ("半角竖线", "<|DSML| calls>", ""),
    ("system_reminder", "<system_reminder>内部提示</system_reminder>正文", "正文"),
    # v7 R1-d：孤立闭合标签当普通文本保留
    ("孤立闭合标记（保留）", "</｜｜DSML｜｜ invoke>", "</｜｜DSML｜｜ invoke>"),
    # `</<` 叠加残片按闭合标签整体保留（`</` 后多一个 `<`）
    ("残缺闭合标记（`</<` 叠加 → 保留）", f"</{DSML} invoke>", f"</{DSML} invoke>"),
    ("夹在正文中间", f"你好\n{DSML} calls>\n今天周二", "你好\n今天周二"),
]
for name, src, want in cases:
    got = txg.finalize_text(src)
    ok(f"清洗：{name}", got == want, repr(got))

print("\n---- 二、不完整标记 ----")
for name, src, want in [
    ("只有开头", f"正文 {DSML} invoke name=\"x\">", "正文 "),
    ("只有标签名", "<invoke", ""),
    # v7 R3：标记后不是白名单标签，只删标记，`>` 原样保留
    ("竖线残留", f"{DSML}>正文", ">正文"),
]:
    out = txg.finalize_text(src)
    ok(f"不完整标记精确结果：{name}", out == want, repr(out))

print("\n---- 二之二、不误删（审查要求） ----")
for name, src, want in [
    ("普通竖线标记", "保留 A <|random_token|> 保留 B", "保留 A <|random_token|> 保留 B"),
    ("孤立斜杠", "价格 </ 3，其他", "价格 </ 3，其他"),
    # 标记后不是白名单标签 → 不算 R1 起始，按 R3 只删标记（空白原样）
    ("DSML 后跟说明文字（R3 → 只删标记）", f"{DSML} 普通说明文字不应该被删",
     " 普通说明文字不应该被删"),
]:
    got = txg.finalize_text(src)
    ok(f"不误删：{name}", got == want, repr(got))

print("\n---- 三、幂等 ----")
for name, src in [("完整结构", LEAK), ("夹在正文", f"你好\n{DSML} calls>\n今天周二")]:
    once = txg.finalize_text(src)
    twice = txg.finalize_text(once)
    ok(f"幂等：{name}", once == twice, repr(twice))

print("\n---- 四、普通文本 / 代码块保真 ----")
plain = "用 <div> 包起来，公式 a < b，中文标点“你好”，《标题》，≤ 3，emoji 😊，[微笑] 收尾。"
ok("普通文本逐字不变", txg.finalize_text(plain) == plain, repr(txg.finalize_text(plain)))

code = "说明\n```python\nif a < b:\n    print('<invoke>')\n```\n结束"
ok("代码块内容不动", "<invoke>" in txg.finalize_text(code) and txg.finalize_text(code).endswith("结束"))
ok("行内代码不动", txg.finalize_text("看 `x < y` 这个") == "看 `x < y` 这个")

print("\n---- 四之二、代码围栏 ----")
multi_blank = "说明\n```python\na = 1\n\n\nb = 2\n```\n结束"
out_blank = txg.finalize_text(multi_blank)
ok("代码块内多空行保真", "\n\n\nb = 2" in out_blank, repr(out_blank))

tilde = "说明\n~~~\nx < y\n~~~\n结束"
out_tilde = txg.finalize_text(tilde)
ok("~~~ 围栏保真", "~~~" in out_tilde and "x < y" in out_tilde)

quad = '说明\n````\n<invoke name="x">\n````\n结束'
ok("四反引号围栏保真", '<invoke name="x">' in txg.finalize_text(quad))

unclosed = "说明\n```python\nif a < b:\n  print(1)"
ok("未闭合围栏保真", "if a < b:" in txg.finalize_text(unclosed), repr(txg.finalize_text(unclosed)))

tail_ws = "说明\n```python\nprint(1)  \n  "
ok("未闭合围栏尾部空白逐字保真", txg.finalize_text(tail_ws).endswith("  "), repr(txg.finalize_text(tail_ws)))

print("\n---- 五、has_marker 不误判 ----")
ok("普通标签不算标记", txg.has_marker("<div>hi</div>") is False)
ok("a < b 不算标记", txg.has_marker("a < b") is False)
ok("DSML 算标记", txg.has_marker(f"{DSML} calls>") is True)
ok("invoke 算标记", txg.has_marker('<invoke name="x">') is True)

print("\n---- 五之二、大小写兼容 ----")
ok("大写 INVOKE 判为标记", txg.has_marker('<INVOKE name="x">') is True)
ok("小写 dsml 判为标记", txg.has_marker("<|dsml| calls>") is True)
up = '<INVOKE name="propose_change"><PARAMETER name="scope">背景</PARAMETER></INVOKE>正文'
ok("大写标签被清洗", txg.finalize_text(up) == "正文", repr(txg.finalize_text(up)))
ok("小写 dsml 被清洗", txg.finalize_text("<|dsml| calls>") == "", repr(txg.finalize_text("<|dsml| calls>")))

print("\n---- 五之三、围栏按行识别 ----")
indented_fence = "说明\n   ```python\n   x = 1\n   ```\n结束"
ok("缩进 3 格以内的围栏被识别", "   x = 1" in txg.finalize_text(indented_fence))

closed_mismatch = ("````\n```\n"
                   '<invoke name="propose_change"><parameter name="proposal">不该入箱</parameter></invoke>'
                   "\n```\n````\n结束")
ok("四反引号块内的三反引号不是结束标记",
   "不该入箱" in txg.finalize_text(closed_mismatch), repr(txg.finalize_text(closed_mismatch)[:40]))

print("\n---- 五之四、逐字保真（v4） ----")
for name, src in [
    ("前言缩进", "  前言\n正文"),
    ("连续空行", "a\n\n\n\nb"),
    ("闭合围栏尾部空行", "```\nx\n```\n\n"),
    ("未闭合围栏尾部空白", "```\nx  \n  "),
    ("行内反引号不是围栏", "前 ```x``` 后"),
]:
    ok(f"逐字保真：{name}", txg.finalize_text(src) == src, repr(txg.finalize_text(src)))


# ---------------------------------------------------------------- guard
class Result:
    def __init__(self, text):
        self.chain = [types.SimpleNamespace(text=text, type="plain")]


class GuardEv:
    def __init__(self, text):
        self._result = Result(text)
        self.stopped = False

    def get_result(self):
        return self._result

    def stop_event(self):
        self.stopped = True


# 让 isinstance(comp, Plain) 成立：用真实 Plain 类
from astrbot.api.message_components import Plain  # noqa: E402

txg.Plain = Plain


def guard_ev(text):
    ev = GuardEv(text)
    ev._result.chain = [Plain(text)]
    return ev


print("\n---- 五之五、部分清洗时其余内容逐字保留（R2） ----")
partial_cases = [
    ("清洗不影响前面行尾空格",
     "  前言  \n正文 <invoke name=\"x\">内部</invoke>\n",
     "  前言  \n正文 \n"),
    ("清洗不影响后续行尾空格",
     "正文 <invoke name=\"x\">内部</invoke>\n  后续内容  \n",
     "正文 \n  后续内容  \n"),
    ("清洗不影响原有连续空行",
     "前言\n\n\n正文 <invoke name=\"x\">内部</invoke>\n\n\n结尾",
     "前言\n\n\n正文 \n\n\n结尾"),
    ("同处行尾空格也不修剪",
     "  前言保留空格  \n正文 <invoke name=\"x\">内部</invoke>  \n",
     "  前言保留空格  \n正文   \n"),
]
for name, src, want in partial_cases:
    got = txg.finalize_text(src)
    ok(f"部分清洗保真：{name}", got == want, repr(got))

print("\n---- 五之六、围栏边界（R3） ----")
three_open_four_close = "```\n代码\n````\n之后 <invoke name=\"x\">内部</invoke>\n"
ok("3 开 4 关：关闭有效，之后内容被清洗", "<invoke" not in txg.finalize_text(three_open_four_close))

four_open_three_close = "````\n代码\n```\n<invoke name=\"propose_change\"><parameter name=\"proposal\">不该入箱</parameter></invoke>\n````\n"
ok("4 开 3 关：不算关闭，代码内容保留", "<invoke" in txg.finalize_text(four_open_three_close))

tilde_vs_backtick = "```\n代码\n~~~\n<invoke name=\"x\">内部</invoke>\n~~~\n"
ok("反引号围栏不能被波浪线关闭", "<invoke" in txg.finalize_text(tilde_vs_backtick))

backtick_vs_tilde = "~~~\n代码\n```\n<invoke name=\"x\">内部</invoke>\n```\n"
ok("波浪线围栏不能被反引号关闭", "<invoke" in txg.finalize_text(backtick_vs_tilde))

close_with_text = "```\n代码\n``` 还有字\n<invoke name=\"x\">内部</invoke>\n"
ok("关闭行带非空白 → 不算关闭", "<invoke" in txg.finalize_text(close_with_text))

print("\n---- 五之七、CRLF 围栏（R5） ----")
crlf_backtick = (
    "```xml\r\n"
    '<invoke name="x">代码示例</invoke>\r\n'
    "```\r\n"
    '正文 <invoke name="y">控制内容</invoke>\r\n'
)
out_crlf = txg.finalize_text(crlf_backtick)
ok("CRLF 反引号围栏：闭合后正文控制标记被清理",
   '<invoke name="y">' not in out_crlf and "代码示例" in out_crlf, repr(out_crlf))

crlf_tilde = (
    "~~~xml\r\n"
    '<invoke name="x">代码示例</invoke>\r\n'
    "~~~\r\n"
    '正文 <invoke name="y">控制内容</invoke>\r\n'
)
out_crlf2 = txg.finalize_text(crlf_tilde)
ok("CRLF 波浪线围栏：闭合后正文控制标记被清理",
   '<invoke name="y">' not in out_crlf2 and "代码示例" in out_crlf2, repr(out_crlf2))

code_crlf = "   ```python\r\n   x = 1  \r\n   ```   \r\n"
ok("CRLF 代码块逐字保留（缩进/尾随空格/换行）",
   txg.finalize_text(code_crlf) == code_crlf, repr(txg.finalize_text(code_crlf)))

close_space_crlf = "```\r\n代码\r\n```   \r\n正文 <invoke name=\"y\">控制</invoke>\r\n"
out_crlf3 = txg.finalize_text(close_space_crlf)
ok("CRLF 闭合行带空格也能识别", '<invoke name="y">' not in out_crlf3, repr(out_crlf3))

print("\n---- 六、装饰钩子：正常清洗 ----")
g = txg.ToolXmlGuard.__new__(txg.ToolXmlGuard)
g.cfg = {}
ev = guard_ev(f"你好\n{DSML} calls>\n今天周二")
asyncio.run(g.guard(ev))
ok("guard 清洗后保留正文", ev._result.chain and (ev._result.chain[0].text or "").strip() == "你好\n今天周二")
ok("guard 正常时不 stop", ev.stopped is False)

ev2 = guard_ev(f"{DSML} calls>")
asyncio.run(g.guard(ev2))
ok("清洗后为空 → stop_event", ev2.stopped is True)
ok("清洗后为空 → 链清空", len(ev2._result.chain) == 0)

print("\n---- 七、fail-closed ----")
saved_finalize = txg.finalize_text


def _boom(_t):
    raise RuntimeError("cleanup failed")


txg.finalize_text = _boom
ev3 = guard_ev(f"{DSML} calls> 正文")
asyncio.run(g.guard(ev3))
ok("清洗抛异常 → stop_event（不放行原文）", ev3.stopped is True)
ok("清洗抛异常 → 链清空", len(ev3._result.chain) == 0)
ok("清洗抛异常 → 原始标记没有留下", all("DSML" not in (c.text or "") for c in ev3._result.chain))
txg.finalize_text = saved_finalize

print("\n---- 八、钩子顺序 ----")
def priorities_of(path):
    """枚举一个文件里所有 on_decorating_result（含无 priority、跨行写法，默认 0）。"""
    src = Path(path).read_text(encoding="utf-8")
    return [int(m.group(1) or 0) for m in re.finditer(
        r"on_decorating_result\(\s*(?:priority\s*=\s*(-?\d+)\s*)?\)", src, re.S)]


order = {}
for p in PLUGINS.glob("astrbot_plugin_*/main.py"):
    prs = priorities_of(p)
    if prs:
        order[p.parent.name] = max(prs)
# 副本（待部署版本）的优先级：线上还没部署，所以单独读副本
order_new = dict(order)
order_new["astrbot_plugin_tool_xml_guard"] = max(priorities_of(DIR / "tool_xml_guard.py"))
ours = order_new.get("astrbot_plugin_tool_xml_guard")
meme = order.get("astrbot_plugin_meme_manager")
ok("tool_xml_guard 优先级 = -1000000", ours == -1000000, ours)
ok("priority 比 meme_manager 小", ours is not None and meme is not None and ours < meme, f"{ours} vs {meme}")
# AstrBot 的实际执行顺序是 priority 降序（append 时 sort(key=-priority)）
exec_order = sorted(order_new.items(), key=lambda kv: -kv[1])
ok("是最末一个执行（降序最后）", exec_order[-1][0] == "astrbot_plugin_tool_xml_guard", exec_order[-3:])
ok("枚举到全部装饰钩子注册点（≥8）", len(order) >= 8, len(order))
print("   全部装饰钩子（按实际执行顺序：priority 降序）：")
for _n, _p in exec_order:
    print(f"     {_p:>9}  {_n}")

# 运行时证据：AstrBot 自带的 registry 真的按 priority 降序返回
from astrbot.core.star.star_handler import star_handlers_registry, EventType  # noqa: E402


def _fake(pri, name):
    cfgs = {} if pri is None else {"priority": pri}   # None = 不写 priority，走默认 0
    return types.SimpleNamespace(
        extras_configs=cfgs,
        handler_full_name=name,
        event_type=EventType.OnDecoratingResultEvent,
        enabled=True,
        handler_module_path="probe",
        handler_name=name,
    )


star_handlers_registry.append(_fake(1, "probe_low"))
star_handlers_registry.append(_fake(1000000, "probe_high"))
star_handlers_registry.append(_fake(None, "probe_default"))
_rt = [h.handler_full_name for h in star_handlers_registry.get_handlers_by_event_type(
    EventType.OnDecoratingResultEvent, only_activated=False)]
ok("运行时：registry 按 priority 降序返回（大的先执行）",
   _rt.index("probe_high") < _rt.index("probe_low"), _rt[:5])
ok("运行时：默认优先级按 0 处理",
   any(h.handler_full_name == "probe_default" and h.extras_configs["priority"] == 0
       for h in star_handlers_registry.get_handlers_by_event_type(
           EventType.OnDecoratingResultEvent, only_activated=False)))

print("\n---- 九、多气泡：拆前清洗 ----")
class FakeAsync:
    @staticmethod
    async def sleep(_s):
        return None

    @staticmethod
    def create_task(coro):
        return None


mb.asyncio = FakeAsync


class MBCtx:
    def __init__(self):
        self.sent = []

    async def send_message(self, umo, chain):
        text = "".join(getattr(c, "text", "") or "" for c in chain.chain)
        self.sent.append(text)


class MBRun:
    def __init__(self, text):
        self.completion_text = text
        self.unified_msg_origin = "大肥鱼:FriendMessage:2654851421"
        self.message_str = "随便问句"


m = mb.MultiBubblePlugin.__new__(mb.MultiBubblePlugin)
m.cfg = {}
m._pending_parts = {}
m.context = MBCtx()

long_with_leak = (
    f"第一句话说完了。{DSML} calls>\n第二句话也在这里，而且足够长让它被拆开。"
    "第三句话继续补充细节，凑够拆分阈值。第四句话收尾。"
)
ev4 = MBRun(long_with_leak)
asyncio.run(m.on_llm_resp(ev4, ev4))
ok("拆前清洗：completion_text 不含 DSML", "DSML" not in ev4.completion_text, repr(ev4.completion_text[:40]))
queued = list(m._pending_parts.values())
flat = [x for q in queued for x in q]
ok("拆前清洗：待补发气泡不含 DSML", all("DSML" not in x for x in flat), flat[:1])

print("\n---- 十、多气泡：补发前清洗 / 空跳过 / 异常中止 ----")
m.context = MBCtx()
asyncio.run(m._send_rest(ev4.unified_msg_origin, [f"干净一句。{DSML} calls>", "   ", "第二句正常"]))
ok("补发内容不含 DSML", all("DSML" not in x for x in m.context.sent), m.context.sent)
ok("清洗后为空的跳过不发", len(m.context.sent) == 2, m.context.sent)

m2 = mb.MultiBubblePlugin.__new__(mb.MultiBubblePlugin)
m2.cfg = {}
m2.context = MBCtx()
mb._finalize_text = _boom
asyncio.run(m2._send_rest("大肥鱼:FriendMessage:2654851421", ["一", "二", "三"]))
ok("补发清洗异常 → 中止剩余（一条都不发）", m2.context.sent == [], m2.context.sent)
mb._finalize_text = txg.finalize_text

# 发送失败时的日志：只留类型 + req，不能带异常消息
logs = []
_orig_warning = mb.logger.warning
mb.logger.warning = lambda msg, *a, **k: logs.append(str(msg))


class BoomCtx:
    def __init__(self):
        self.sent = []

    async def send_message(self, umo, chain):
        self.sent.append("attempt")
        raise RuntimeError("secret-body-should-not-appear")


m4 = mb.MultiBubblePlugin.__new__(mb.MultiBubblePlugin)
m4.cfg = {}
m4.context = BoomCtx()
asyncio.run(m4._send_rest("大肥鱼:FriendMessage:2654851421", ["第一句正常"], "req123"))
mb.logger.warning = _orig_warning
joined = " | ".join(logs)
ok("发送失败日志含类型和 req", "RuntimeError" in joined and "req123" in joined, joined[:80])
ok("发送失败日志不含异常消息", "secret-body" not in joined, joined[:80])

# 发送失败要中止剩余补发（不能越过失败的那一条继续发）
logs2 = []
mb.logger.warning = lambda msg, *a, **k: logs2.append(str(msg))
m5 = mb.MultiBubblePlugin.__new__(mb.MultiBubblePlugin)
m5.cfg = {}
m5.context = BoomCtx()
asyncio.run(m5._send_rest("大肥鱼:FriendMessage:2654851421", ["一", "二", "三"], "req456"))
mb.logger.warning = _orig_warning
ok("发送失败 → 中止剩余（只尝试 1 条）", len(m5.context.sent) == 1, m5.context.sent)
ok("中止日志含类型和 req", "RuntimeError" in " ".join(logs2) and "req456" in " ".join(logs2), logs2[:1])

# after_sent 的异常日志也不许带异常正文
logs3 = []
mb.logger.warning = lambda msg, *a, **k: logs3.append(str(msg))
gm = mb.MultiBubblePlugin.__new__(mb.MultiBubblePlugin)
gm.cfg = {}
gm._pending_parts = {}
asyncio.run(gm.after_sent(object()))   # 没有 unified_msg_origin → AttributeError
mb.logger.warning = _orig_warning
joined3 = " ".join(logs3)
ok("after_sent 异常日志含类型", "AttributeError" in joined3, joined3[:60])
ok("after_sent 异常日志不含异常正文", "object" not in joined3.replace("type(e)", ""), joined3[:60])

print("\n---- 十一、多气泡：预处理失败取消拆分 ----")
m3 = mb.MultiBubblePlugin.__new__(mb.MultiBubblePlugin)
m3.cfg = {}
m3._pending_parts = {}
m3.context = MBCtx()
mb._finalize_text = _boom
ev5 = MBRun(long_with_leak)
asyncio.run(m3.on_llm_resp(ev5, ev5))
ok("预处理异常 → 不排队补发", not m3._pending_parts)
ok("预处理异常 → 原文保持不动（交给管道清洗）", ev5.completion_text == long_with_leak)
mb._finalize_text = txg.finalize_text

print("\n---- 十二、propose_change 两种格式入箱 ----")
import tempfile as _tf
tmp_plan = Path(_tf.mkdtemp()) / "提案.md"
txg.PLAN = tmp_plan

plain_xml = ('<invoke name="propose_change"><parameter name="scope">背景</parameter>'
             '<parameter name="proposal">加个天气提醒</parameter></invoke>说明')
ev_p = guard_ev(plain_xml)
asyncio.run(g.guard(ev_p))
txt = tmp_plan.read_text(encoding="utf-8") if tmp_plan.exists() else ""
ok("普通 XML 提案入箱", "加个天气提醒" in txt, txt[:30])

dsml_xml = (f'{DSML} invoke name="propose_change">\n'
            f'{DSML} parameter name="scope">背景{DSML} /parameter>\n'
            f'{DSML} parameter name="proposal">加个喝水提醒{DSML} /parameter>\n'
            f'{DSML} /invoke>')
ev_q = guard_ev(dsml_xml)
asyncio.run(g.guard(ev_q))
txt2 = tmp_plan.read_text(encoding="utf-8") if tmp_plan.exists() else ""
ok("DSML 包裹提案入箱", "加个喝水提醒" in txt2, txt2[-40:])
# 2026-11-20 修订：`<｜｜DSML｜｜ /parameter>` / `/invoke>` 是第二种闭合形式 → 完整清理
ok("DSML 提案（第二种闭合）→ 清洗后为空 → 不发送",
   ev_q.stopped is True and len(ev_q._result.chain) == 0,
   repr(ev_q._result.chain[0].text[:40]) if ev_q._result.chain else "")

# 代码块里的提案示例：是文档，不是真调用，不能入箱
before = tmp_plan.read_text(encoding="utf-8") if tmp_plan.exists() else ""
samples = [
    ("```", f"看这个例子：\n\n```xml\n{plain_xml}\n```\n结束"),
    ("~~~", f"看这个例子：\n\n~~~xml\n{dsml_xml}\n~~~\n结束"),
    ("four", f"看这个例子：\n\n````xml\n{plain_xml}\n````\n结束"),
    ("inline", f"就像 `{plain_xml}` 这种写法"),
]
for kind, body in samples:
    ev_s = guard_ev(body)
    asyncio.run(g.guard(ev_s))
    after = tmp_plan.read_text(encoding="utf-8") if tmp_plan.exists() else ""
    ok(f"代码块内提案示例不入箱：{kind}", after == before)

# 四反引号块里出现字面量三反引号：后面的示例仍然不能解析
before_lit = tmp_plan.read_text(encoding="utf-8") if tmp_plan.exists() else ""
literal_body = "看这个写法：\n````\n```\n" + '<invoke name="propose_change"><parameter name="proposal">字面量示例</parameter></invoke>' + "\n```\n````\n结束"
ev_lit = guard_ev(literal_body)
asyncio.run(g.guard(ev_lit))
after_lit = tmp_plan.read_text(encoding="utf-8") if tmp_plan.exists() else ""
ok("四反引号块内字面量三反引号之后的提案不入箱", after_lit == before_lit, after_lit[-30:])

before_unc = tmp_plan.read_text(encoding="utf-8") if tmp_plan.exists() else ""
unclosed_proposal = ("示例：\n```xml\n"
                     '<invoke name="propose_change"><parameter name="proposal">未闭合也入不了箱</parameter></invoke>')
ev_unc = guard_ev(unclosed_proposal)
asyncio.run(g.guard(ev_unc))
after_unc = tmp_plan.read_text(encoding="utf-8") if tmp_plan.exists() else ""
ok("未闭合围栏后的假提案不入箱", after_unc == before_unc, after_unc[-30:])

print("\n---- 十三、读取结果失败 fail-closed ----")
class BrokenEv:
    def __init__(self):
        self.stopped = False

    def get_result(self):
        raise RuntimeError("boom")

    def stop_event(self):
        self.stopped = True

ev_b = BrokenEv()
asyncio.run(g.guard(ev_b))
ok("读取结果失败 → stop_event", ev_b.stopped is True)

print("\n---- 十四、P1-A2 v7 规范案例 1–31 ----")
V7_CASES = [
    (1, "前缀A <｜｜DSML｜｜ calls>正文</｜｜DSML｜｜ calls> 后缀B", "前缀A  后缀B"),
    (2, "前缀A ｜｜DSML｜｜ calls> 后缀文字", "前缀A  后缀文字"),
    (3, '前缀A ｜｜DSML｜｜ invoke name="x"> 后缀文字', "前缀A  后缀文字"),
    (4, "前缀A ｜｜DSML｜｜ calls 后缀文字", "前缀A   后缀文字"),
    (5, "前缀A ｜｜DSML｜｜ 后缀B", "前缀A  后缀B"),
    (6, "这个标记写作 ｜｜DSML｜｜", "这个标记写作 "),
    (7, "他问「｜｜DSML｜｜是什么意思」", "他问「｜｜DSML｜｜是什么意思」"),
    (8, "看 `｜｜DSML｜｜ calls` 这个", "看 `｜｜DSML｜｜ calls` 这个"),
    (9, "说明\n```\n<｜｜DSML｜｜ calls>示例</｜｜DSML｜｜ calls>\n```\n结束",
        "说明\n```\n<｜｜DSML｜｜ calls>示例</｜｜DSML｜｜ calls>\n```\n结束"),
    (10, "他问「｜｜DSML｜｜ calls> 后缀", "他问「 后缀"),
    (11, "前缀A ｜｜DSML｜｜ 未知标签> 后缀B", "前缀A  未知标签> 后缀B"),
    (12, '前缀A ｜｜DSML｜｜ invoke name="a>b"> 后缀文字', "前缀A  后缀文字"),
    (13, '前缀A ｜｜DSML｜｜ invoke name="a>b 后缀文字',
         '前缀A   name="a>b 后缀文字'),
    (14, "前缀A ｜｜DSML｜｜ invoke name='a>b'> 后缀文字", "前缀A  后缀文字"),
    (15, "他说的 don't 和 owners' 都在正文里", "他说的 don't 和 owners' 都在正文里"),
    (16, "她说「it's fine」然后走了", "她说「it's fine」然后走了"),
    (17, "第一段「引号开头\n\n第二段结尾」", "第一段「引号开头\n\n第二段结尾」"),
    (18, "第一段「引号开头\n第二段结尾」", "第一段「引号开头\n第二段结尾」"),
    (19, "前缀A ｜｜DSML｜｜ callsxyz> 后缀B", "前缀A  callsxyz> 后缀B"),
    (20, "前缀A ｜｜DSML｜｜ tool_calls> 后缀B", "前缀A  tool_calls> 后缀B"),
    (21, "<｜｜DSML｜｜ calls>看 `code` 示例</｜｜DSML｜｜ calls>",
         "<｜｜DSML｜｜ calls>看 `code` 示例</｜｜DSML｜｜ calls>"),
    (22, "第一段「\r\n｜｜DSML｜｜ calls>正文\r\n\r\n第二段结尾」",
         "第一段「\r\n正文\r\n\r\n第二段结尾」"),
    (23, "看 `a\\`b` 这个", "看 `a\\`b` 这个"),
    (24, '<｜｜DSML｜｜ calls name="a>b">正文</｜｜DSML｜｜ calls>', ""),
    (25, '<｜｜DSML｜｜ calls name="a>b', '<｜｜DSML｜｜ calls name="a>b'),
    (26, "<｜｜DSML｜｜ calls>正文", "正文"),
    (27, "<｜｜DSML｜｜ calls>正文</｜｜DSML｜｜ invoke>",
         "<｜｜DSML｜｜ calls>正文</｜｜DSML｜｜ invoke>"),
    (28, "</｜｜DSML｜｜ invoke> 前缀", "</｜｜DSML｜｜ invoke> 前缀"),
    (29, "｜DSML｜ calls> 后缀", " 后缀"),
    (30, "前缀A ｜｜DSML｜｜ 后缀B", "前缀A  后缀B"),
    (31, "<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke>x</｜｜DSML｜｜ invoke></｜｜DSML｜｜ calls>", ""),
]
for _n, _src, _want in V7_CASES:
    _got = txg.finalize_text(_src)
    ok(f"v7 规范 #{_n}", _got == _want, repr(_got))

print("\n---- 十五、P1-A2 v4 关键案例 1–14 ----")
V4_CASES = [
    (1, "</｜｜DSML｜｜ invoke> 前缀", "</｜｜DSML｜｜ invoke> 前缀"),
    (2, "</｜DSML｜ invoke> 前缀", "</｜DSML｜ invoke> 前缀"),
    (3, "<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke>x</｜｜DSML｜｜ calls>",
        "<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke>x</｜｜DSML｜｜ calls>"),
    (4, "<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke>x</｜｜DSML｜｜ invoke>",
        "<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke>x</｜｜DSML｜｜ invoke>"),
    (5, "外层<｜｜DSML｜｜ calls>完整内层<｜｜DSML｜｜ invoke>x</｜｜DSML｜｜ invoke>",
        "外层<｜｜DSML｜｜ calls>完整内层<｜｜DSML｜｜ invoke>x</｜｜DSML｜｜ invoke>"),
    (6, '<｜｜DSML｜｜ calls name="a>b">正文</｜｜DSML｜｜ calls>', ""),
    (7, "「<｜｜DSML｜｜ calls>示例</｜｜DSML｜｜ calls>」",
        "「<｜｜DSML｜｜ calls>示例</｜｜DSML｜｜ calls>」"),
    (8, "<｜DSML｜ calls>", ""),
    (9, '{"a": "b\\"c"}', '{"a": "b\\"c"}'),
    (13, "<｜｜DSML｜｜ calls 后缀", "<｜｜DSML｜｜ calls 后缀"),
    (14, "</｜｜DSML｜｜ invoke> <｜｜DSML｜｜ calls>正文",
         "</｜｜DSML｜｜ invoke> 正文"),
]
for _n, _src, _want in V4_CASES:
    _got = txg.finalize_text(_src)
    ok(f"v4 案例 #{_n}", _got == _want, repr(_got))

print("\n---- 十六、attrs 三状态 ----")
for _label, _text, _want in [
    ("FOUND_END", '<｜｜DSML｜｜ calls name="x">', "FOUND_END"),
    ("UNTERMINATED_ATTRIBUTE", '<｜｜DSML｜｜ calls name="x', "UNTERMINATED_ATTRIBUTE"),
    ("MISSING_END", '<｜｜DSML｜｜ calls', "MISSING_END"),
]:
    _m = txg._marker_at(_text, 0)
    _st, _idx = txg._scan_attrs(_text, _m["end"])
    ok(f"_scan_attrs {_label}", _st == _want, _st)

print("\n---- 十七、P1-A2 fail-closed 注入（三条链路） ----")
for _fn in ("_code_regions", "_scan_attrs", "_match_r1"):
    _orig = getattr(txg, _fn)

    def _inject(*_a, **_k):
        raise RuntimeError("injected")

    setattr(txg, _fn, _inject)
    _ev = guard_ev(f"{DSML} calls>正文")
    asyncio.run(g.guard(_ev))
    ok(f"注入 {_fn} → 不发送（发送次数 0）",
       _ev.stopped is True and len(_ev._result.chain) == 0)
    setattr(txg, _fn, _orig)

print("\n---- 十八、P1-A2 幂等 + 性能 ----")
for _name, _src in [
    ("完整结构", "<｜｜DSML｜｜ calls>x</｜｜DSML｜｜ calls>"),
    ("R2-A", "前缀A ｜｜DSML｜｜ calls> 后缀"),
    ("R3", "前缀A ｜｜DSML｜｜ 后缀B"),
    ("引号保护", "「<｜｜DSML｜｜ calls>示例</｜｜DSML｜｜ calls>」"),
    ("CRLF 跨段", "第一段「\r\n｜｜DSML｜｜ calls>正文\r\n\r\n第二段结尾」"),
]:
    _once = txg.finalize_text(_src)
    _twice = txg.finalize_text(_once)
    ok(f"P1-A2 幂等：{_name}", _once == _twice, repr(_twice))

import time as _time  # noqa: E402

_unit = ("正常正文，包含一些说明文字和标点。" * 8
         + "<｜｜DSML｜｜ calls>示例</｜｜DSML｜｜ calls>\n")
_big = (_unit * 40)[:5000]
_t0 = _time.perf_counter()
for _ in range(10):
    txg.finalize_text(_big)
_dt = (_time.perf_counter() - _t0) / 10 * 1000
ok("5KB 文本 < 10ms", _dt < 10, f"{_dt:.2f}ms")

print("\n---- 十九、2026-11-20 修订：第二种闭合形式 `<｜｜DSML｜｜ /name>` ----")
NEW_CLOSE_CASES = [
    ("完整新闭合", "<｜｜DSML｜｜ calls>正文<｜｜DSML｜｜ /calls>", ""),
    ("嵌套新闭合",
     "<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke>x<｜｜DSML｜｜ /invoke><｜｜DSML｜｜ /calls>", ""),
    ("大小写", "<｜｜DSML｜｜ CALLS>正文<｜｜DSML｜｜ /Calls>", ""),
    ("半角竖线新闭合", "<||DSML|| calls>正文<||DSML|| /calls>", ""),
    ("闭合尾部空格", "<｜｜DSML｜｜ calls>正文<｜｜DSML｜｜ /calls  >", ""),
    ("属性引号不影响新闭合",
     '<｜｜DSML｜｜ calls name="a>b">正文<｜｜DSML｜｜ /calls>', ""),
    ("孤立新闭合", "<｜｜DSML｜｜ /calls>", "<｜｜DSML｜｜ /calls>"),
    ("孤立新闭合前缀", "</x><｜｜DSML｜｜ /calls> 后缀", "</x><｜｜DSML｜｜ /calls> 后缀"),
    ("错名新闭合", "<｜｜DSML｜｜ calls>正文<｜｜DSML｜｜ /invoke>",
     "<｜｜DSML｜｜ calls>正文<｜｜DSML｜｜ /invoke>"),
    ("未知标签新闭合", "<｜｜DSML｜｜ calls>正文<｜｜DSML｜｜ /unknown>",
     "正文<｜｜DSML｜｜ /unknown>"),
    ("带属性新闭合", '<｜｜DSML｜｜ calls>正文<｜｜DSML｜｜ /calls name="x">',
     '正文<｜｜DSML｜｜ /calls name="x">'),
    ("带属性标准闭合", '<｜｜DSML｜｜ calls>正文</｜｜DSML｜｜ calls name="x">',
     '<｜｜DSML｜｜ calls>正文</｜｜DSML｜｜ calls name="x">'),
    ("行内代码内新闭合", "看 `<｜｜DSML｜｜ calls>示例<｜｜DSML｜｜ /calls>` 这个",
     "看 `<｜｜DSML｜｜ calls>示例<｜｜DSML｜｜ /calls>` 这个"),
    ("引号内新闭合", "「<｜｜DSML｜｜ calls>示例<｜｜DSML｜｜ /calls>」",
     "「<｜｜DSML｜｜ calls>示例<｜｜DSML｜｜ /calls>」"),
    ("R1-f 代码相交", "<｜｜DSML｜｜ calls>看 `code` 示例<｜｜DSML｜｜ /calls>",
     "<｜｜DSML｜｜ calls>看 `code` 示例<｜｜DSML｜｜ /calls>"),
    ("跨段新闭合", "<｜｜DSML｜｜ calls>\n\n正文<｜｜DSML｜｜ /calls>",
     "\n正文<｜｜DSML｜｜ /calls>"),
    ("缺少空格", "<｜｜DSML｜｜calls>正文<｜｜DSML｜｜/calls>", "正文<｜｜DSML｜｜/calls>"),
    ("</< 兼容", "</<｜｜DSML｜｜ invoke>", "</<｜｜DSML｜｜ invoke>"),
]
for _name, _src, _want in NEW_CLOSE_CASES:
    _got = txg.finalize_text(_src)
    ok(f"新闭合：{_name}", _got == _want, repr(_got))

# 带属性/未知标签的负例：不能误判 COMPLETE、不能删正文
for _name, _src in [
    ("带属性新闭合", '<｜｜DSML｜｜ calls>正文<｜｜DSML｜｜ /calls name="x">'),
    ("带属性标准闭合", '<｜｜DSML｜｜ calls>正文</｜｜DSML｜｜ calls name="x">'),
    ("未知标签新闭合", "<｜｜DSML｜｜ calls>正文<｜｜DSML｜｜ /unknown>"),
]:
    _out = txg.finalize_text(_src)
    ok(f"新闭合负例不删正文：{_name}", "正文" in _out, repr(_out))
    ok(f"新闭合负例不进 COMPLETE：{_name}", _out != "", repr(_out))

# 完整 LEAK 不再整段保留，且不残留任何 DSML 标记
_leak_out = txg.finalize_text(LEAK)
ok("完整 LEAK 清理为空", _leak_out == "", repr(_leak_out))
ok("完整 LEAK 不残留 DSML", "DSML" not in _leak_out, repr(_leak_out))

# 新闭合幂等
for _name, _src in [
    ("完整新闭合", "<｜｜DSML｜｜ calls>x<｜｜DSML｜｜ /calls>"),
    ("孤立新闭合", "<｜｜DSML｜｜ /calls>"),
    ("带属性新闭合", '<｜｜DSML｜｜ calls>正文<｜｜DSML｜｜ /calls name="x">'),
]:
    _once = txg.finalize_text(_src)
    _twice = txg.finalize_text(_once)
    ok(f"新闭合幂等：{_name}", _once == _twice, repr(_twice))

print("\n---- 二十、2026-11-20 v9 复审修订（引号感知终点 / 非法候选跳过） ----")
V10_CASES = [
    # 标准闭合属性值含 `>` 且属性未闭合：不因 find(">") 截断而误删后面内容
    ("标准闭合属性值含 > 且未闭合",
     '<｜｜DSML｜｜ calls>正文</｜｜DSML｜｜ calls name="a>｜｜DSML｜｜ calls>',
     '<｜｜DSML｜｜ calls>正文</｜｜DSML｜｜ calls name="a>｜｜DSML｜｜ calls>'),
    # 标准闭合属性值含 `>` 且闭合：整段按异常处理，不判 COMPLETE、不删正文
    ("标准闭合属性值含 >",
     '<｜｜DSML｜｜ calls>正文</｜｜DSML｜｜ calls name="a>b">',
     '<｜｜DSML｜｜ calls>正文</｜｜DSML｜｜ calls name="a>b">'),
]
for _name, _src, _want in V10_CASES:
    _got = txg.finalize_text(_src)
    ok(f"v10：{_name}", _got == _want, repr(_got))

# 新闭合候选带属性值含 `>`：不能误判 COMPLETE，正文保留
_v10a = txg.finalize_text('<｜｜DSML｜｜ calls>正文<｜｜DSML｜｜ /calls name="a>b">')
ok("v10：新闭合候选属性值含 > 不删正文", "正文" in _v10a, repr(_v10a))
ok("v10：新闭合候选属性值含 > 不进 COMPLETE", _v10a != "", repr(_v10a))

# 非法新闭合候选内部还有标记：整体跳过，不把内部标记当结构、不吞正文
_v10b = txg.finalize_text("<｜｜DSML｜｜ calls>正文<｜｜DSML｜｜ /bad <｜｜DSML｜｜ invoke>x")
ok("v10：非法候选内部标记不吞正文", "正文" in _v10b and "x" in _v10b, repr(_v10b))
ok("v10：非法候选整体隔离、内部标记保真",
   "｜｜DSML｜｜ invoke" in _v10b, repr(_v10b))

_v10c = txg.finalize_text("<｜｜DSML｜｜ calls>正文<｜｜DSML｜｜ /bad <｜｜DSML｜｜ invoke>>尾巴")
ok("v10：非法候选 + 内部 > 不误删正文", "正文" in _v10c and "尾巴" in _v10c, repr(_v10c))
ok("v10：非法候选 + 内部 > 隔离保真",
   "｜｜DSML｜｜ invoke" in _v10c, repr(_v10c))

print("\n---- 二十一、2026-11-20 v11 修订：非法候选隔离贯穿扫描（KEEP_ME） ----")
KEEP_CASES = [
    ("栈内候选 + UNCLOSED_SINGLE",
     f"{DSML} calls>KEEP_ME{DSML} /bad>TAIL", ("KEEP_ME", "TAIL")),
    ("顶层孤立候选",
     f"前缀{DSML} /bad>KEEP_ME 后缀", ("前缀", "KEEP_ME", "后缀")),
    ("顶层孤立候选 + 内部完整 invoke",
     f"前缀{DSML} /bad {DSML} invoke>INNER{DSML} /invoke>>TAIL 后缀",
     ("INNER", "TAIL", "后缀")),
    ("候选内完整 invoke（栈内）",
     f"{DSML} calls>KEEP_ME{DSML} /bad {DSML} invoke>INNER{DSML} /invoke>>TAIL",
     ("KEEP_ME", "INNER", "TAIL")),
    ("候选之后尾部裸标记",
     f"{DSML} calls>KEEP_ME{DSML} /bad>TAIL {DSML} 后缀",
     ("KEEP_ME", "TAIL", "后缀")),
    ("候选之后尾部完整结构",
     f"{DSML} calls>KEEP_ME{DSML} /bad>TAIL {DSML} invoke>X{DSML} /invoke>尾部",
     ("KEEP_ME", "TAIL", "X", "尾部")),
    ("候选属性含 >",
     f'{DSML} calls>KEEP_ME{DSML} /bad name="a>b">TAIL',
     ("KEEP_ME", "TAIL")),
]
for _name, _src, _must in KEEP_CASES:
    _out = txg.finalize_text(_src)
    ok(f"v11 隔离：{_name} 正文保留", all(x in _out for x in _must), repr(_out))

# 候选之后仍按规范处理：外层完整但含候选 → R1-f 跳过外层；候选之后的合法结构照常清理
_r1f = txg.finalize_text(
    f"{DSML} calls>KEEP_ME{DSML} /bad></{DSML} calls>TAIL {DSML} invoke>X{DSML} /invoke>")
ok("v11 隔离后：候选之后的完整结构仍按规范清理", "X" not in _r1f, repr(_r1f))
ok("v11 隔离后：R1-f 不删候选内部正文", "KEEP_ME" in _r1f and "TAIL" in _r1f, repr(_r1f))

# R1-c / MISMATCH / skip_to：只删该删的，不扩大正文删除
_r1c = txg.finalize_text(f"{DSML} calls>KEEP_ME{DSML} /bad>TAIL")
ok("v11 R1-c 只删外层起始标签", _r1c.startswith("KEEP_ME"), repr(_r1c))
_mm = txg.finalize_text(f"{DSML} calls>KEEP_ME{DSML} /invoke>TAIL")
ok("v11 MISMATCH 不删正文", "KEEP_ME" in _mm and "TAIL" in _mm, repr(_mm))

print("\n==== 汇总 ====")
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL PASS")
