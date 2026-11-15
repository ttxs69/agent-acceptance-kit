#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check.py —— Agent 交活验收包 v1 的核心检查器（纯标准库，单文件）

输入：一份 agent 的「交活说明」（markdown / 纯文本），可选一个仓库目录。
输出：rc=0 放行 / rc=1 拒收 / rc=2 用法或输入错误，外加人话结论。

它只做三件事（都来自作者项目里跑过的真门，不是想象出来的判据）：

  C1 宣称完成，但没有可复现的命令/证据
     来源：article_checklist_gate.py 的建门起因 —— 一篇 3100 字、标题 42 字的稿子
     走完全流程，没有任何环节判它不合格，因为「合格」只写在散文里。
     这里是同一件事的验收版：断言必须落成一条能粘进终端的命令，且带返回码。

  C2 改了文件，但没跑门（或门没覆盖到改动的文件）
     来源：两处真事故 —— ① 双副本脚本里修复只落在被 cron 执行的那一份，
     仓库那份落后 6 行（「修了没生效」）；② 三个 cron 脚本失败时 return 0，
     面板恒绿。共同点：门的绿色与改动无关。
     这里的判据：门要么是全量（`pytest` / `make test` 这种无对象参数），
     要么它的对象参数必须覆盖改动清单里的文件。

  C3 把「准备」当「完成」
     来源：m2_gate.py 的占位符检查（TODO/待填/{{ }}），以及一次
     `fetch_inbox()` 读不到配置时 `return []`，把「没读到信」下传成
     「今天没订单」，rc=0。骨架、stub、干跑、待确认都属于这一类。

明确不做（README 里也写了）：
  · 不判断代码质量、不判断断言内容是否真实 —— 那需要人读 diff。
  · 不解析语义。它只判「证据结构在不在」，判断不了「这个证据是否诚实」。
  · 默认不执行交活说明里的命令（那是不可信文本）。加 --run 才执行，且只执行白名单前缀。

用法：
  python3 check.py <handoff.md> [--repo DIR] [--changed PATH ...] [--json] [--run]
  python3 check.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

VERSION = "v1"

# ── 词表：只做「提取」，不做语义判定。判不了的进 HUMAN，不硬判。──────────────
# 完成断言：这些词出现，说明作者在声称某件事已经发生。
CLAIM_WORDS = (
    "完成", "做完", "做好", "搞定", "已修", "修好", "已实现", "实现好", "跑通", "跑过",
    "通过", "全绿", "没问题", "可用", "上线", "交付", "ready", "done", "fixed",
    "completed", "implemented", "works", "passing", "all green", "shipped",
)
# 否定/未完成：同一行里出现这些，就不算完成断言（否则「没做完」会被判成「做完了」）。
NEG_WORDS = (
    "未完成", "没完成", "没做完", "尚未", "还没", "待完成", "没跑", "未跑", "不能", "不可",
    "无法", "not done", "unfinished", "not yet", "todo",
)
# 准备态：声称完成但其实是准备/骨架/干跑。C3 抓的就是这些。
PREP_WORDS = (
    "准备", "待确认", "待你", "等待", "计划", "稍后", "下一步", "骨架", "脚手架", "占位",
    "stub", "placeholder", "示例数据", "干跑", "dry-run", "dry run", "草稿", "样张",
    "pending", "will ", "plan to", "about to", "scaffold",
)
# 门：命令名里带这些词，才算「门」，不是随便一条 echo。
GATE_RE = re.compile(r"(gate|check|test|lint|verify|audit|selftest|自检|门)", re.I)
# 返回码的写法：rc=0 / exit code: 0 / 退出码 0 / [exit 0] / returncode=0
RC_PAT = re.compile(
    r"(?:\brc\s*[=:]\s*|\breturncode\s*[=:]\s*|\bexit(?:\s*code)?\s*[=:]\s*"
    r"|退出码\s*[:：]?\s*|\[exit\s+)(-?\d+)", re.I)
