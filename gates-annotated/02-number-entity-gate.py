#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实门注释版 ②：数字/实体核验 —— 从 facts_gate.py 裁剪而来。

**这个门存在的起因**（原文件 docstring）：
  2026-10-22 我写文章时编了 3 个数字：「23 条 6%」（真值 15 条 4%）、
  「有代码 18%」（真值 17.3%）、「其余 32%」（真值 36%）。
  单独看都合理，合起来全错 —— 它们不是撒谎，只是从记忆里取的，没有回源。

**结构（这是它值得抄的地方）**：
  先让数字只存在于一个 facts.json 里（每个值都写源路径、口径、日期），
  门只做一件事：比对文中的数和文件里的数。数字的唯一来源 = 可复算。

**裁剪说明**：
  保留：边界精确匹配、facts 文件比对、实体（owner/repo）校验、kind 豁免。
  删掉：arxiv/GitHub 各算子的取数逻辑（那部分依赖作者自己的原始数据）。
  这个文件**不复制**上面两项判据 —— 它 import patterns/ 下的真身，
  因为「同一个判据抄两份，改一处另两处还在旧口径」正是原门踩过的坑。

用法：
  python3 02-number-entity-gate.py --text draft.md --facts facts.json \
      [--entities entities.json] [--kind article|promo]
  python3 02-number-entity-gate.py --selftest
退出码：0 全对 / 78 有对不上 / 2 参数错误
"""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # 别在买家的目录里留 __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "patterns"))
from entity_verify import extract, looks_local  # noqa: E402
from number_traceback import check as check_numbers  # noqa: E402


def selftest() -> int:
    text = "本期 15 条里占 4%，其余 36% 有代码；区间 10-20 条，数据截至 2017 年。"
    facts = {"样本数": 15, "占比": 4, "有代码": 36}
    bad = check_numbers(text, facts)
    cases = [
        ("三个真数字全部对上", bad == []),
        ("`0` 不被 `10-20` 命中", check_numbers(text, {"x": 0}) != []),
        ("`17` 不被 `2017` 命中", check_numbers(text, {"x": 17}) != []),
        ("编的 `5` 被判红", check_numbers(text, {"x": 5}) != []),
        ("本地路径不被当成仓库", looks_local("tools/facts_gate.py")),
        ("真仓库名保留下来", "openai/codex" in extract("`openai/codex` 和 `tools/x.py`")),
    ]
    ok = all(v for _, v in cases)
    for n, v in cases:
        print(f"  [{'PASS' if v else 'FAIL'}] {n}")
    print("✅ 自测通过" if ok else "⛔ 自测失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--facts")
    ap.add_argument("--entities")
    ap.add_argument("--kind", default="article")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.text or not a.facts:
        print("需要 --text 与 --facts（或 --selftest）", file=sys.stderr)
        return 2

    text = Path(a.text).read_text(encoding="utf-8")
    facts = json.loads(Path(a.facts).read_text(encoding="utf-8"))
    failed = 0

    for k, v in check_numbers(text, facts):
        print(f"[MISMATCH] {k} = {v}")
        failed += 1

    if a.entities and a.kind != "promo":
        allowed = set(json.loads(Path(a.entities).read_text(encoding="utf-8")).get("repos", []))
        for e in sorted(extract(text) - allowed):
            print(f"[MISMATCH] 实体 {e} 不在源数据里")
            failed += 1

    if failed:
        print(f"\n⛔ {failed} 处对不上 —— 不许交付")
        return 78
    print(f"✅ {len(facts)} 个数字全部有源（kind={a.kind}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
