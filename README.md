# Agent 交活验收包 v1（Acceptance Kit）

> 给你的 coding agent 装一道门：它说「做完了」，门只问——**命令在哪，返回码多少**。
>
> 本仓库为公开源码版。付费 ¥19.9 买断版 = 逐件 sha256 校验 zip + 可跑示例 + 验收手册 + false-green 清单（见 Release）。

# Agent 交活验收包 v1

给你的 agent 交活那一刻装一道门：**它说「做完了」，门只问一句 —— 命令在哪，返回码多少。**

不依赖任何第三方库，不联网，不读你的账号数据。整个包是几个 `.py` 和一个 markdown。

---

## 0. 三十秒判断要不要往下看

适用：你用 Codex / Claude Code / Cursor / 自建 agent 改代码，交付时靠读 diff 或靠它自己汇报。
不适用：你只想要一个「自动判断代码好不好」的工具 —— 这个包做不到，也没打算做。

它替代的是**「通读 diff 找有没有证据」**这一步，不是「读 diff」。

---

## 1. 需要什么

- Python 3.8+（只用标准库；`python3 --version` 有输出即可）
- 一个文件：agent 的收工说明（markdown / txt 都行）
- 可选：git 仓库路径（用来自动取改动清单）

解压后先确认能跑：

```bash
cd agent-acceptance-kit-v1
python3 check.py --selftest; echo "rc=$?"
```

期望最后两行是 `✅ 自测全部通过` 和 `rc=0`。这一步同时验证了「门能被改坏」。

---

## 2. 一条命令

```bash
python3 check.py examples/01-reject-adjectives/handoff.md; echo "rc=$?"
```

输出（节选）：

```
交活验收：拒收  (rc=1)
读到的结构：2 条完成断言 / 0 条命令（0 条带返回码）/ 0 个门 / 2 个改动文件
依据：
  [FAIL C1] 第 5 行  2 处完成断言，0 条可复现命令。第一处：「已完成登录页空指针修复，测试也跑过了，没问题。」
  [FAIL C2] 第 9 行  改动清单有 2 个文件（api/session.py, web/login.js），但没有任何门的执行记录。
```

`rc=1` 就是拒收。接到 CI 或 agent 的收工钩子里，非 0 就别让它交。

---

## 3. 三个例子（先看它们，再看自己的）

```bash
python3 check.py examples/02-pass/handoff.md;                 echo "rc=$?"   # 0 放行
python3 check.py examples/01-reject-adjectives/handoff.md;    echo "rc=$?"   # 1 拒收：全是形容词
python3 check.py examples/03-edge/handoff.md;                 echo "rc=$?"   # 1 边界：有真门，但漏了一个文件
```

| 例子 | 期望 rc | 它示范什么 |
|---|---|---|
| `02-pass` | **0** | 断言 + 命令 + 返回码 + 门覆盖了改动文件。这是「合格的交付说明」长什么样 |
| `01-reject-adjectives` | **1** | 「完成了 / 跑过了 / 没问题」+ 零命令。最能骗人的形态：读起来毫无破绽 |
| `03-edge` | **1** | 有真门、真 rc=0、文件也真存在，但门只覆盖 `api/session.py`，另一个改动 `web/login.js` 没人看；而且「准备工作已完成」被写进了完成 |

`03-edge` 是重点：它不是「明显没做」，是**看起来已经做完了**。只查「有没有命令」的门会放过它。

想让它真的跑一遍证据命令（默认不跑，见 §8）：

```bash
python3 check.py examples/02-pass/handoff.md --run
# stderr: [复跑] `python3 demo_repo/gate_calc.py` → rc=0（记录 0） ✓
```

---

## 4. 接进你自己的流程（两种用法）

### A. 有 git 仓库（推荐）

```bash
python3 check.py /path/to/agent-handoff.md --repo /path/to/your/repo
```

`--repo` 做两件事：用 `git status --porcelain --untracked-files=all` 取改动清单（未跟踪的新目录会展开成具体文件）；把命令里的相对路径按仓库根解析。
交活说明这个文件本身不计入改动清单 —— 它是证据文档，没有门会去测它。
于是「改了 3 个文件，但门只跑了 1 个」会被抓出来。