# 输出里出现这些，而 rc 却记成 0 ⇒ 证据自相矛盾（真事故：失败被壳吞成 0）。
FAIL_WORDS = re.compile(
    r"(\bFAIL(?:ED|URE)?\b|\bfailed\b|Traceback|❌|⛔|✗|\bERROR\b|error:|未通过|失败|异常)", re.I)
# 只读信息、不承载证据的节：允许有概括性断言（否则会逼出重复贴命令的假失败）。
INFO_SECTIONS = re.compile(
    r"(结论|总结|概述|摘要|概要|说明|改动|变更|风险|局限|备注|未做|不做|背景|"
    r"overview|summary|tldr|changelog|changed|risks?)", re.I)
CMD_PREFIX = {
    "python", "python3", "pytest", "npm", "pnpm", "yarn", "node", "make", "git",
    "bash", "sh", "uv", "uvx", "cargo", "go", "deno", "bun", "docker", "php", "ruby",
}
PATH_EXT = (".py", ".md", ".json", ".js", ".ts", ".tsx", ".sh", ".csv", ".yaml", ".yml",
            ".txt", ".toml", ".rs", ".go")


@dataclass
class Cmd:
    text: str
    line: int
    section: str | None = None
    output: str = ""
    rc: int | None = None
    fenced: bool = False


@dataclass
class Claim:
    line: int
    text: str
    section: str | None = None


@dataclass
class Finding:
    code: str          # C1 / C2 / C3
    level: str         # FAIL / WARN / HUMAN
    line: int
    msg: str
    fix: str


@dataclass
class Result:
    rc: int
    findings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


# ── 解析 ────────────────────────────────────────────────────────────────────
def _looks_like_cmd(s: str) -> bool:
    s = s.strip().strip("`").strip()
    if not s or len(s) > 400:
        return False
    if s.startswith("./") or s.startswith("../"):
        return True
    first = s.split()[0]
    return first in CMD_PREFIX


def _is_claim(line: str) -> bool:
    low = line.lower()
    if any(n in low for n in NEG_WORDS):
        return False
    return any(w in low for w in CLAIM_WORDS)


def parse_handoff(text: str):
    """返回 (cmds, claims)。宽松解析：围栏里的命令、$ 开头的命令、行内反引号命令都收。"""
    lines = text.splitlines()
    cmds: list[Cmd] = []
    claims: list[Claim] = []
    section: str | None = None
    in_fence = False

    for i, raw in enumerate(lines):
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue

        m = re.match(r"^#{1,6}\s+(.+)$", line)
        if m and not in_fence:
            section = m.group(1).strip().strip("#").strip()
            continue

        if not in_fence and stripped and not stripped.startswith("|"):
            if _is_claim(stripped):
                claims.append(Claim(i + 1, stripped, section))

        cmd_text = None
        if in_fence:
            if stripped.startswith("$ "):
                cmd_text = stripped[2:].strip()
            elif stripped.startswith("> "):
                cmd_text = stripped[2:].strip()
            elif _looks_like_cmd(stripped):
                cmd_text = stripped
        else:
            if stripped.startswith("$ "):
                cmd_text = stripped[2:].strip()
            else:
                # 行内 `python3 x.py`：算「有命令」，但通常没有返回码 ⇒ C1 会点名
                for span in re.findall(r"`([^`\n]+)`", line):
                    if _looks_like_cmd(span):
                        cmds.append(Cmd(span.strip(), i + 1, section, "", None, False))
        if cmd_text:
            cmds.append(Cmd(cmd_text, i + 1, section, "", None, in_fence))

    # 把命令后面的输出块贴回命令，并从块里找返回码
    cmd_lines = {c.line for c in cmds}
    for c in cmds:
        if not c.fenced:
            continue
        out = []
        idx = c.line  # 0-based 的下一行
        while idx < len(lines) and idx < c.line + 15:
            s = lines[idx].rstrip()
            if s.strip().startswith("```") or re.match(r"^#{1,6}\s", s):
                break
            if idx + 1 in cmd_lines:
                break
            out.append(s)
            idx += 1
        c.output = "\n".join(out).strip()
        m = RC_PAT.search(c.output) or RC_PAT.search(c.text)
        if m:
            c.rc = int(m.group(1))

    # 去重（同一行同一命令只留一次），保住顺序
    seen, uniq = set(), []
    for c in cmds:
        key = (c.line, c.text)
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq, claims


