#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实门注释版 ③：标题断言可核验 —— 从 headline_gate.py 裁剪而来。

**起因**（真实事故 2026-10-29）：日报标题
    「Trinity 让多模态 Agent 递归自改，100 篇里排第一」
  用户批：「完全没有任何依据」。根因：正文第一篇 = 采集顺序，根本没有排序规则
  ⇒「排第一」是伪断言。

**方法论（本门最值钱的一条）**：
  「这个标题是不是在宣称排名」是语义问题。先用正则做，词表从「排第一」补到
  「第1篇」「打头」「挤进」，仍然被各种说法绕过 —— 正则做语义判定是**必然漏**的。
  ⇒ 做法反过来：**由生成标题的模型自己声明 claims**，门只做机械核验：
     声明的断言有没有对应依据（order_basis 在不在）、断言后面有没有增量信息。

**裁剪说明**：
  保留：T0（断言必须有依据）、T3（字节/显示宽度）、T4（断言后要有增量）、数字回源。
  删掉：T1/T2/T5/T6 与本包无关的选题/模板判据。
  本门**不猜语义**：没有 claims.rank 就不判排名。

用法：
  python3 03-headline-claim-gate.py --title "..." --claims claims.json \
      [--order-basis stars_today] [--numbers 100,42]
  python3 03-headline-claim-gate.py --selftest
退出码：0 通过 / 78 不许发布 / 2 参数错误
"""
import argparse
import json
import re
import sys

MAX_BYTES = 64      # 微信标题字节硬限
MAX_WIDTH = 28      # 移动端显示宽度
GOOD_MIN = 13


def title_bytes(t: str) -> int:
    return len(t.encode("utf-8"))


def title_width(t: str) -> float:
    return sum(1.0 if ord(c) > 0x2E80 else 0.5 for c in re.sub(r"\s", "", t))


def check(title: str, claims: dict, order_basis: str | None, numbers: list) -> list[str]:
    bad = []
    t = (title or "").strip()
    if not t:
        return ["标题为空"]

    nb, nw = title_bytes(t), title_width(t)
    if nb > MAX_BYTES:
        bad.append(f"T3 超 {MAX_BYTES} 字节（{nb} 字节）")
    if nw > MAX_WIDTH:
        bad.append(f"T3 显示宽度 {nw} 超 {MAX_WIDTH}（移动端截断）")
    elif nw < GOOD_MIN:
        bad.append(f"T3 显示宽度 {nw} 太短（最佳 {GOOD_MIN}-24）")

    # T0：排名断言必须声明依据；没有 order_basis ⇒ 判死（正文第一篇只是采集顺序）
    rank = (claims or {}).get("rank")
    if isinstance(rank, dict):
        what = str(rank.get("what") or "排名断言")
        if not order_basis:
            bad.append(f"T0 含排名断言「{what}」但无依据（当前源没有排序规则）⇒ 判死")
        # T4：断言之后要有增量（实测：85 阅读 vs 2 阅读，差 42 倍）
        pos = rank.get("pos")
        if isinstance(pos, int) and 0 <= pos < len(t):
            tail = re.sub(r"\s", "", t[pos + len(what):])
            if len(tail) < 4:
                bad.append("T4 排名断言后没有增量信息")

    # 数字回源：标题里的每个数字都要在当日数据里出现
    if numbers:
        raw = " ".join(str(x) for x in numbers).replace(",", "")
        ghost = [n for n in re.findall(r"\d[\d,\.]*", t)
                 if n.replace(",", "") not in raw]
        if ghost:
            bad.append(f"T2 数字 {ghost} 在数据里找不到（疑似编造）")
    return bad


def selftest() -> int:
    # 原事故标题一字不改：断言在句末，本身也过不了 T4 —— 这正是当时的现场
    incident = "Trinity 让多模态 Agent 递归自改，100 篇里排第一"
    claims = {"rank": {"what": "排第一", "pos": incident.index("排第一")}}
    # 正例：断言后带增量（，省3小时），数字都能回源
    good = "Codex 交活门实测：100 次里排第一，省 3 小时"
    good_claims = {"rank": {"what": "排第一", "pos": good.index("排第一")}}
    cases = [
        ("原事故标题（无排序依据）→ 必须红", incident, claims, None, [100], 78),
        ("补上依据后仍红：断言在句末，无增量（T4）", incident, claims, "stars_today", [100], 78),
        ("正例：有依据 + 有增量 + 数字有源 → 绿", good, good_claims, "stars_today", [100, 3], 0),
        ("数字 100 不在数据里 → 必须红", good, good_claims, "stars_today", [42], 78),
        ("断言后无增量 → 必须红", "Codex 排第一", {"rank": {"what": "排第一", "pos": 6}},
         "stars_today", [], 78),
    ]
    ok = True
    for name, title, cl, basis, nums, expect in cases:
        bad = check(title, cl, basis, nums)
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
    ap.add_argument("--title", default="")
    ap.add_argument("--claims", default="")
    ap.add_argument("--order-basis", default=None)
    ap.add_argument("--numbers", default="")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.title:
        print("需要 --title（或 --selftest）", file=sys.stderr)
        return 2
    claims = json.loads(open(a.claims, encoding="utf-8").read()) if a.claims else {}
    nums = [x for x in a.numbers.split(",") if x]
    bad = check(a.title, claims, a.order_basis, nums)
    for b in bad:
        print(f"✗ {b}")
    if bad:
        print(f"\n⛔ {len(bad)} 项不合格")
        return 78
    print("✅ 标题通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