拿包内例子试这一条时，仓库根要指向例子自己（`--repo examples/02-pass`）：
例子里的命令是相对它那个目录写的，指向包根会报「命令里的文件不存在」，那是路径基准问题，不是判据问题。

### B. 没有 git / 只想贴一段文字

在交活说明里加一节：

```markdown
## 改动
- `src/a.py`
- `src/b.py`
```

`check.py` 会从这一节里取反引号路径当改动清单。取不到时，C2 只能判「有没有门」，
判不了「门覆没覆盖改动」—— 这种情况它会打印一行 `[? HUMAN]` 让你自己确认。

### 让 agent 自己交这份说明

在 `AGENTS.md` / `CLAUDE.md` / 系统提示里加一段（**这是建议，不是判据** —— 判据是那条命令）：

```
收工前把交活说明写到 handoff.md：每节一个结论，结论下面贴命令和 `rc=N`。
然后运行 `python3 check.py handoff.md --repo .`，rc 非 0 就继续修，不要交。
```

---

## 5. 三条判据分别在查什么

| 代号 | 判据 | 命中条件（会拒收） | 来源 |
|---|---|---|---|
| **C1** | 说完成，但没有可复现的命令/证据 | 有完成断言但 0 条命令；或有命令但 0 个返回码；或某个非信息节的结论在本节内没有带 rc 的命令；或命令指向不存在的文件 | 一篇 3100 字、标题 42 字的稿子走完全流程无红灯 —— 「合格」只写在散文里 |
| **C2** | 改了文件，但没跑门 / 门没覆盖改动 | 有改动清单但没有任何门；门全红却按完成交；门只覆盖了部分改动文件；rc=0 但输出里有 `failed`/`Traceback` 等失败字样 | 修复只落在被 cron 执行的那份副本，仓库那份落后 6 行；另有脚本失败时 `return 0`，面板恒绿 |
| **C3** | 把「准备」当「完成」 | 断言里出现 骨架 / stub / 占位 / 干跑 / 示例数据 / 准备 / 待确认 / 等待 / 计划…；或宣称「过门了」但全文 0 次门的执行记录 | `fetch_inbox()` 读不到配置时 `return []`，把「没读到」下传成「今天没订单」，rc=0 |

三个代号会同时报。`rc=1` = 至少一条 FAIL；`rc=0` = 一条 FAIL 都没有（可能有 `[? HUMAN]`）。

### 交活说明的推荐形状

```markdown
# 交活：修 calc 取整

## 结论
已修复取整，自检通过。              ← 概述类小节允许概括

## 改动
- `demo_repo/calc.py`

## 证据
```
$ python3 demo_repo/gate_calc.py
检查 2 项：返回值 42、无 TODO
rc=0
```

## 未做
没改调用方。
```