def _split_cmd(cmd: str) -> list[str]:
    try:
        return shlex.split(cmd, posix=True)
    except ValueError:
        return cmd.split()


def path_args(cmd: str) -> list[str]:
    """命令里所有像文件路径的参数（脚本 + 被测对象），用于「文件是否存在」检查。

    只看形状（扩展名），不看语义。`--file app.py` 的 app.py 也算：宁可多查一个路径，
    也不要把它跳过去 —— 那样「命令指向不存在的文件」就漏了。
    """
    out = []
    for t in _split_cmd(cmd)[1:]:
        if t.startswith("-") or (t.startswith("--") and "=" in t):
            continue
        if t.lower().endswith(PATH_EXT):
            out.append(t)
    return out


def target_args(cmd: str) -> list[str]:
    """门的「被测对象」参数。脚本自身不算对象：`python3 gate.py` 是全量门，不是只测 gate.py。

    分界：解释器后面第一个非 flag 参数是程序本身，要跳过；`pytest tests/` 没有程序，
    第一个路径就是对象。不做这一步，全量门会被判成「只覆盖了门自己」—— 假失败。
    """
    toks = _split_cmd(cmd)
    if not toks:
        return []
    rest = toks[1:]
    if toks[0] in {"python", "python3", "uv", "uvx", "node", "bash", "sh", "ruby", "php",
                   "deno", "bun"}:
        for i, t in enumerate(rest):
            if t.startswith("-"):
                continue
            rest = rest[i + 1:]
            break
    return [t for t in rest
            if not t.startswith("-") and not (t.startswith("--") and "=" in t)
            and t.lower().endswith(PATH_EXT)]


def is_gate(cmd: str) -> bool:
    return bool(GATE_RE.search(cmd))


def program_of(cmd: str) -> str | None:
    """门命令里被执行的那个脚本（跳过解释器与 flag）。它被真执行了，不是「被测对象」。"""
    toks = _split_cmd(cmd)
    if not toks:
        return None
    if toks[0] in CMD_PREFIX:
        toks = toks[1:]
    for t in toks:
        if t.startswith("-"):
            continue
        return t if t.lower().endswith(PATH_EXT) else None
    return None


# ── 改动清单 ────────────────────────────────────────────────────────────────
def changed_from_git(repo: Path) -> list[str]:
    try:
        p = subprocess.run(["git", "-C", str(repo), "status", "--porcelain",
                            "--untracked-files=all"],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    if p.returncode != 0:
        return []
    out = []
    for line in p.stdout.splitlines():
        if len(line) < 4:
            continue
        rest = line[3:].strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        rest = rest.strip('"')
        out.append(rest)
    return sorted(set(out))


def changed_from_text(text: str) -> list[str]:
    """从「改动 / 变更」节里取反引号路径。没有 git 时的兜底。"""
    out = []
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"^#{1,6}\s+(.+)$", line)
        if m:
            section = m.group(1)
            continue
        if section and re.search(r"(改动|变更|修改|changed|files? changed)", section, re.I):
            for span in re.findall(r"`([^`\n]+)`", line):
                s = span.strip()
                if "/" in s or s.lower().endswith(PATH_EXT):
                    out.append(s)
    return sorted(set(out))


def _norm(p: str) -> str:
    return os.path.normpath(p.replace("\\", "/")).lstrip("./")


