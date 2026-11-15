#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""负对照跑法：写完门的第一件事不是拿正确样本去跑，而是**故意改坏一位，看它红不红**。

它回答的问题是「这个门到底在看什么」。没跑过负对照的门，可能一直是绿的，
也可能一直是红的 —— 两种都等于没有。

用法（{sample} 会被替换成样本路径）：
  python3 negative_control.py \
      --gate "python3 02-number-source-gate.py --text {sample} --facts facts.json" \
      --sample good.md --mutate "4=5"

退出码：0 = 好样本绿、改坏样本红（门是活的）；1 = 门没反应或好样本本来就红
"""
import argparse
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


def run_gate(template: str, sample: Path) -> tuple[int, str]:
    cmd = template.replace("{sample}", str(sample))
    p = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=120)
    return p.returncode, (p.stdout + p.stderr).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", required=True, help="门命令，用 {sample} 占位")
    ap.add_argument("--sample", required=True, help="已知正确的样本")
    ap.add_argument("--mutate", action="append", default=[],
                    help="改坏方式 old=new，可多次给（每次都单独测）")
    a = ap.parse_args()

    good = Path(a.sample)
    if not good.exists():
        print(f"样本不存在：{good}", file=sys.stderr)
        return 2
    text = good.read_text(encoding="utf-8")

    rc0, out0 = run_gate(a.gate, good)
    print(f"好样本：rc={rc0}（期望 0）")
    if rc0 != 0:
        print(out0)
        print("⛔ 好样本本来就是红的 —— 先修门，再谈它能不能拦住坏的")
        return 1

    ok = True
    for spec in a.mutate or ["__noop__"]:
        if spec == "__noop__":
            print("没给 --mutate，只验证了好样本是绿的；这样不够。")
            ok = False
            break
        old, _, new = spec.partition("=")
        if old not in text:
            print(f"⚠ 改坏串 {old!r} 不在样本里，跳过（这不算负对照）")
            ok = False
            continue
        with tempfile.TemporaryDirectory(prefix="negctl-") as d:
            bad = Path(d) / good.name
            bad.write_text(text.replace(old, new), encoding="utf-8")
            rc1, out1 = run_gate(a.gate, bad)
        hit = rc1 != 0
        ok &= hit
        print(f"改坏 {old!r} → {new!r}：rc={rc1}（期望非 0）  [{'PASS' if hit else 'FAIL'}]")
        if not hit:
            print(out1)

    print("✅ 门是活的：好样本绿、改坏样本红" if ok else "⛔ 门没被证明活着")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
