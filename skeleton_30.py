#!/usr/bin/env python3
"""30 行骨架：一条判据 —— 说「完成」就必须有一条带返回码的命令。

这是文章里承诺的「三十行骨架」，故意只做一件事。要三组判据、按节核验、
改动清单比对，用同目录的 check.py（它把这个骨架扩成了可用的检查器）。

用法：python3 skeleton_30.py <handoff.md>     rc=0 有证据 / rc=1 只有形容词
"""
import re
import sys

CLAIM = ("完成", "做完", "已修", "跑通", "通过", "没问题", "搞定", "done", "fixed")
RC = re.compile(r"\brc\s*[=:]\s*(-?\d+)", re.I)


def main(path: str) -> int:
    text = open(path, encoding="utf-8").read()
    claims = [l.strip() for l in text.splitlines()
              if any(w in l.lower() for w in CLAIM) and not l.strip().startswith("#")]
    rcs = RC.findall(text)
    if claims and not rcs:
        print(f"拒收：{len(claims)} 处完成断言，0 个返回码")
        for c in claims[:3]:
            print(f"  - {c}")
        return 1
    print(f"放行：{len(claims)} 处断言，{len(rcs)} 个返回码（仅这一条判据）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