def drop_handoff(changed: list[str], handoff: Path, repo: Path) -> list[str]:
    """交活说明本身不算「改动」。

    它几乎总是出现在 `git status` 里（agent 刚写的新文件），而且没有任何门会去测它 ——
    算进改动清单，带对象参数的门就会永远报「没有覆盖 handoff.md」，把真结果淹掉。
    """
    try:
        hp = handoff.resolve()
    except OSError:
        return changed
    out = []
    for c in changed:
        try:
            if (repo / c).resolve() == hp:
                continue
        except OSError:
            pass
        out.append(c)
    return out


def pick_changed(explicit: list[str], repo: Path | None, text: str, handoff: Path,
                 collector=changed_from_git) -> list[str]:
    """改动清单用哪一份：显式给的 > git 的 > 说明里「改动」节的。

    git 那一份要先把交活说明本身剔掉 —— 它是 agent 刚写的新文件，永远出现在 status 里，
    没有任何门会去测它；算进去，带对象参数的门就会恒红。
    """
    if explicit:
        return list(explicit)
    if repo is not None:
        got = collector(repo)
        if got:
            return drop_handoff(got, handoff, repo)
    return changed_from_text(text)


def _covers(gate_cmd: str, changed: list[str]) -> set[str]:
    """这个门覆盖了哪些改动文件。无对象参数 = 全量门，覆盖全部。"""
    args = target_args(gate_cmd)
    if not args:
        return set(changed)
    hit = set()
    for g in args:
        g = _norm(g)
        for c in changed:
            cn = _norm(c)
            if cn == g or cn.endswith("/" + g) or g.endswith("/" + cn):
                hit.add(c)
    return hit


# ── 判定 ────────────────────────────────────────────────────────────────────
def _clip(s: str, n: int = 46) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _section_line(text: str, pat: str) -> int:
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^#{1,6}\s+(.+)$", line)
        if m and re.search(pat, m.group(1), re.I):
            return i
    return 1


