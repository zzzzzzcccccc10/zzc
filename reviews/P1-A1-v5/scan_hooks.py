#!/usr/bin/env python3
"""扫描所有插件的 `on_decorating_result` 注册点（静态、可复核）。

用法：
    python3 scan_hooks.py --root /AstrBot/data/plugins --json out.json
    python3 scan_hooks.py --root /opt/astrbot/data/plugins      # 宿主机路径

输出：
    - 每个注册点：插件名、priority（缺省 0）、源码行号、该行原文、插件 main.py 的 sha256
    - 按 priority 降序排序（= AstrBot 实际执行顺序，`append()` 里 sort(key=-priority)）
    - 结论：指定插件在全部注册点里的执行位次

覆盖边界（必须如实告知审查方）：
    1. 只扫描 `astrbot_plugin_*/main.py` 的**静态装饰器**写法，
       支持 `on_decorating_result(priority=N)` 与无参数的 `on_decorating_result()`。
    2. **不覆盖**：运行时动态注册、别名导入（`from ... import on_decorating_result as x`）、
       写在其它文件名里的注册（如 `decorating.py`）、以及 AstrBot 内置 handler。
    3. 因此本脚本能证明"静态可见的注册点里谁最后"，不能证明"运行时集合里没有别的钩子"。
       运行时集合的完整 dump 需要 AstrBot 暴露注册表读取接口（当前版本没有）。
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

PATTERN = r"on_decorating_result\(\s*(?:priority\s*=\s*(-?\d+)\s*)?\)"


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan(root: Path) -> list[dict]:
    import re

    pat = re.compile(PATTERN)
    rows = []
    for main in sorted(root.glob("astrbot_plugin_*/main.py")):
        try:
            data = main.read_bytes()
            src = data.decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            rows.append({"plugin": main.parent.name, "error": str(e)})
            continue
        sha = hashlib.sha256(data).hexdigest()
        for m in pat.finditer(src):
            line_no = src.count("\n", 0, m.start()) + 1
            line_text = src.splitlines()[line_no - 1].strip()
            rows.append({
                "plugin": main.parent.name,
                "priority": int(m.group(1)) if m.group(1) else 0,
                "file": str(main),
                "line": line_no,
                "source_line": line_text,
                "main_sha256": sha,
            })
    rows.sort(key=lambda r: (-r.get("priority", 0), r.get("plugin", "")))
    return rows


def core_evidence() -> dict:
    out = {"astrbot_version": None, "star_handler_sha256": None, "sort_impl": None}
    for base in ("/AstrBot", "/opt/astrbot"):
        ver = Path(base) / "astrbot" / "__init__.py"
        core = Path(base) / "astrbot" / "core" / "star" / "star_handler.py"
        if core.is_file():
            out["star_handler_sha256"] = file_sha256(core)
            try:
                src = core.read_text(encoding="utf-8", errors="replace")
                for ln in src.splitlines():
                    if "sort(key=lambda h: -h.extras_configs" in ln:
                        out["sort_impl"] = ln.strip()
                        break
            except Exception:
                pass
            break
    try:
        import astrbot  # noqa: F401

        out["astrbot_version"] = getattr(astrbot, "__version__", None)
    except Exception:
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/AstrBot/data/plugins")
    ap.add_argument("--json", default=None)
    ap.add_argument("--target", default="astrbot_plugin_tool_xml_guard")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"root not found: {root}", file=sys.stderr)
        return 2

    rows = scan(root)
    meta = core_evidence()
    target_rows = [r for r in rows if r.get("plugin") == args.target]

    print(f"root = {root}")
    print(f"注册点数量 = {len(rows)}")
    print()
    print("| 序 | 插件 | priority | 行号 | main.py sha256(前12) | 源码行 |")
    print("|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        sha = r["main_sha256"][:12] if r.get("main_sha256") else "-"
        print(f"| {i} | `{r['plugin']}` | {r['priority']} | {r['line']} | `{sha}` | `{r['source_line']}` |")

    print()
    if target_rows:
        pos = [i for i, r in enumerate(rows, 1) if r.get("plugin") == args.target]
        print(f"{args.target} 的执行位次（降序 = 执行顺序）= {pos}，共 {len(rows)} 个注册点")
        print(f"它是最后一个吗：{'是' if pos and pos[-1] == len(rows) else '否'}")
    else:
        print(f"未找到 {args.target} 的注册点")

    print()
    print("AstrBot 排序实现：", meta.get("sort_impl"))
    print("star_handler.py sha256：", meta.get("star_handler_sha256"))
    print("astrbot 版本：", meta.get("astrbot_version"))

    if args.json:
        payload = {"root": str(root), "rows": rows, "core": meta,
                   "coverage_boundary": [
                       "只扫 astrbot_plugin_*/main.py 的静态装饰器",
                       "不覆盖动态注册、别名导入、其它文件里的注册、内置 handler",
                   ]}
        Path(args.json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON 已写入 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
