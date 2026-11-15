"""最小门：两个断言 —— calc() 返回 42、源码里没有 TODO。rc=0 过 / rc=1 不过。"""
import sys
from pathlib import Path

from calc import calc

bad = []
if calc() != 42:
    bad.append(f"calc() 返回 {calc()}，应为 42")
if "TODO" in Path(__file__).with_name("calc.py").read_text(encoding="utf-8"):
    bad.append("calc.py 里还有 TODO")

for b in bad:
    print(f"✗ {b}")
print(f"检查 2 项：返回值 42、无 TODO")
sys.exit(0 if not bad else 1)