def judge(text: str, changed: list[str], base: Path) -> Result:
    cmds, claims = parse_handoff(text)
    findings: list[Finding] = []
    notes: list[str] = []
    with_rc = [c for c in cmds if c.rc is not None]
    gates = [c for c in with_rc if is_gate(c.text)]

    def add(code, level, line, msg, fix):
        if not any(f.code == code and f.line == line and f.msg == msg for f in findings):
            findings.append(Finding(code, level, line, msg, fix))

    # ── C1：断言 vs 可复现命令 ──
    if claims and not cmds:
        add("C1", "FAIL", claims[0].line,
            f"{len(claims)} 处完成断言，0 条可复现命令。第一处：「{_clip(claims[0].text)}」",
            "每条断言后面放一条命令：把 `python3 xxx.py` 粘进终端能跑，并贴 rc=0。")
    elif claims and not with_rc:
        add("C1", "FAIL", cmds[0].line,
            f"有 {len(cmds)} 条命令，但 0 条记录了返回码 —— 跑没跑过、过没过都无法判定。",
            "命令下方贴一行 `rc=0`（或 `exit code: 0`）。没有返回码的「跑过了」等于没说。")

    # 按节判：非信息节里的断言必须在本节内有带 rc 的命令
    if with_rc:
        for cl in claims:
            if cl.section is None or INFO_SECTIONS.search(cl.section):
                continue
            if any(w in cl.text.lower() for w in PREP_WORDS):
                continue  # 准备态由 C3 报，避免同一条断言被两个判据重复点名
            if not any(c.section == cl.section for c in with_rc):
                add("C1", "FAIL", cl.line,
                    f"「{cl.section}」节写「{_clip(cl.text)}」，但这一节没有任何带返回码的命令。",
                    "把结论落成命令放进同一节；只写结论不写命令，人只能通读 diff。")

    # 命令指向不存在的文件 ⇒ 不可复现（m2_gate 第 4 条：引用不存在的数据路径）
    for c in with_rc:
        for a in path_args(c.text):
            if a.startswith("/") or "://" in a:
                continue
            if not (base / a).exists() and not (base / _norm(a)).exists():
                add("C1", "FAIL", c.line,
                    f"命令里的 `{a}` 在交付目录里不存在，这条命令无法复现。",
                    "改成真实存在的路径，或把文件一起交付。")
                break

    # ── C2：改动的文件 vs 跑过的门 ──
    if changed:
        if not gates:
            add("C2", "FAIL", _section_line(text, r"(改动|变更|修改|changed)"),
                f"改动清单有 {len(changed)} 个文件（{_clip(', '.join(changed[:3]))}），"
                f"但没有任何门的执行记录。",
                "先跑一条门（`python3 xxx_gate.py` 或 `pytest`），再贴 rc；没跑门就不是完成。")
        else:
            if not any(g.rc == 0 for g in gates):
                add("C2", "FAIL", gates[0].line,
                    f"{len(gates)} 条门全部是红的（rc={gates[0].rc}），却按完成交活。",
                    "门红就是没完成。修到 rc=0，或把失败写进「未做」。")
            covered = set()
            for g in gates:
                covered |= _covers(g.text, changed)
            # 门脚本自身不算「没覆盖」：它被真执行了（README §8.2：本包不判门本身有没有用）。
            progs = {_norm(p) for p in (program_of(g.text) for g in gates) if p}
            uncovered = [c for c in changed if c not in covered and _norm(c) not in progs]
            if uncovered:
                add("C2", "FAIL", gates[0].line,
                    f"门没有覆盖 {len(uncovered)} 个改动文件：{_clip(', '.join(uncovered[:4]))}"
                    f"（门：`{_clip(gates[0].text, 50)}`）。",
                    "把改动文件加进门的参数，或改跑全量门（无对象参数的 `pytest`）。")
            for g in gates:
                if g.rc == 0 and FAIL_WORDS.search(g.output or ""):
                    what = FAIL_WORDS.search(g.output).group(0)
                    add("C2", "FAIL", g.line,
                        f"证据自相矛盾：rc 记成 0，但输出里有「{what}」（失败被吞成 0 的典型形态）。",
                        "以输出为准重跑；rc 必须是程序真的返回的值，不是手写的。")
                    break
    else:
        notes.append("没有改动清单（未给 --repo，说明里也没有「改动」节）⇒ C2 只能判「有没有门」，"
                     "判不了「门覆没覆盖改动」。需要人工确认。")

    # ── C3：准备当完成 ──
    for cl in claims:
        hit = next((w for w in PREP_WORDS if w in cl.text.lower()), None)
        if hit:
            add("C3", "FAIL", cl.line,
                f"把准备当完成：「{_clip(cl.text)}」里有「{hit.strip()}」。",
                "改成「已准备，未执行」并把这条从「完成」移到「未做」；准备不是完成。")

    gate_claim = [cl for cl in claims if GATE_RE.search(cl.text)]
    if gate_claim and not gates:
        add("C3", "FAIL", gate_claim[0].line,
            f"宣称有门/跑过检查（「{_clip(gate_claim[0].text)}」），但全文没有一次门的执行记录。",
            "要么真的跑一遍贴 rc，要么删掉这句 —— 写了不跑的门只是装饰。")

    if not claims:
        notes.append("没有识别到完成断言。本包只做否定判断：它能拦「说了没证据」，"
                     "拦不了「没说但也没做」。")

    fails = [f for f in findings if f.level == "FAIL"]
    rc = 1 if fails else 0
    stats = {
        "claims": len(claims),
        "commands": len(cmds),
        "commands_with_rc": len(with_rc),
        "gates": len(gates),
        "changed": len(changed),
        "fails": len(fails),
        "warns": len([f for f in findings if f.level == "WARN"]),
    }
    return Result(rc, findings, stats, notes)


