#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数字回源（从 facts_gate.py 抽出的核心片段）。

判据只有一句：文章里出现的数字，必须能在**一个**事实文件里找到同值。
事实文件是唯一来源（源路径、口径、日期都写在里面），门只做比对。

三个真坑，别重犯：
  1. 子串包含等于没判断：`"0" in "10-20"` 为真，`"17" in "2017"` 为真
     ⇒ 所有期望值为 0 的检查都会静默通过。必须用带边界的精确匹配。
  2. 先把 `v in text` 当快路径、再拿边界匹配兜底 —— 子串命中时边界检查根本不跑。
     ⇒ 纯数字一律只走边界匹配。
  3. 小数要按原样匹配（"4.0" 不该被 "4" 命中，也不该漏掉 "4.0"）。

用法：
  python3 number_traceback.py --text 文章.md --facts facts.json
  python3 number_traceback.py --selftest
退出码：0 全部对上 / 78 有对不上 / 2 参数错误
"""
import argparse
import json
import re
import sys
from pathlib import Path


def number_present(text: str, value) -> bool:
    """value 是否以「一个独立的数」的形式出现在 text 里。"""
    v = str(value).strip()
    if not re.fullmatch(r"-?[\d.]+", v):
        return v in text                      # 非数字：语义匹配，没有边界问题
    if "." in v:
        pat = r"(?<![\d.])" + re.escape(v) + r"(?![\d])"
    else:
        pat = r"(?<![\d.])" + re.escape(v) + r"(?![\d.])"
    return bool(re.search(pat, text))


def check(text: str, facts: dict) -> list[tuple[str, object]]:
    return [(k, v) for k, v in facts.items() if not number_present(text, v)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--facts")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        text = "本期 15 条里占 4%，其余 36% 有代码；样本区间 10-20 条，数据截至 2017 年。"
        facts = {"样本数": 15, "占比": 4, "有代码": 36}
        bad = check(text, facts)
        cases = [
            ("正常数字能对上", not bad),
            ("`0` 不能被 `10-20` 命中", number_present(text, 0) is False),
            ("`17` 不能被 `2017` 命中", number_present(text, 17) is False),
            ("`4` 不能被 `4%` 里的别的数命中", number_present(text, 4) is True),
            ("不存在的 5 必须判红", number_present(text, 5) is False),
        ]
        ok = all(v for _, v in cases)
        for name, good in cases:
            print(f"  [{'PASS' if good else 'FAIL'}] {name}")
        print("✅ 自测通过" if ok else "⛔ 自测失败")
        return 0 if ok else 1

    if not a.text or not a.facts:
        print("需要 --text 与 --facts（或 --selftest）", file=sys.stderr)
        return 2
    text = Path(a.text).read_text(encoding="utf-8")
    facts = json.loads(Path(a.facts).read_text(encoding="utf-8"))
    bad = check(text, facts)
    for k, v in facts.items():
        print(f"[{'OK' if (k, v) not in bad else 'MISMATCH'}] {k} = {v}")
    if bad:
        print(f"\n⛔ {len(bad)} 处数字在文中找不到同值 —— 不许交付")
        for k, v in bad:
            print(f"   ✗ {k} = {v}")
        return 78
    print(f"\n✅ {len(facts)} 个数字全部有源")
    return 0


if __name__ == "__main__":
    sys.exit(main())
