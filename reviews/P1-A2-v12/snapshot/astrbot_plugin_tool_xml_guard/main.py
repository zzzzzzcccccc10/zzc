"""她要是把工具调用写成了 XML 文本，就替她执行 + 把控制标记从消息里抹掉。

为什么需要
----------
deepseek-v4-pro 有时不走 function calling，而是在回复正文里输出
`<invoke name="propose_change"><parameter name="scope">…` 这种 XML
（2026-11-02 15:46 实测：用户屏幕上直接看到一堆标签，提案一条没落库）。

这个插件做两件事：
1. 认出这种 XML（普通格式和 `<｜｜DSML｜｜ …>` 包裹格式都认），按她的意图执行（目前支持 propose_change）
2. 把控制标记从发出去的文本里删干净

2026-11-17 修（P1-A1 第一版）：原来删除顺序错，`<｜｜DSML｜｜ calls>` 会被剩成 `<｜｜ calls>` 发出去。

2026-11-18 修（第二版，按审查意见）
---------------------------------
- 读取结果失败也 fail-closed；日志只记异常类型 + request_id
- DSML 规则收紧到白名单标签；普通竖线文本、未闭合标记按原文保留
- 代码围栏原样拼回，空白收敛只在非代码片段做
- `has_marker()` 大小写不敏感；`parse_invokes()` 普通 XML / DSML 双格式

2026-11-18 修（第三版，v4）
--------------------------
- **围栏按行识别**：开始 `^ {0,3}(```|~~~)`；结束必须独立行、同字符、长度不小于开始、后面只有空白；
  未闭合一路保护到文本末尾。代码块里出现的字面量三反引号不会被当成结束标记。
- **文本保真**：不再对整条 `lstrip()`；没发生删除的片段逐字返回；只清理删除标记产生的多余空行，
  原文本来就有的连续空行不动。
- **执行顺序**：AstrBot 的 `append()` 是 `sort(key=-priority)`（**priority 大的先执行**），
  所以"最后一道清洗"要用**最小** priority（-1000000），而不是最大。

2026-11-19 修（P1-A2，按 v7 规范与施工方案 v4）
---------------------------------------------
- 控制标记识别改成显式形态匹配：双竖线（主形态）与单竖线（受限形态），带尖括号 / 裸标记分开。
- 保护区扩成两种：CODE（围栏 + 行内代码）与 QUOTE（同段落成对引号），并叠加 SYNTAX 区间排除属性引号。
- R1 改成严格栈式配对：完整配对才整段删；有起无闭只删起始标签；错名 / 嵌套未闭合 / 属性未闭合一律不删；
  跨段落视为不完整（R1-e）。
- R2 只删到明确的 `>`；没有 `>` 时只删标记和标签名（R2-B）；R3 只删标记，不动其余空白。
- 与保护区相交的完整结构整体跳过（R1-f），其内部标记不再回流 R2/R3。
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

# 普通 XML 格式
INVOKE_RE = re.compile(r"<invoke\s+name=\"([^\"]+)\">(.*?)</invoke>", re.S | re.I)
PARAM_RE = re.compile(r"<parameter\s+name=\"([^\"]+)\">(.*?)</parameter>", re.S | re.I)

# 会被模型当正文吐出来的内部标签（2026-11-02 按大肥鱼配置包的 dafeiyu_clean 扩充）
LEAK_TAGS = ("system_reminder", "image_caption", "thinking", "tool_call",
             "tool_response", "function_call", "antml:invoke")

# 允许出现在 XML 与 DSML 结构里的标签名（白名单：不在这份名单里的尖括号文本一律不动）
_XML_NAMES = ("calls", "invoke", "parameter") + LEAK_TAGS
_TAGS = "|".join(_XML_NAMES)

# deepseek 的内部结构标记（提案救回正则沿用旧形态；清洗主循环用显式形态匹配）
_DSML = r"<[｜|]+\s*DSML\s*[｜|]+"

# DSML 包裹的 invoke/parameter（用于提案救回）
_DSML_INVOKE = re.compile(
    _DSML + r"\s*invoke\s+name=\"([^\"]+)\"[^>]*>(.*?)" + _DSML + r"\s*/\s*invoke>",
    re.S | re.I,
)
_DSML_PARAM = re.compile(
    _DSML + r"\s*parameter\s+name=\"([^\"]+)\"[^>]*>(.*?)" + _DSML + r"\s*/\s*parameter>",
    re.S | re.I,
)

# 用来判断"要不要进清洗流程"（大小写不敏感）
_MARKER = re.compile(r"DSML|<(?:" + _TAGS + r")\b", re.I)

# 代码围栏：按行识别开始标记（``` 或 ~~~，允许最多 3 个前导空格）
_FENCE_OPEN = re.compile(r"(?m)^ {0,3}(`{3,}|~{3,})[^\n]*\n")

# 段落边界：空行（允许空白行）。CRLF 的 \r\n\r\n 同样命中。
_PARA_BREAK = re.compile(r"\n[ \t\r]*\n")

# 普通 XML 标签（白名单）
_XML_START = re.compile(r"<(" + _TAGS + r")(?=[\s>/]|$)", re.I)
_XML_CLOSE = re.compile(r"</(" + _TAGS + r")\s*>", re.I)


# ---------------------------------------------------------------- 通用小工具

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


def _is_escaped(text: str, pos: int) -> bool:
    """pos 前的连续反斜杠为奇数 → 该字符已转义。"""
    bs = 0
    j = pos - 1
    while j >= 0 and text[j] == "\\":
        bs += 1
        j -= 1
    return bs % 2 == 1


def _merge_regions(regions):
    """排序并合并重叠/相邻区间。"""
    if not regions:
        return []
    ordered = sorted(regions)
    out = [list(ordered[0])]
    for s, e in ordered[1:]:
        if s <= out[-1][1]:
            if e > out[-1][1]:
                out[-1][1] = e
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def _region_index(regions, pos):
    """pos 落在哪个区间（半开 [start, end)）。"""
    for idx, (s, e) in enumerate(regions):
        if s <= pos < e:
            return idx
    return None


def _overlaps(regions, start: int, end: int) -> bool:
    """[start, end) 是否与任一保护区区间相交。"""
    for s, e in regions:
        if start < e and s < end:
            return True
    return False


def _apply_deletions(text: str, dels) -> str:
    """按合并后的删除区间重建文本。"""
    if not dels:
        return text
    merged = _merge_regions(dels)
    out = []
    last = 0
    for s, e in merged:
        if s < last:
            s = last
        if e <= last:
            continue
        out.append(text[last:s])
        last = e
    out.append(text[last:])
    return "".join(out)


# ---------------------------------------------------------------- 形态匹配

def _marker_at(text: str, pos: int):
    """在 pos 处尝试匹配一个 DSML 标记。

    返回 dict(kind, start, end, angle, vcount, is_close) 或 None。
    kind: open_double / close_double / open_single / close_single

    额外兼容一种叠加残片 `</<｜｜DSML｜｜ …>`：模型把 `</` 和 `<｜｜DSML｜｜` 打了两次，
    这里按「闭合标签」整体保留（D1 精神），避免删掉内部标记后只剩一个孤零零的 `</`。
    """
    n = len(text)
    i = pos
    has_angle = False
    is_close = False
    start = pos
    if i + 1 < n and text[i] == "<" and text[i + 1] == "/":
        has_angle = True
        is_close = True
        i += 2
    elif i >= 2 and text[i] == "<" and text[i - 1] == "/" and text[i - 2] == "<":
        # `</<` 叠加：从外层的 `</` 开始算闭合标签
        start = i - 2
        has_angle = True
        is_close = True
        i += 1
    elif i < n and text[i] == "<":
        has_angle = True
        i += 1

    j = i
    while j < n and text[j] in "｜|":
        j += 1
    vcount = j - i
    if vcount not in (1, 2):
        return None
    if text[j:j + 4].upper() != "DSML":
        return None
    j += 4

    k = j
    while k < n and text[k] in "｜|":
        k += 1
    if k - j != vcount:
        return None

    kind = ("close" if is_close else "open") + ("_double" if vcount == 2 else "_single")
    return {
        "kind": kind,
        "start": pos,
        "end": k,
        "angle": has_angle,
        "vcount": vcount,
        "is_close": is_close,
    }


def _find_marker(text: str, pos: int):
    """从 pos 起找第一个 DSML 标记（跳过普通字符）。"""
    n = len(text)
    i = pos
    while i < n:
        c = text[i]
        if c in "<｜|":
            m = _marker_at(text, i)
            if m:
                return m
        i += 1
    return None


# ---------------------------------------------------------------- 属性扫描

def _is_name_start(c: str) -> bool:
    return ("A" <= c <= "Z") or ("a" <= c <= "z") or c == "_"


def _is_name_char(c: str) -> bool:
    return _is_name_start(c) or ("0" <= c <= "9") or c in "-:"


def _scan_attrs(text: str, start: int):
    """从 start 扫描到引号外第一个 `>`。

    返回 (status, index)：
    - FOUND_END: index 是 `>` 的位置
    - UNTERMINATED_ATTRIBUTE: index 是文本末尾（属性值引号未闭合）
    - MISSING_END: index 是文本末尾（没有 `>`，也没有未闭合属性）
    """
    n = len(text)
    i = start
    while i < n:
        c = text[i]
        if c == ">":
            return ("FOUND_END", i)
        if c in "\"'":
            # 只有完整属性赋值（属性名 = "值"）才开启属性值；普通撇号不开启
            j = i - 1
            while j >= start and text[j] in " \t":
                j -= 1
            if j >= start and text[j] == "=":
                k = j - 1
                while k >= start and text[k] in " \t":
                    k -= 1
                if k >= start and _is_name_char(text[k]):
                    t = k
                    while t >= start and _is_name_char(text[t]):
                        t -= 1
                    if t + 1 <= k and _is_name_start(text[t + 1]):
                        close = text.find(c, i + 1)
                        if close == -1:
                            return ("UNTERMINATED_ATTRIBUTE", n)
                        i = close + 1
                        continue
        i += 1
    return ("MISSING_END", n)


# ---------------------------------------------------------------- 标签名匹配

_TAG_RE = re.compile(r"(?i)(" + _TAGS + r")(?=[ \t>/]|$)")


def _match_tag(text: str, pos: int):
    """在 pos（可隔空白）匹配白名单标签名。返回 (name, end, start) 或 None。"""
    j = pos
    while j < len(text) and text[j] in " \t":
        j += 1
    m = _TAG_RE.match(text, j)
    if not m:
        return None
    return (m.group(1).lower(), m.end(), j)


def _match_new_close(text: str, marker):
    """第二种闭合形式 `<｜｜DSML｜｜ /name>`（2026-11-20 裁定，v8 修订）。

    严格形态：带尖括号、双竖线；标记后至少一个空格/Tab；`/` 后紧跟完整白名单标签名；
    标签名后只允许空格/Tab 和 `>`。返回 (name, end_after_gt) 或 None。
    不允许属性或任何额外内容。
    """
    if marker["kind"] != "open_double" or not marker["angle"]:
        return None
    n = len(text)
    i = marker["end"]
    start = i
    while i < n and text[i] in " \t":
        i += 1
    if i == start:          # 至少要有一个空格/Tab
        return None
    if i >= n or text[i] != "/":
        return None
    i += 1
    tag = _match_tag(text, i)
    if tag is None or tag[2] != i:   # `/` 后不能隔空白
        return None
    j = tag[1]
    while j < n and text[j] in " \t":
        j += 1
    if j >= n or text[j] != ">":
        return None
    return (tag[0], j + 1)


def _match_close_tag(text: str, marker):
    """标准闭合 `</｜｜DSML｜｜ name>` 的严格校验。

    标签名后只允许空格/Tab 和 `>`；带属性或多余文本返回 None（按异常处理，不删正文）。
    """
    if not marker["is_close"]:
        return None
    tag = _match_tag(text, marker["end"])
    if tag is None:
        return None
    n = len(text)
    j = tag[1]
    while j < n and text[j] in " \t":
        j += 1
    if j >= n or text[j] != ">":
        return None
    return (tag[0], j + 1)


# ---------------------------------------------------------------- 保护区：CODE

def _code_regions(text: str):
    """按行识别代码围栏，返回 [(start, end)]（含围栏行）。未闭合一直保护到文本末尾。"""
    regions = []
    pos = 0
    while True:
        m = _FENCE_OPEN.search(text, pos)
        if not m:
            break
        fence = m.group(1)
        ch, n = fence[0], len(fence)
        # Windows 换行（CR LF）：$ 匹配不到行尾 \r 前的位置，必须显式允许 \r
        close = re.compile(r"(?m)^ {0,3}" + re.escape(ch) + "{%d,}[ \t]*\r?$" % n)
        c = close.search(text, m.end())
        end = c.end() if c else len(text)
        regions.append((m.start(), end))
        pos = end
    return regions


def _inline_code_regions(text: str):
    """行内代码：单反引号成对，不跨行；前面奇数个反斜杠的反引号不算闭合。"""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "`" and not _is_escaped(text, i):
            k = i + 1
            found = None
            while k < n and text[k] != "\n":
                if text[k] == "`" and not _is_escaped(text, k):
                    found = k
                    break
                k += 1
            if found is not None:
                out.append((i, found + 1))
                i = found + 1
                continue
        i += 1
    return out


def _split_code(text: str):
    """把文本切成 [(is_code, segment)]，代码段原文不动。"""
    out = []
    last = 0
    for s, e in _code_regions(text):
        out.append((False, text[last:s]))
        out.append((True, text[s:e]))
        last = e
    out.append((False, text[last:]))
    return out


def _no_code(text: str) -> str:
    """给「解析提案」用的视图：代码块与行内代码一律扣掉，避免把示例当成真调用。"""
    parts = []
    for is_code, seg in _split_code(text or ""):
        if not is_code:
            regions = _inline_code_regions(seg)
            parts.append(_apply_deletions(seg, regions))
    return "".join(parts)


# ---------------------------------------------------------------- 保护区：SYNTAX / QUOTE

def _syntax_regions(text: str, code_regions):
    """在 CODE 外扫描语法区间（DSML 标记 + 白名单普通 XML 标签）。

    起始标签：[标记起点, `>` 前)。
    闭合标签：[标记起点, `>` 前) —— 整体一个区间，内部不产生 QUOTE。
    属性未闭合 / 无 `>`：一直保护到文本末尾。
    普通 XML 也要进 SYNTAX，否则 `name="x"` 的属性引号会被误当成 QUOTE。
    """
    out = []
    n = len(text)

    i = 0
    while i < n:
        ri = _region_index(code_regions, i)
        if ri is not None:
            i = code_regions[ri][1]
            continue
        m = _find_marker(text, i)
        if not m:
            break
        ri = _region_index(code_regions, m["start"])
        if ri is not None:
            i = code_regions[ri][1]
            continue
        if m["is_close"]:
            ct = _match_close_tag(text, m)
            if ct is None:
                # 异常闭合不是合法语法单元，不生成 SYNTAX
                i = max(m["end"], i + 1)
                continue
            out.append((m["start"], ct[1] - 1))
            i = max(ct[1], m["end"])
            continue
        nc = _match_new_close(text, m)
        if nc is not None:
            # 合法第二种闭合：语法区间到 `>` 前
            out.append((m["start"], nc[1] - 1))
            i = max(nc[1], m["end"])
            continue
        if _match_tag(text, m["end"]) is None:
            # 候选 / 裸标记 / 非标签：不是合法语法单元，不生成 SYNTAX
            i = max(m["end"], i + 1)
            continue
        status, idx = _scan_attrs(text, m["end"])
        if status == "FOUND_END":
            out.append((m["start"], idx))
            i = max(idx, m["end"])
        elif status == "UNTERMINATED_ATTRIBUTE":
            out.append((m["start"], n))
            i = n
        else:
            i = max(m["end"], i + 1)

    i = 0
    while i < n:
        ri = _region_index(code_regions, i)
        if ri is not None:
            i = code_regions[ri][1]
            continue
        x = _XML_START.search(text, i)
        c = _XML_CLOSE.search(text, i)
        cands = [v for v in ((x.start() if x else None), (c.start() if c else None))
                 if v is not None]
        if not cands:
            break
        start = min(cands)
        ri = _region_index(code_regions, start)
        if ri is not None:
            i = code_regions[ri][1]
            continue
        gt = text.find(">", start)
        end = gt if gt != -1 else n
        out.append((start, end))
        i = max(end, start + 1)

    return _merge_regions(out)


def _in_same_syntax(open_pos: int, close_end: int, syntax_regions) -> bool:
    for s, e in syntax_regions:
        if s <= open_pos and close_end <= e:
            return True
    return False


def _paragraphs(text: str):
    out = []
    last = 0
    for m in _PARA_BREAK.finditer(text):
        out.append((last, m.start()))
        last = m.end()
    out.append((last, len(text)))
    return out


def _quotes_in(text: str, start: int, end: int, syntax_regions):
    """同一段落内配对引号。返回 [(open_pos, close_pos+1)]。"""
    out = []
    pairs = {"“": "”", "‘": "’", "「": "」", "『": "』"}
    stack = []
    i = start
    while i < end:
        c = text[i]
        if c in pairs:
            stack.append((c, i))
        elif c in pairs.values():
            for j in range(len(stack) - 1, -1, -1):
                oc, op = stack[j]
                if pairs[oc] == c:
                    del stack[j:]
                    if not _in_same_syntax(op, i + 1, syntax_regions):
                        out.append((op, i + 1))
                    break
        i += 1

    # 半角双引号：前面奇数个反斜杠的不参与配对
    positions = []
    esc = 0
    i = start
    while i < end:
        c = text[i]
        if c == "\\":
            esc += 1
        elif c == '"':
            if esc % 2 == 0:
                positions.append(i)
            esc = 0
        else:
            esc = 0
        i += 1
    for k in range(0, len(positions) - 1, 2):
        o, c2 = positions[k], positions[k + 1]
        if not _in_same_syntax(o, c2 + 1, syntax_regions):
            out.append((o, c2 + 1))
    return out


def _quote_regions(text: str, syntax_regions):
    out = []
    for s, e in _paragraphs(text):
        out.extend(_quotes_in(text, s, e, syntax_regions))
    return _merge_regions(out)


# ---------------------------------------------------------------- R1 栈式配对

class _Match:
    __slots__ = ("kind", "start", "end", "tag_end", "skip_to")

    def __init__(self, kind, start=0, end=0, tag_end=0, skip_to=0):
        self.kind = kind
        self.start = start
        self.end = end
        self.tag_end = tag_end
        self.skip_to = skip_to


def _paragraph_end(text: str, pos: int) -> int:
    m = _PARA_BREAK.search(text, pos)
    return m.start() if m else len(text)


def _candidate_regions(text: str, code_regions, quote_regions, syntax_regions):
    """非法新闭合候选：从标记起点到候选终点整体隔离。

    候选定义：带尖括号的双竖线起始标记，标记后（可隔空白）以 `/` 开头，
    但没有通过 `_match_new_close()` 的严格校验。
    隔离区间不参与 R1/R2/R3，也不让普通 XML 清理进入；候选之后的内容照常处理。

    CODE 与 QUOTE 内的标记不识别；被外层合法标签的 SYNTAX 区间包含的标记
    （例如属性值里的伪候选）也不算独立候选。
    """
    out = []
    n = len(text)
    skip = _merge_regions(list(code_regions) + list(quote_regions))
    i = 0
    while i < n:
        ri = _region_index(skip, i)
        if ri is not None:
            i = skip[ri][1]
            continue
        m = _find_marker(text, i)
        if not m:
            break
        ri = _region_index(skip, m["start"])
        if ri is not None:
            i = skip[ri][1]
            continue
        pos = m["start"]
        if any(s < pos < e for s, e in syntax_regions):
            # 外层合法标签的属性值内伪候选：不是独立候选
            i = max(m["end"], i + 1)
            continue
        if m["kind"] == "open_double" and m["angle"] and _match_new_close(text, m) is None:
            j = m["end"]
            while j < n and text[j] in " \t":
                j += 1
            if j < n and text[j] == "/":
                st, gt = _scan_attrs(text, m["end"])
                end = gt + 1 if st == "FOUND_END" else n
                out.append((m["start"], end))
                i = end
                continue
        i = max(m["end"], i + 1)
    return _merge_regions(out)


def _match_r1(text: str, pos: int, regions, max_depth_box=None):
    """从 pos 处的双竖线起始标签开始做栈式配对。

    max_depth_box: 可选 [int]，用于把内层最大深度带出去（供 UNCLOSED 区分 C1 / NESTED）。
    """
    first = _marker_at(text, pos)
    nc_first = _match_new_close(text, first)
    if nc_first is not None:
        # 孤立的第二种闭合形式：整体保留（与 R1-d 一致）
        return _Match("ORPHAN_CLOSE", start=pos, skip_to=nc_first[1])
    # 先认标签名：标记后不是白名单标签 → 不是 R1 起始，交给 R2/R3，
    # 不能先扫属性（否则 MISSING_END 会把整段吞到末尾）
    tag = _match_tag(text, first["end"])
    if tag is None:
        return _Match("NOT_R1")
    status, gt = _scan_attrs(text, first["end"])
    if status == "UNTERMINATED_ATTRIBUTE":
        return _Match("ATTR_UNTERMINATED", start=pos, skip_to=len(text))
    if status == "MISSING_END":
        return _Match("ATTR_UNTERMINATED", start=pos, skip_to=len(text))

    para_end = _paragraph_end(text, gt + 1)
    stack = [tag[0]]
    depth = 1
    i = gt + 1
    n = len(text)
    while i < n:
        if i > para_end:
            return _Match("CROSS_PARAGRAPH", start=pos, tag_end=gt + 1)
        ri = _region_index(regions, i)
        if ri is not None:
            i = regions[ri][1]
            continue
        m = _find_marker(text, i)
        if not m:
            break
        if m["start"] > para_end:
            return _Match("CROSS_PARAGRAPH", start=pos, tag_end=gt + 1)
        i = m["start"]
        ri = _region_index(regions, i)
        if ri is not None:
            # 保护区 / 隔离区内的标记不参与配对，也不回流
            i = regions[ri][1]
            continue
        kind = m["kind"]
        if kind == "open_double" and m["angle"]:
            nc = _match_new_close(text, m)
            if nc is not None:
                # 第二种闭合形式参与原有的严格栈式配对
                if not stack:
                    return _Match("ORPHAN_CLOSE", start=pos, skip_to=nc[1])
                if nc[0] != stack[-1]:
                    return _Match("MISMATCH", start=pos, skip_to=nc[1])
                stack.pop()
                if not stack:
                    return _Match("COMPLETE", start=pos, end=nc[1])
                i = nc[1]
                continue
            # 格式错误的新闭合候选（兜底；正常已由 _candidate_regions 隔离）
            j = m["end"]
            while j < n and text[j] in " \t":
                j += 1
            if j < n and text[j] == "/":
                st2, g3 = _scan_attrs(text, m["end"])
                i = g3 + 1 if st2 == "FOUND_END" else n
                continue
            # 先认标签名：标记后不是白名单标签（如裸标记后跟普通正文）→ 跳过，
            # 不能当成起始标签扫描属性，否则会误触发 ATTR_UNTERMINATED 吞掉整段
            t2 = _match_tag(text, m["end"])
            if t2 is None:
                i = m["end"]
                continue
            st, g2 = _scan_attrs(text, m["end"])
            if st == "UNTERMINATED_ATTRIBUTE":
                return _Match("ATTR_UNTERMINATED", start=pos, skip_to=n)
            if st == "MISSING_END":
                return _Match("ATTR_UNTERMINATED", start=pos, skip_to=n)
            stack.append(t2[0])
            depth = max(depth, len(stack))
            i = g2 + 1
        elif kind == "close_double":
            ct = _match_close_tag(text, m)
            if ct is None:
                # 闭合标签带属性 / 多余文本 / 未知标签：按异常处理，不猜、不删。
                # 终点用引号感知扫描，属性值里的 `>` 不能截断 skip_to
                st2, g2 = _scan_attrs(text, m["end"])
                return _Match("MISMATCH", start=pos,
                              skip_to=(g2 + 1 if st2 == "FOUND_END" else n))
            if not stack:
                return _Match("ORPHAN_CLOSE", start=pos, skip_to=ct[1])
            if ct[0] != stack[-1]:
                return _Match("MISMATCH", start=pos, skip_to=ct[1])
            stack.pop()
            if not stack:
                return _Match("COMPLETE", start=pos, end=ct[1])
            i = ct[1]
        else:
            # 单竖线 / 裸标记不参与 R1 栈
            i = m["end"]

    if max_depth_box is not None:
        max_depth_box[0] = depth
    if len(stack) == 1 and depth == 1:
        return _Match("UNCLOSED_SINGLE", start=pos, tag_end=gt + 1)
    return _Match("NESTED_UNCLOSED", start=pos, skip_to=n)


# ---------------------------------------------------------------- 普通 XML 清理

def _xml_deletions(text: str, regions):
    """白名单普通 XML 标签的删除区间（与保护区相交时整体跳过）。"""
    dels = []
    n = len(text)
    i = 0
    while i < n:
        ri = _region_index(regions, i)
        if ri is not None:
            i = regions[ri][1]
            continue
        m = _XML_START.search(text, i)
        if not m:
            break
        name = m.group(1).lower()
        start = m.start()
        if _region_index(regions, start) is not None:
            i = m.end()
            continue
        status, gt = _scan_attrs(text, m.end())
        if status != "FOUND_END":
            line_end = text.find("\n", m.end())
            if line_end == -1:
                line_end = n
            dels.append((start, line_end))
            i = line_end
            continue
        open_end = gt + 1
        close_re = re.compile(r"</" + re.escape(name) + r"\s*>", re.I)
        cm = close_re.search(text, open_end)
        if cm:
            ce = cm.end()
            if _overlaps(regions, start, ce):
                # 保护区里是示例/引用，不整段删，也不动保护区
                i = ce
                continue
            dels.append((start, ce))
            i = ce
            continue
        dels.append((start, open_end))
        i = open_end

    for cm in _XML_CLOSE.finditer(text):
        if _region_index(regions, cm.start()) is None:
            dels.append(cm.span())
    return dels


# ---------------------------------------------------------------- 清洗

def _clean_segment(t: str) -> str:
    """清洗一段非围栏文本。

    顺序：CODE → SYNTAX → QUOTE → 保护区 → DSML 主循环（R1/R2/R3）→ 普通 XML。
    """
    code = _merge_regions(_code_regions(t) + _inline_code_regions(t))
    syntax = _syntax_regions(t, code)
    quotes = _quote_regions(t, syntax)
    regions = _merge_regions(code + quotes)
    isolated = _candidate_regions(t, code, quotes, syntax)
    # 主循环 / R1 / 普通 XML 都用 skip：保护区 + 非法候选隔离区
    skip = _merge_regions(regions + isolated)

    dels = []
    i = 0
    n = len(t)
    while i < n:
        ri = _region_index(skip, i)
        if ri is not None:
            i = skip[ri][1]
            continue
        m = _find_marker(t, i)
        if not m:
            break
        ri = _region_index(skip, m["start"])
        if ri is not None:
            i = skip[ri][1]
            continue
        i = m["start"]
        kind = m["kind"]

        if kind in ("close_double", "close_single"):
            # R1-d / 4.2：孤立闭合标签整体保留（单竖线闭合也不残留 `</`）
            st2, gt = _scan_attrs(t, m["end"])
            i = gt + 1 if st2 == "FOUND_END" else n
            continue

        if kind == "open_double" and m["angle"]:
            nc = _match_new_close(t, m)
            if nc is not None:
                # 孤立的新闭合形式：整体保留，不删、不回流 R2/R3
                i = nc[1]
                continue
            res = _match_r1(t, i, skip)
            if res.kind == "COMPLETE":
                if _overlaps(skip, res.start, res.end):
                    i = res.end
                    continue
                dels.append((res.start, res.end))
                i = res.end
                continue
            if res.kind in ("UNCLOSED_SINGLE", "CROSS_PARAGRAPH"):
                dels.append((res.start, res.tag_end))
                i = res.tag_end
                continue
            if res.kind in ("ORPHAN_CLOSE", "MISMATCH", "NESTED_UNCLOSED",
                            "ATTR_UNTERMINATED"):
                i = res.skip_to
                continue
            # NOT_R1 → 落到 R2/R3

        # R2 / R3（裸标记、单竖线、非 R1 的双竖线标记）
        tag = _match_tag(t, m["end"])
        if tag is None:
            dels.append((m["start"], m["end"]))
            i = m["end"]
            continue
        status, gt = _scan_attrs(t, m["end"])
        if status == "FOUND_END":
            dels.append((m["start"], gt + 1))
            i = gt + 1
        else:
            # R2-B：只删标记和标签名，两者之间的空白原样保留
            dels.append((m["start"], m["end"]))
            dels.append((tag[2], tag[1]))
            i = tag[1]

    dels.extend(_xml_deletions(t, skip))
    return _apply_deletions(t, dels)


def parse_invokes(text: str) -> list[dict]:
    """普通 XML 与 DSML 包裹两种格式都解析。"""
    out = []
    for m in INVOKE_RE.finditer(text):
        name = m.group(1).strip()
        params = {p.group(1).strip(): p.group(2).strip()
                  for p in PARAM_RE.finditer(m.group(2))}
        out.append({"name": name, "params": params})
    for m in _DSML_INVOKE.finditer(text):
        name = m.group(1).strip()
        params = {p.group(1).strip(): p.group(2).strip()
                  for p in _DSML_PARAM.finditer(m.group(2))}
        out.append({"name": name, "params": params})
    return out


def _tidy_deleted(orig: str, cleaned: str) -> str:
    """只处理「删除标记」留下的整行空白；不碰任何原文空白。

    规则（v5，按审查 R1/R2 定）：
    1. 只删标签及其内部内容，**不修剪行尾空格、不动缩进、不压空行**。
    2. 删除后某一行只剩空白、而原文该行有内容 → 这行是标记被删走的残留，整行丢掉。
    3. 行数变化（成对结构跨行删除）时不做行级处理，原样返回，避免误删。
    """
    if cleaned == orig:
        return orig
    o_lines = orig.split("\n")
    c_lines = cleaned.split("\n")
    if len(o_lines) != len(c_lines):
        return cleaned
    out = []
    for o, c in zip(o_lines, c_lines):
        if c.strip() == "" and o.strip() != "":
            continue
        out.append(c)
    return "\n".join(out)


def _clean_span(seg: str) -> str:
    """清洗一段文本。没删除就逐字返回。"""
    if not seg:
        return seg
    cleaned = _clean_segment(seg)
    if cleaned == seg:
        return seg
    return _tidy_deleted(seg, cleaned)


def _clean_piece(piece: str) -> str:
    """清洗一段非围栏文本。"""
    if not piece:
        return piece
    return _clean_span(piece)


def finalize_text(text: str) -> str:
    """把控制标记删干净。幂等、代码块逐字保真、不做整条 strip。"""
    if not isinstance(text, str) or not text:
        return text or ""
    parts = []
    for is_code, seg in _split_code(text):
        parts.append(seg if is_code else _clean_piece(seg))
    return "".join(parts)


def strip_xml(text: str) -> str:
    """兼容旧调用：等价于 finalize_text。"""
    return finalize_text(text)


def has_marker(text: str) -> bool:
    """要不要进清洗流程。大小写不敏感，只认白名单标签与 DSML。"""
    if not isinstance(text, str) or not text:
        return False
    return bool(_MARKER.search(text))


def save_proposal(scope: str, prop: str, reason: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    scope = "本体" if "本体" in scope else "背景"
    entry = (f"\n## {stamp} · 她随时提（工具XML补录）· 待批\n"
             f"范围：{scope}\n提案：{prop.strip()}\n理由：{reason.strip()}\n")
    with PLAN.open("a", encoding="utf-8") as f:
        f.write(entry)


@register("astrbot_plugin_tool_xml_guard", "dsh", "把写错的工具XML执行掉并从消息里删掉", "1.3.0")
class ToolXmlGuard(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.cfg = config or {}

    def _stop(self, event, why: str) -> None:
        logger.error(f"[tool_xml_guard] {why}，按 fail-closed 停止发送 req={_rid(event)}")
        try:
            result = event.get_result()
            if result is not None:
                result.chain = []
        except Exception:
            pass
        try:
            event.stop_event()
        except Exception:
            pass

    # AstrBot 的 handler 按 -priority 排序（priority 越大越先跑），
    # 所以"最后一道清洗"要用最小 priority，保证在所有会改 chain 的钩子之后执行。
    @filter.on_decorating_result(priority=-1000000)
    async def guard(self, event: AstrMessageEvent) -> None:
        try:
            result = event.get_result()
        except Exception as e:  # noqa: BLE001
            self._stop(event, f"读取结果失败（{type(e).__name__}）")
            return
        if result is None or not result.chain:
            return

        targets = [
            comp for comp in result.chain
            if isinstance(comp, Plain) and has_marker(comp.text or "")
        ]
        if not targets:
            return

        try:
            saved = 0
            for comp in targets:
                text = comp.text or ""
                for call in parse_invokes(_no_code(text)):
                    if call["name"] != "propose_change":
                        continue
                    p = call["params"]
                    prop = p.get("proposal", "").strip()
                    if not prop:
                        continue
                    try:
                        save_proposal(p.get("scope", "背景"), prop, p.get("reason", ""))
                        saved += 1
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            f"[tool_xml_guard] 补录失败（{type(e).__name__}）req={_rid(event)}")
                comp.text = finalize_text(text)
            result.chain = [
                c for c in result.chain
                if not (isinstance(c, Plain) and not (c.text or "").strip())
            ]
            if saved:
                try:
                    subprocess.run([sys.executable, str(REVIEW), "刷新"],
                                   capture_output=True, timeout=30)
                except Exception:
                    pass
                logger.info(f"[tool_xml_guard] 从 XML 里救回 {saved} 条提案，已入箱")
            if not result.chain:
                logger.warning(
                    f"[tool_xml_guard] 清洗后为空，停止发送 req={_rid(event)}")
                event.stop_event()
                return
            logger.info(f"[tool_xml_guard] 已把控制标记从消息里删掉 req={_rid(event)}")
        except Exception as e:  # noqa: BLE001
            self._stop(event, f"清洗异常（{type(e).__name__}）")