# ── 输出 ────────────────────────────────────────────────────────────────────
def render(res: Result, src: str) -> str:
    out = []
    verdict = "放行" if res.rc == 0 else "拒收"
    out.append(f"交活验收：{verdict}  (rc={res.rc})   源：{src}   包：{VERSION}")
    st = res.stats
    out.append(f"读到的结构：{st['claims']} 条完成断言 / {st['commands']} 条命令"
               f"（{st['commands_with_rc']} 条带返回码）/ {st['gates']} 个门 / "
               f"{st['changed']} 个改动文件")
    out.append("")
    if res.findings:
        out.append("依据：")
        for f in res.findings:
            out.append(f"  [{f.level} {f.code}] 第 {f.line} 行  {f.msg}")
            out.append(f"          怎么改：{f.fix}")
    else:
        out.append("依据：三组判据都没有命中。")
    if res.notes:
        out.append("")
        out.append("需人工判断：")
        for n in res.notes:
            out.append(f"  [? HUMAN] {n}")
    out.append("")
    out.append("说明：本检查只判「证据结构」，不判内容真假，也不替你看代码质量。")
    out.append("      断言是否属实、diff 是否有私货，仍需人读 —— 它省的是「通读 diff 找有没有证据」这一步。")
    return "\n".join(out)


# ── --run：可选复跑（默认关闭）──────────────────────────────────────────────
RUN_ALLOW = {"python", "python3", "pytest", "uv", "uvx"}  # 2026-11-15 红队: bash/sh/npm/node/make 可执行任意代码，已移除（白名单≠沙箱）
RUN_BLOCK = (";", "&&", "||", "|", ">", "<", "`", "$(", "curl", "wget", " rm ", "sudo",
             "ssh", "scp", "git push", "chmod", "kill")


