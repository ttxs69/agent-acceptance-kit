#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实门注释版 ①：篇幅 / 标题 —— 从 article_checklist_gate.py 裁剪而来。

**这个门存在的起因**（原文件 docstring 原句）：
  一篇 3100 字、标题 42 字的稿子走完了当时的全部流程，没有任何环节说它不合格。
  因为「合格」只写在 skill 的散文清单里 —— 散文不会被执行，代码才会。

**裁剪说明（诚实标注，别当全门用）**：
  保留：按类别（kind）取不同阈值、标题显示宽度、正文篇幅。
  删掉：钩子/段落/CTA/模板化标题等本包不涉及的部分。
  原门还有 `--kind arxiv`（≥8000 字）和 HTML 输入支持，这里不展开。

**为什么必须有 kind**：
  最初用长文标准判日报（篇幅、加粗、结尾三项），4 项里 3 项是假失败。
  日报本来就是条目卡片结构，用长文阈值判它必然红。假失败的真正代价不是多报一次，
  而是**训练你忽略告警** —— 一个经常误报的门，第三次之后没人看它。

用法：
  python3 01-article-length-kind-gate.py --text draft.md --title "..." --kind article|promo|daily|xhs
  python3 01-article-length-kind-gate.py --selftest
退出码：0 通过 / 78 不合格 / 2 参数错误
"""
import argparse
import re
import sys
from pathlib import Path

# 阈值来源（原门注释）：外部 2026 实测 1200–1500 为长文最佳区间；
# promo（推广自家工具）来自 skill 的规格 2000–3000，下限放到 1500；
# xhs 是发布器硬限；daily（日报）**没有**篇幅判据 —— 它本来就不是长文。
KIND_LEN = {
    "article": (1200, 1500),
    "promo": (1500, 3000),
    "xhs": (700, 900),
    "daily": None,
}
TITLE_OK = (15, 28)
XHS_TITLE_MAX = 20


def zh_len(s: str) -> int:
    """显示宽度：汉字=1，拉丁字母/数字=0.5（"GitHub" 算 3 个字宽）。

    第一版直接用 len()，把 "GitHub" 当 6 个字，于是「33 天 GitHub Trending：
    AI Agent 只有 8 个赛道」被判 31 字超标，实际约 22 字 —— 判据比被测对象还离谱。
    """
    s = re.sub(r"\s+", "", s)
    w = 0.0
    for ch in s:
        w += 1.0 if ord(ch) > 0x2E80 else 0.5
    return int(w)


def check(text: str, title: str, kind: str) -> list[str]:
    bad = []
    if kind not in KIND_LEN:
        return [f"未知类别 {kind}（可选：{', '.join(KIND_LEN)}）"]

    # 标题：日报的标题在微信侧字段里，不在这份正文 ⇒ 对日报查标题只会得到「标题 0 字」的假失败
    if kind != "daily":
        tl = zh_len(title)
        limit = XHS_TITLE_MAX if kind == "xhs" else TITLE_OK[1]
        if not title.strip():
            bad.append("标题为空")
        elif tl > limit:
            bad.append(f"标题显示宽度 {tl} > {limit}（会被截断）")
        elif kind != "xhs" and tl < TITLE_OK[0]:
            bad.append(f"标题显示宽度 {tl} < {TITLE_OK[0]}（太短，打开率低）")

    span = KIND_LEN[kind]
    if span:
        n = len(re.sub(r"\s+", "", text))
        lo, hi = span
        if n < lo:
            bad.append(f"正文 {n} 字 < {lo}（{kind} 类下限）")
        elif n > hi:
            bad.append(f"正文 {n} 字 > {hi}（{kind} 类上限；超了要删，不是加豁免）")
    return bad


def selftest() -> int:
    # 字数按去空白后的字符数算（与 check() 同口径），别用「大概」
    long_text = "测" * 3100      # 原事故：3100 字
    mid_text = "测" * 1400       # article 区间内
    promo_text = "测" * 1690     # promo 区间内，但对 article 超上限
    T = "长度合规的标题示例文字内容"   # 显示宽度 13？下面用 zh_len 现算，不猜
    title_ok = T + "示例" if zh_len(T) < TITLE_OK[0] else T
    cases = [
        ("3100 字按 article 判 → 必须红（原门建门起因）",
         long_text, title_ok, "article", 78),
        ("同一篇按 daily 判 → 必须绿（日报没有篇幅判据，别造假日失败）",
         long_text, "", "daily", 0),
        ("1400 字按 article 判 → 绿", mid_text, title_ok, "article", 0),
        ("1690 字按 promo 判 → 绿", promo_text, title_ok, "promo", 0),
        ("同一篇按 article 判 → 红（类别不同，阈值不同）",
         promo_text, title_ok, "article", 78),
    ]
    ok = True
    for name, text, title, kind, expect in cases:
        bad = check(text, title, kind)
        rc = 78 if bad else 0
        good = rc == expect
        ok &= good
        print(f"  [{'PASS' if good else 'FAIL'}] rc={rc}（期望 {expect}）{name}")
        if not good:
            for b in bad:
                print(f"          {b}")
    print("✅ 自测通过" if ok else "⛔ 自测失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--title", default="")
    ap.add_argument("--kind", default="article")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.text:
        print("需要 --text（或 --selftest）", file=sys.stderr)
        return 2
    text = Path(a.text).read_text(encoding="utf-8")
    bad = check(text, a.title, a.kind)
    for b in bad:
        print(f"✗ {b}")
    if bad:
        print(f"\n⛔ {len(bad)} 项不合格（kind={a.kind}）")
        return 78
    print(f"✅ 篇幅/标题合格（kind={a.kind}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
