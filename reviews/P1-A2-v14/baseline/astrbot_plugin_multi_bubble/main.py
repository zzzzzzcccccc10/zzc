"""Send a reply as two or three bubbles with human-like pauses.

Design constraint learned the hard way: never swallow the whole reply. The
first bubble goes out through the normal pipeline (so a failure here can only
cost the extra bubbles, not the message). Remaining bubbles are sent by a
background task through context.send_message.

Split rules:
  - needs enough text to split at all
  - splits on sentence ends first; falls back to commas only for long text
  - keeps meme markers attached to the last bubble
  - hard cap of 3 bubbles, no fragments shorter than 3 chars
"""

import asyncio
import random
import re
from collections import defaultdict
from typing import Dict, List

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.message_components import Face, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.api.star import Context, Star, register

# 补发的气泡不经过 decorating 阶段，[微笑] 这类 token 不会自动变成黄脸，
# 这里复用 face_map 插件里的表；取不到就退化成纯文本。
try:
    from data.plugins.astrbot_plugin_face_map.main import FACE_MAP as _FACE_MAP
    from data.plugins.astrbot_plugin_face_map.main import TOKEN_RE as _TOKEN_RE
except Exception:  # pragma: no cover - 插件被禁用时走这里
    _FACE_MAP, _TOKEN_RE = {}, None

# 2026-11-17（P1-A1）：补发的气泡走 context.send_message，不经过 decorating，
# 所以清洗必须在这里自己做——拆之前一次，每条发出去之前再一次。
try:
    from data.plugins.astrbot_plugin_tool_xml_guard.main import finalize_text as _finalize_text
except Exception:  # pragma: no cover - 清洗器不可用时按 fail-closed 处理
    _finalize_text = None

MIN_LEN = 28
_REPLACE = str.maketrans({",": "\uff0c", "\u3001": "\uff0c", "\uff1b": "\uff0c", ";": "\uff0c", "\u3002": "", "\uff0e": ""})


def _tidy(text: str) -> str:
    """直发路径也要过一遍标点清理，不然同一个人一半带句号一半不带。"""
    import re as _re
    if not text:
        return text
    s = text.translate(_REPLACE)
    s = _re.sub(r"\u2014{2,}|\u2014", "\uff0c", s)
    s = _re.sub(r"\uff0c{2,}", "\uff0c", s)
    s = _re.sub(r"\uff0c\s+", "\uff0c", s)  # 逗号后面的空格
    s = _re.sub(r"[ \t]{2,}", " ", s)
    s = _re.sub(r"\s+([\uff1f\uff01~\u2026])", r"\1", s)
    s = _re.sub(r"^[\uff0c\s]+|[\uff0c\s]+$", "", s)
    return s.strip()

def _rid(event) -> str:
    """日志关联用的短 request id（拿不到就 -）。"""
    try:
        from astrbot.core import trust_context as tc

        t = tc.current(event)
        if isinstance(t, dict):
            rid = str(t.get("request_id") or "")
            return rid[:12] if rid else "-"
    except Exception:
        pass
    return "-"


MIN_SPLIT_TOTAL = 60   # 少于这么多字不拆
MIN_PART = 2
MAX_BUBBLES = 2
CLAUSE_MIN_LEN = 70
MARKER_RE = re.compile(r"&&[^&\n]{1,64}&&")
SENT_SPLIT = re.compile(r"(?<=[。！？!?~])")
CLAUSE_SPLIT = re.compile(r"(?<=[，,、；;])")

# 书名号/引号/括号里面的句子不许拆——《大肥鱼完整的一生!》这种标题里带感叹号，
# 一拆就变成「《…完整的一生!」+「）」，看着像断线的机器。
BRACKETS = (("《", "》"), ("「", "」"), ("（", "）"), ("(", ")"), ("“", "”"), ("【", "】"))


def _merge_unbalanced(units: List[str]) -> List[str]:
    merged: List[str] = []
    buffer = ""
    for unit in units:
        buffer += unit
        if all(buffer.count(o) == buffer.count(c) for o, c in BRACKETS):
            merged.append(buffer)
            buffer = ""
    if buffer:
        if merged:
            merged[-1] += buffer
        else:
            merged.append(buffer)
    return merged


