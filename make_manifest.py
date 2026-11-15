#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 MANIFEST.json：文件清单 + sha256 + 字节数 + 版本。

用法：python3 make_manifest.py [--check]
  --check  只比对现有 MANIFEST.json 与磁盘是否一致，不一致 rc=1（发布前跑一次）
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = "v1"
SKIP_DIRS = {"__pycache__", ".git"}
SKIP_FILES = {"MANIFEST.json", ".DS_Store"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect() -> list[dict]:
    files = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file() or p.name in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        rel = p.relative_to(ROOT).as_posix()
        files.append({"path": rel, "bytes": p.stat().st_size, "sha256": sha256(p)})
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    files = collect()
    manifest = {
        "name": "agent-acceptance-kit",
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "file_count": len(files),
        "total_bytes": sum(f["bytes"] for f in files),
        "hash": "sha256",
        "files": files,
    }
    out = ROOT / "MANIFEST.json"

    if a.check:
        if not out.exists():
            print("MANIFEST.json 不存在", file=sys.stderr)
            return 1
        old = json.loads(out.read_text(encoding="utf-8"))
        old_map = {f["path"]: f["sha256"] for f in old.get("files", [])}
        new_map = {f["path"]: f["sha256"] for f in files}
        diff = [p for p in sorted(set(old_map) | set(new_map)) if old_map.get(p) != new_map.get(p)]
        if diff:
            print("⛔ 与 MANIFEST 不一致：")
            for d in diff:
                print(f"   {d}: {old_map.get(d, '(缺)')[:12]} → {new_map.get(d, '(删)')[:12]}")
            return 1
        print(f"✅ 一致：{len(files)} 个文件")
        return 0

    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"写入 {out}：{len(files)} 个文件，{manifest['total_bytes']} 字节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