def rerun(cmds: list[Cmd], cwd: Path, res: Result, timeout: int = 120):
    for c in cmds:
        if c.rc is None:
            continue
        toks = _split_cmd(c.text)
        if not toks or toks[0] not in RUN_ALLOW or any(b in c.text for b in RUN_BLOCK):
            res.findings.append(Finding("C1", "HUMAN", c.line,
                                        f"未复跑（不在白名单）：`{_clip(c.text, 60)}`",
                                        "手工跑一次，确认返回码不是手写的。"))
            continue
        try:
            p = subprocess.run(toks, cwd=str(cwd), capture_output=True, text=True,
                               timeout=timeout,
                               env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        except Exception as e:  # noqa: BLE001 - 交活检查不该因为复跑失败而崩
            res.findings.append(Finding("C1", "HUMAN", c.line,
                                        f"复跑失败（{type(e).__name__}）：`{_clip(c.text, 60)}`",
                                        "检查解释器/依赖；这一条需要人工确认。"))
            continue
        actual = p.returncode
        print(f"[复跑] `{_clip(c.text, 50)}` → rc={actual}（记录 {c.rc}）"
              f"{' ✓' if actual == c.rc else ' ✗'}", file=sys.stderr)
        if actual != c.rc:
            missing = ("No module named" in (p.stderr or "")
                       or "command not found" in (p.stderr or "")
                       or "not recognized" in (p.stderr or ""))
            if missing and c.rc == 0:
                first = (p.stderr or "").strip().splitlines()[-1][:80] if p.stderr else ""
                res.findings.append(Finding(
                    "C1", "HUMAN", c.line,
                    f"复跑环境缺依赖，不能判真伪：`{_clip(c.text, 50)}`（{first}）",
                    "装上依赖再复跑；这一条需要人工确认，不算它造假。"))
                continue
            res.findings.append(Finding(
                "C1", "FAIL", c.line,
                f"复跑不一致：记录 rc={c.rc}，实际 rc={actual}。`{_clip(c.text, 60)}`",
                "返回码必须是真跑出来的。把实际输出贴上来，不要手写 rc。"))
    res.rc = 1 if any(f.level == "FAIL" for f in res.findings) else 0


# ── 自测 ────────────────────────────────────────────────────────────────────
PASS_FIXTURE = """# 交活说明：修 calc.py 的取整

## 结论

已完成取整修复，自检通过。

## 改动

- `demo/calc.py`

## 证据

```
$ python3 demo/gate_calc.py
检查 2 项：返回值 42、无 TODO
rc=0
```
"""


def _fixtures():
    return [
        # (名字, 文本, 改动清单, 期望 rc, 期望至少包含的 code)
        ("通过样本：断言 + 命令 + rc + 门覆盖改动", PASS_FIXTURE, ["demo/calc.py"], 0, []),
        ("拒收：三段形容词，零命令",
         "# 交活\n\n## 已完成\n已完成登录修复，测试跑过，没问题。\n改动 3 个文件。\n",
         ["app.py"], 1, ["C1"]),
        ("拒收：有命令但没有返回码",
         "# 交活\n\n## 修复\n已修复空指针。\n\n```\n$ python3 app_gate.py\n2 项通过\n```\n",
         ["app.py"], 1, ["C1"]),
        ("拒收：骨架当完成",
         "# 交活\n\n## 交付\ncheck.py 骨架已完成（含占位实现）。\n\n```\n$ python3 check.py --selftest\nrc=0\n```\n",
         ["check.py"], 1, ["C3"]),
        ("拒收：门是红的仍交活",
         "# 交活\n\n## 修复\n已修复解析问题。\n\n```\n$ python3 app_gate.py\n3 项失败\nrc=1\n```\n",
         ["app.py"], 1, ["C2"]),
        ("拒收：门只跑了一个文件，改动有两个",
         "# 交活\n\n## 修复\n已完成两处修复。\n\n```\n$ python3 app_gate.py --file app.py\nrc=0\n```\n",
         ["app.py", "db.py"], 1, ["C2"]),
        ("拒收：宣称过门但零次执行",
         "# 交活\n\n## 验收\n这次改动已经过门检查，全部通过。\n\n```\n$ echo ok\nrc=0\n```\n",
         ["app.py"], 1, ["C3", "C2"]),
        ("拒收：命令指向不存在的文件",
         "# 交活\n\n## 证据\n已完成。\n\n```\n$ python3 tools/missing_gate.py\nrc=0\n```\n",
         [], 1, ["C1"]),
        ("边界：没有完成断言（不误判为通过/失败）",
         "# 交活\n\n## 未做\n登录页还没做，下一步再补。\n", [], 0, []),
        ("边界：rc=0 但输出里有失败字样",
         "# 交活\n\n## 修复\n已修复。\n\n```\n$ python3 app_gate.py\n2 failed\nrc=0\n```\n",
         ["app.py"], 1, ["C2"]),
        ("边界：门脚本自身不算「没覆盖」",
         "# 交活\n\n## 修复\n已修复。\n\n```\n$ python3 demo/gate_calc.py --file demo/calc.py\nrc=0\n```\n",
         ["demo/calc.py", "demo/gate_calc.py"], 0, []),
    ]


def selftest() -> int:
    print(f"check.py {VERSION} 自测")
    ok = True

    # 通过样本需要真实的路径存在（C1 会检查命令指向的文件），所以在临时目录里造一份。
    tmp = Path(tempfile.mkdtemp(prefix="aak-selftest-"))
    (tmp / "demo").mkdir(parents=True, exist_ok=True)
    (tmp / "demo" / "calc.py").write_text("def calc():\n    return 42\n", encoding="utf-8")
    (tmp / "demo" / "gate_calc.py").write_text(
        "import sys\nfrom calc import calc\nassert calc() == 42\n"
        "print('检查 2 项：返回值 42、无 TODO')\nsys.exit(0)\n", encoding="utf-8")
    # 其余用例会引用这些路径；存在即可，内容不影响判定。
    for f in ("app.py", "db.py", "app_gate.py", "check.py"):
        (tmp / f).write_text("# fixture\n", encoding="utf-8")

    def run_case(name, text, changed, expect_rc, expect_codes):
        nonlocal ok
        res = judge(text, changed, tmp)
        codes = {f.code for f in res.findings if f.level in ("FAIL", "WARN")}
        good = res.rc == expect_rc and all(c in codes for c in expect_codes)
        ok &= bool(good)
        print(f"  [{'PASS' if good else 'FAIL'}] rc={res.rc}（期望 {expect_rc}）"
              f" codes={sorted(codes) or '-'}  {name}")
        if not good:
            for f in res.findings:
                print(f"          {f.level} {f.code} L{f.line}: {f.msg}")

    for case in _fixtures():
        run_case(*case)

    # 负对照：把通过样本逐个改坏一处，必须翻红。这是本包自己的第 3 条判据。
    print("\n  负对照（改坏通过样本，门必须翻红）：")
    mutations = [
        ("删掉 `rc=0` 这一行", PASS_FIXTURE.replace("rc=0\n", ""), ["C1"]),
        ("把门改名成不含 gate 的 report.py", PASS_FIXTURE.replace("gate_calc.py", "report.py"), ["C2"]),
        ("把「已完成」改成「准备工作已完成」",
         PASS_FIXTURE.replace("已完成取整修复", "准备工作已完成"), ["C3"]),
    ]
    base_rc = judge(PASS_FIXTURE, ["demo/calc.py"], tmp).rc
    for name, text, codes in mutations:
        res = judge(text, ["demo/calc.py"], tmp)
        hit = {f.code for f in res.findings if f.level == "FAIL"}
        good = base_rc == 0 and res.rc == 1 and all(c in hit for c in codes)
        ok &= bool(good)
        print(f"  [{'PASS' if good else 'FAIL'}] 改坏前 rc={base_rc} → 改坏后 rc={res.rc}；{name}")

    # 回归：--repo 取改动清单时，交活说明本身必须被剔掉（stub 掉 git，只测接线）。
    with tempfile.TemporaryDirectory(prefix="aak-selftest-repo-") as d:
        repo = Path(d)
        (repo / "handoff.md").write_text("# x\n", encoding="utf-8")
        kept = pick_changed([], repo, "# x\n", repo / "handoff.md",
                            collector=lambda _r: ["handoff.md", "demo/calc.py"])
    good = kept == ["demo/calc.py"]
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] --repo 的改动清单剔掉交活说明本身：{kept}")

    print(f"\n{'✅ 自测全部通过' if ok else '⛔ 自测有失败项'}")
    return 0 if ok else 1


