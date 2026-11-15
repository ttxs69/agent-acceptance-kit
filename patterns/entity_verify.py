#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实体核验（从 facts_gate.py 的 slug 校验抽出的片段，含那次假失败的修法）。

判据：文中提到的每个 `owner/repo` 必须在源榜单里真的出现过 —— 防止编一个
看起来很像的仓库名。

真事故（必须写进注释，否则下一个人会再踩）：
  第一版把 `tools/facts_gate.py` 这类**本地文件路径**也当成仓库名，报了一堆假失败。
  修法是给门加类别（`--kind promo` 跳过实体校验），**不是**改正文去迁就门。
  这两件事反了，门就变成装饰：正文被改得越来越像门喜欢的样子，缺陷还在。

即使同为 article 类，也要先按形状排掉本地路径 —— 它们不是「不存在的仓库」，
而是「不是仓库」。假失败比漏检更快杀死一个门：第三次误报之后没人再看它。

用法：
  python3 entity_verify.py --text 文章.md --entities entities.json [--kind article|promo]
  python3 entity_verify.py --selftest
退出码：0 全部有源 / 78 有查不到的实体 / 2 参数错误
"""
import argparse
import json
import re
import sys
from pathlib import Path

FILE_EXT = (".py", ".md", ".json", ".js", ".ts", ".sh", ".txt", ".yaml", ".yml", ".toml")
LOCAL_HEADS = {"tools", "src", "api", "web", "scripts", "docs", "tests", "examples", "out"}


def looks_local(s: str) -> bool:
    """`./x/y`、`/tmp/a/b`、`tools/facts_gate.py` 这类是路径，不是仓库名。"""
    if s.startswith(("./", "../", "/", "~")):
        return True
    parts = s.split("/")
    if len(parts) != 2:
        return True
    if parts[1].lower().endswith(FILE_EXT):
        return True
    return parts[0].lower() in LOCAL_HEADS


def extract(text: str) -> set:
    cands = set(re.findall(r"`([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)`", text))
    return {c for c in cands if not looks_local(c)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--entities")
    ap.add_argument("--kind", default="article")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        text = ("榜单里的 `openai/codex` 涨了；本地文件 `tools/facts_gate.py` 和 "
                "`agent/continue_hook.py` 不是仓库；`acme/not-in-list` 是编的。")
        got = extract(text)
        cases = [
            ("保留真仓库", "openai/codex" in got),
            ("排掉 tools/ 下的本地文件", "tools/facts_gate.py" not in got),
            ("排掉 agent/ 下的本地文件", "agent/continue_hook.py" not in got),
            ("保留编造的仓库名（交给白名单判）", "acme/not-in-list" in got),
        ]
        ok = all(v for _, v in cases)
        for n, v in cases:
            print(f"  [{'PASS' if v else 'FAIL'}] {n}")
        print("✅ 自测通过" if ok else "⛔ 自测失败")
        return 0 if ok else 1

    if not a.text or not a.entities:
        print("需要 --text 与 --entities（或 --selftest）", file=sys.stderr)
        return 2
    text = Path(a.text).read_text(encoding="utf-8")
    allowed = set(json.loads(Path(a.entities).read_text(encoding="utf-8")).get("repos", []))
    if a.kind == "promo":
        print("kind=promo ⇒ 跳过实体核验（推广文里的斜杠串是本地路径，不是榜单仓库）")
        return 0
    got = extract(text)
    bad = sorted(got - allowed)
    for e in sorted(got):
        print(f"[{'OK' if e in allowed else 'MISMATCH'}] {e}")
    if bad:
        print(f"\n⛔ {len(bad)} 个实体在源数据里查不到：{', '.join(bad)}")
        return 78
    print(f"\n✅ {len(got)} 个实体全部有源")
    return 0


if __name__ == "__main__":
    sys.exit(main())
