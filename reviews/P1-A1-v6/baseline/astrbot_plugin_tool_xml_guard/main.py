"""她要是把工具调用写成了 XML 文本，就替她执行 + 把 XML 从消息里抹掉。

为什么需要
----------
deepseek-v4-pro 有时不走 function calling，而是在回复正文里输出
`<invoke name="propose_change"><parameter name="scope">…` 这种 XML
（2026-11-02 15:46 实测：用户屏幕上直接看到一堆标签，提案一条没落库）。

这个插件做两件事：
1. 认出这种 XML，按她的意图真正执行（目前支持 propose_change）
2. 把 XML 从发出去的文本里删掉，只留她本来那句人话
   —— 删完如果空了，补一句自然的短话，绝不把标签发出去
"""

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star, register

PLAN = Path(r"/AstrBot/shared/她的提案.md")
REVIEW = Path(r"C:\Users\Lenovo\Documents\deepseek-harness\default-workspace\批阅.py")

INVOKE_RE = re.compile(r"<invoke\s+name=\"([^\"]+)\">(.*?)</invoke>", re.S)
PARAM_RE = re.compile(r"<parameter\s+name=\"([^\"]+)\">(.*?)</parameter>", re.S)

FALLBACK = "行，我写好了，放你那儿等点头。"

# 会被模型当正文吐出来的内部标签（2026-11-02 按大肥鱼配置包的 dafeiyu_clean 扩充）
LEAK_TAGS = ["system_reminder", "image_caption", "thinking", "tool_call",
             "tool_response", "function_call", "antml:invoke", "DSML"]



def parse_invokes(text: str) -> list[dict]:
    out = []
    for m in INVOKE_RE.finditer(text):
        name = m.group(1).strip()
        params = {p.group(1).strip(): p.group(2).strip() for p in PARAM_RE.finditer(m.group(2))}
        out.append({"name": name, "params": params})
    return out


def strip_xml(text: str) -> str:
    t = INVOKE_RE.sub("", text)
    # 成对的内部标签整段删掉
    for tag in LEAK_TAGS:
        t = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", t, flags=re.S)
    # 残留的开始/结束标签
    names = "|".join(["invoke", "parameter"] + LEAK_TAGS)
    t = re.sub(rf"</?(?:{names})[^>]*>", "", t)
    # DSML 这类竖线标记
    t = t.replace("｜DSML｜", "").replace("<DSML>", "").replace("</DSML>", "")
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def save_proposal(scope: str, prop: str, reason: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    scope = "本体" if "本体" in scope else "背景"
    entry = (f"\n## {stamp} · 她随时提（工具XML补录）· 待批\n"
             f"范围：{scope}\n提案：{prop.strip()}\n理由：{reason.strip()}\n")
    with PLAN.open("a", encoding="utf-8") as f:
        f.write(entry)


@register("astrbot_plugin_tool_xml_guard", "dsh", "把写错的工具XML执行掉并从消息里删掉", "1.0.0")
class ToolXmlGuard(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.cfg = config or {}

    @filter.on_decorating_result(priority=100)
    async def guard(self, event: AstrMessageEvent) -> None:
        try:
            result = event.get_result()
            if result is None or not result.chain:
                return
            changed = False
            saved = 0
            for comp in result.chain:
                if not isinstance(comp, Plain):
                    continue
                text = comp.text or ""
                if not any(m in text for m in ("<invoke", "<parameter", "<system_reminder", "DSML", "<thinking")):
                    continue
                for call in parse_invokes(text):
                    if call["name"] == "propose_change":
                        p = call["params"]
                        prop = p.get("proposal", "").strip()
                        if not prop:
                            continue
                        try:
                            save_proposal(p.get("scope", "背景"), prop, p.get("reason", ""))
                            saved += 1
                        except Exception as e:
                            logger.warning(f"[tool_xml_guard] 补录失败：{e}")
                cleaned = strip_xml(text)
                if not cleaned:
                    cleaned = FALLBACK
                comp.text = cleaned
                changed = True
            if saved:
                try:
                    subprocess.run([sys.executable, str(REVIEW), "刷新"],
                                   capture_output=True, timeout=30)
                except Exception:
                    pass
                logger.info(f"[tool_xml_guard] 从 XML 里救回 {saved} 条提案，已入箱")
            if changed:
                logger.info("[tool_xml_guard] 已把工具XML从消息里删掉")
        except Exception as e:
            logger.warning(f"[tool_xml_guard] 放行：{e}")