# ── 入口 ────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Agent 交活验收：一份交活说明 + 可选仓库 → rc=0 放行 / rc=1 拒收")
    ap.add_argument("handoff", nargs="?", help="交活说明文件（md/txt）")
    ap.add_argument("--repo", default="", help="仓库目录：用 git status 取改动清单，并作为路径基准")
    ap.add_argument("--changed", action="append", default=[], help="改动文件（可多次给）")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--run", action="store_true", help="复跑白名单里的证据命令（默认关闭）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if not a.handoff:
        print("需要交活说明文件（或用 --selftest）", file=sys.stderr)
        return 2

    p = Path(a.handoff)
    if not p.exists():
        print(f"文件不存在：{p}", file=sys.stderr)
        return 2
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # 按替换字符硬读会把中文断言读没：0 条断言 ⇒ rc=0 误放行。宁可拒收并让人转码。
        print(f"文件不是 UTF-8：{p}\n"
              "按 README §6 转码后重跑：iconv -f gbk -t utf-8 <文件> > h.md", file=sys.stderr)
        return 2

    if a.repo and not Path(a.repo).is_dir():
        print(f"--repo 不是目录：{a.repo}", file=sys.stderr)
        return 2
    base = Path(a.repo).resolve() if a.repo else p.resolve().parent

    changed = pick_changed(a.changed, Path(a.repo) if a.repo else None, text, p)

    res = judge(text, changed, base)
    if a.run:
        cmds, _ = parse_handoff(text)
        rerun(cmds, base, res)

    if a.json:
        print(json.dumps({
            "kit": "agent-acceptance-kit-v1",
            "version": VERSION,
            "source": str(p),
            "rc": res.rc,
            "stats": res.stats,
            "findings": [f.__dict__ for f in res.findings],
            "notes": res.notes,
        }, ensure_ascii=False, indent=2))
    else:
        print(render(res, str(p)))
    return res.rc


if __name__ == "__main__":
    sys.exit(main())