要点只有三个：**命令单独一行、以 `$ ` 开头放进 ``` 围栏、输出里有一行 `rc=0`。**
`rc=0` / `exit code: 0` / `退出码 0` / `[exit 0]` 都认。

---

## 6. 常见报错 / 假失败排查

| 现象 | 原因 | 怎么办 |
|---|---|---|
| `文件不存在` / rc=2 | 路径不对，或没先 `cd` 进包目录 | 用绝对路径；`--selftest` 确认脚本本身能跑 |
| 「0 条可复现命令」但明明贴了命令 | 命令在普通段落里，没有 ``` 围栏，也没有 `$ ` 前缀 | 包进 ``` 围栏并以 `$ ` 开头（这是判据能看见它的唯一方式） |
| 「有 N 条命令，但 0 条记录了返回码」 | 只贴了输出，没贴 `rc=` | 在命令块最后加一行 `rc=0`（由程序打印，别手写） |
| 「门没有覆盖 X」但你确实测了 | 门带了 `--file`/路径参数，只覆盖了参数里那几个；或改动清单里有生成文件 | 跑全量门（如不带路径参数的 `pytest`），或把 X 加进门参数 |
| 「把准备当完成」但你确实做完了 | 句子里有「准备 / 等待 / 待确认 / 计划」 | 把这条挪到「未做」并写清还差什么；或者改成「已执行/已合并」。这不是让你撒谎，是让你别用中间态词描述终态 |
| 「宣称有门/跑过检查」但你没门 | 句子里出现「门 / gate / 检查 / 自检」被当成声明 | 要么真跑一遍贴 rc，要么删掉这句话 |
| `--run` 说「不在白名单」 | 默认只复跑 `python3/pytest/npm/make/...`，且拒绝 `; | > &&` | 手工跑一次；这是故意的，交活说明是不可信文本 |

> ⚠ 白名单不是沙箱：`--run` 仍会执行交活说明里的代码（受白名单限制的解释器也可能被用来跑任意脚本）。只对可信内容使用 `--run`。

| `文件不是 UTF-8` / rc=2 | 文件是 GBK 等编码；硬按 UTF-8 读会把中文断言读没，等于「零断言 ⇒ 放行」 | `iconv -f gbk -t utf-8 handoff.md > h.md`，再跑 `h.md` |
| Windows 上 `python3` 不存在 | 命令名不同 | 用 `python check.py ...`（判据不挑解释器名） |

**假失败的处理原则**：先判断是「门的类别错了」还是「文档的写法真的有歧义」。
前者改门（加 kind / 改判据），后者改文档。**不要靠改正文去迁就一条判错的判据** —— 那是把门变成装饰。

---

## 7. 包里还有什么

```
check.py                        主检查器（746 行，纯标准库；三条判据的核心在 judge()）
skeleton_30.py                  31 行骨架：只判「有断言就必须有返回码」，方便先跑起来
examples/                       三个最小例子（见 §3）
patterns/
  number_traceback.py           数字回源：边界精确匹配，防 "0" 命中 "10-20"
  entity_verify.py              实体核验：本地路径不算仓库（那次假失败的修法）
  negative_control.py           负对照跑法：改坏一处，门必须红
  samples/                      上面两个脚本的示例输入
gates-annotated/
  01-article-length-kind-gate.py  篇幅/标题门（按 kind 分阈值；含「3100 字无红灯」原案）
  02-number-entity-gate.py        数字/实体门（facts.json 单一来源）
  03-headline-claim-gate.py       标题断言门（claims 由生成方声明，门只机械核验）
false-green-checklist.md        12 条假绿灯/假失败，每条「现象 / 根因 / 怎么防」
MANIFEST.json                   文件清单 + sha256 + 版本
```

每个脚本都能单独自测：

```bash
python3 patterns/number_traceback.py --selftest
python3 patterns/entity_verify.py --selftest
python3 patterns/negative_control.py \
  --gate "python3 patterns/number_traceback.py --text {sample} --facts patterns/samples/facts.json" \
  --sample patterns/samples/draft.md --mutate "4%=5%"
python3 gates-annotated/01-article-length-kind-gate.py --selftest
python3 gates-annotated/02-number-entity-gate.py --selftest
python3 gates-annotated/03-headline-claim-gate.py --selftest
```

---

## 8. 它做不到什么（请当说明书读，不是免责声明）

1. **不判真假。** 它只判「证据结构在不在」。一条命令写了但是假的、输出是编的，结构上可能过。
   `--run` 能拆掉「手写 rc」这一种，拆不掉「输出是编的」。
2. **不判「门本身有没有用」。** 一个永远 `exit 0` 的 gate 也能满足 C2。
   用 `patterns/negative_control.py` 改坏一处，它必须红 —— 这才是门活着的证据。
3. **概述节不逐条核验。** 标题含 结论/总结/概述/摘要/改动/风险/未做 等字样的小节视为信息节，
   里面的断言不要求本节内带命令（否则会逼出重复贴命令的假失败）。想严格，把这些断言挪进有证据的节。
4. **不读语义。** 「这条测试有没有覆盖这个 bug」「diff 里有没有加私货」—— 需人工判断。
5. **没有改动清单时 C2 降级。** 没 git、说明里也没有「改动」节，它只能判「有没有门」。
6. **默认不执行任何东西。** 只有显式 `--run` 才会复跑，且只跑白名单内的简单命令。
7. **`check.py` 是 746 行，不是 30 行。** 30 行的骨架在 `skeleton_30.py`；
   多出来的行是解析、按节归类、改动清单比对、人话输出和自测。想读懂判据只看 `judge()` 一个函数。

---

## 9. 版本

`v1`。文件与哈希见 `MANIFEST.json`（`python3 make_manifest.py` 可重算）。
包内不含任何账号、token、cookie 或客户数据；所有示例都是虚构的小文件。
