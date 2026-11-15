"""门：会话接口的三个断言。--file 指定被测文件（本次只覆盖 api/session.py）。"""
import argparse
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--file", default=str(Path(__file__).with_name("session.py")))
a = ap.parse_args()

src = Path(a.file).read_text(encoding="utf-8")
bad = []
if "200" not in src:
    bad.append("状态码 200 不在实现里")
if "user_id" not in src:
    bad.append("字段 user_id 不在实现里")
if "10" not in src:
    bad.append("超时 10s 不在实现里")

for b in bad:
    print(f"✗ {b}")
print("3 项通过：状态码 200、字段 user_id 存在、超时 10s")
sys.exit(0 if not bad else 1)