@register(
    "astrbot_plugin_multi_bubble",
    "dsh",
    "split replies into bubbles without swallowing the message",
    "2.0.0",
)
class MultiBubblePlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.cfg = config or {}
        self._pending_parts: Dict[str, List[List[str]]] = defaultdict(list)

    def _max_bubbles(self) -> int:
        try:
            return max(2, min(20, int(self.cfg.get("max_bubbles", MAX_BUBBLES))))
        except Exception:
            return MAX_BUBBLES

    def _split(self, text: str) -> List[str]:
        # 太短就别拆：一句话拆成两条，读起来像重复说了一遍（2026-11-01）
        if len(MARKER_RE.sub("", text).strip()) < MIN_SPLIT_TOTAL:
            return []
        body = MARKER_RE.sub("", text).strip()
        markers = " ".join(MARKER_RE.findall(text))
        cap = self._max_bubbles()

        units = [s for s in SENT_SPLIT.split(body) if s.strip()]
        if len(units) < 2:
            if len(body) >= CLAUSE_MIN_LEN:
                units = [s for s in CLAUSE_SPLIT.split(body) if s.strip()]
            if len(units) < 2:
                return []
        # 把落在书名号/引号里的断句合回去
        units = _merge_unbalanced(units)
        if len(units) < 2:
            return []

        n = min(cap, len(units))
        per = max(1, round(len(units) / n))
        parts: List[str] = []
        for i in range(0, len(units), per):
            chunk = "".join(units[i : i + per]).strip()
            if chunk:
                parts.append(chunk)
        # 先合并再截断：原来先 parts[:cap] 再合并，超出 cap 的内容会直接丢掉
        # （2026-11-02：她答 5 题只发出 3 条，第 4 条就这么没的）
        if len(parts) > cap:
            parts = parts[: cap - 1] + ["".join(parts[cap - 1:])]

        if len(parts) < 2 or any(len(p) < MIN_PART for p in parts):
            return []
        # 拆出来的两条如果意思太像，就别拆（"今天没追…明天再看"这种）
        if len(parts) >= 2:
            a, b = parts[0], parts[1]
            sa, sb = set(a), set(b)
            if sa and sb and len(sa & sb) / min(len(sa), len(sb)) > 0.75:
                return []
        if markers:
            parts[-1] = (parts[-1] + "\n" + markers).strip()
        return parts

    @staticmethod
    def _to_chain(part: str) -> MessageChain:
        """把 [微笑] 这类 token 换成 Face，其余原样。"""
        if not _FACE_MAP or _TOKEN_RE is None or "[" not in part:
            return MessageChain([Plain(part)])
        chain = []
        buffer: List[str] = []
        for piece in _TOKEN_RE.split(part):
            if not piece:
                continue
            if piece in _FACE_MAP:
                if buffer:
                    chain.append(Plain("".join(buffer)))
                    buffer = []
                chain.append(Face(id=_FACE_MAP[piece]))
            else:
                buffer.append(piece)
        if buffer:
            chain.append(Plain("".join(buffer)))
        return MessageChain(chain or [Plain(part)])

    async def _send_rest(self, umo: str, parts: List[str], rid: str = "-") -> None:
        # T1：间隔按这一条的长度浮动，长句多停一点；上限 gap_max（默认 2.5 秒，比原来 4 秒快）
        gap_max = float(self.cfg.get("gap_max", 2.5))
        for part in parts:
            # 直发通道没有装饰阶段兜底：每条发出去之前再清洗一次（fail-closed）
            if _finalize_text is None:
                logger.warning(f"[multi_bubble] 清洗器不可用，中止剩余补发 req={rid}")
                return
            try:
                cleaned = _finalize_text(part)
            except Exception as e:
                logger.warning(
                    f"[multi_bubble] 补发清洗失败，中止剩余补发（{type(e).__name__}）req={rid}")
                return
            text = _tidy(cleaned)
            if not text.strip():
                logger.info(f"[multi_bubble] 清洗后为空，跳过这条气泡 req={rid}")
                continue
            gap = min(gap_max, max(0.6, len(text) * 0.06)) + random.uniform(0.0, 0.4)
            await asyncio.sleep(gap)
            try:
                await self.context.send_message(umo, self._to_chain(text))
            except Exception as e:
                # 发不出去就中止剩余补发，避免后面的气泡越过失败的那一条
                logger.warning(
                    f"[multi_bubble] 追加气泡失败（{type(e).__name__}），中止剩余补发 req={rid}")
                return

    @filter.after_message_sent()
    async def after_sent(self, event: AstrMessageEvent) -> None:
        """第一条真的发出去之后，才补后面的。

        2026-11-02 修：原来在 on_llm_resp 里立刻起后台任务，管道那条（引用、
        标点清洗、真正发送）只要超过 1.2 秒，第二条就先到——用户看到的顺序是
        「6-10 → 1-5 → 11-15」。现在挂在 after_message_sent 上，顺序就定了。
        """
        try:
            umo = event.unified_msg_origin
            queues = self._pending_parts.get(umo)
            if not queues:
                return
            parts = queues.pop(0)
            if not queues:
                self._pending_parts.pop(umo, None)
            if parts:
                asyncio.create_task(self._send_rest(umo, parts, _rid(event)))
        except Exception as e:
            logger.warning(
                f"[multi_bubble] 补发调度失败（{type(e).__name__}）req={_rid(event)}")

    @filter.on_llm_response()
    async def on_llm_resp(self, event: AstrMessageEvent, resp):
        if not self.cfg.get("enable", True):
            return
        try:
            text = getattr(resp, "completion_text", "") or ""
        except Exception:
            return
        if len(text.strip()) < MIN_LEN:
            return

        # 拆之前先清洗：拆分是在 on_llm_response 做的，此时还没经过装饰阶段，
        # 不清洗的话控制标记会被分到第 2 段之后、随直发通道漏出去。
        if _finalize_text is None:
            logger.warning("[multi_bubble] 清洗器不可用，本轮不拆分（整条走管道）")
            return
        try:
            cleaned = _finalize_text(text)
        except Exception as e:
            logger.warning(
                f"[multi_bubble] 预处理清洗失败，取消本轮拆分/补发（{type(e).__name__}）req={_rid(event)}")
            return
        if not cleaned.strip():
            logger.info("[multi_bubble] 清洗后为空，不拆分也不补发")
            return
        text = cleaned
        try:
            resp.completion_text = text
        except Exception:
            pass

        if len(text.strip()) > 6:
            try:
                think_max = float(self.cfg.get("think_max", 2.5))
                if "戳了戳你" in (event.message_str or ""):
                    think = 0.0
                else:
                    think = min(think_max, max(0.6, len(text) * 0.03))
                # B10：情绪影响开口速度（心情好快一点，低落慢一点）
                try:
                    import json as _j
                    st = Path("/AstrBot/data/plugin_data/astrbot_plugin_growth/state.json")
                    mood = float((_j.loads(st.read_text(encoding="utf-8")) or {}).get("mood") or 0)
                    if mood <= -0.3:
                        think = min(2.6, think * 1.35)
                    elif mood >= 0.4:
                        think = max(0.3, think * 0.7)
                except Exception:
                    pass
                if think > 0:
                    logger.info(f"[multi_bubble] 想 {think:.1f}s 再开口")
                    await asyncio.sleep(think)
            except Exception:
                pass

        parts = self._split(text)
        if len(parts) < 2:
            return

        # 第一条走正常管道；其余排队，等第一条真的发出去了再按顺序补
        try:
            resp.completion_text = parts[0]
            self._pending_parts[event.unified_msg_origin].append(parts[1:])
            logger.info(f"[multi_bubble] 首条走管道，排队 {len(parts) - 1} 条待补发")
        except Exception as e:
            logger.warning(f"[multi_bubble] 拆分失败，保持整条: {e}")
