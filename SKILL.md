---
name: api-autotest
description: 通用接口自动化测试 skill，面向 python + pytest + requests。用于在任意项目中新增、维护接口测试方法与 pytest 用例：接入引导、接口索引与查重、抓包/源码/手工/参考已有用例四种发现接口的方式、pytest 报错驱动的修复闭环。当用户说“给某个接口写自动化测试”“补接口用例”“接口回归”“接口测试报错帮我修”时使用。
---

# api-autotest

通用接口自动化测试 skill，面向 **python + pytest + requests**。

被测系统可以是任何语言写的后端（Java / Python / Node 等），只要它能通过 HTTP 访问——
测试代码永远跑在 Python 侧，被测服务只用它的接口地址。

本 skill 安装在用户级目录（`~/.claude/skills/api-autotest/`），**不属于任何项目**。
因此它不假设、也不推导任何项目目录结构：**项目结构一律由项目自己的
`.api-autotest/config.json` 声明**。读不到这份配置就无法工作——这是设计如此，不是缺陷。

## 第一步永远是：定位项目

主流程的第 0 步是**预检**，核心动作是定位配置：

1. 用 `skill_utils/project_locator.py` 的 `find_config(Path.cwd())` 从当前工作目录**逐级向上**查找 `.api-autotest/config.json`。
2. **找到** → 用 `skill_utils/config_loader.py` 的 `load_config()` 读取并校验配置，继续主流程
   （`load_config()` 可不传参，是本流程里唯一真正无参的入口，内部按上面方式定位配置）。
3. **找不到** → **立即停止**。不要在无配置的情况下凭默认值瞎跑。把
   `skill_utils/project_locator.py` 的 `missing_config_guidance(Path.cwd())` 返回的指引原样交给用户，
   告诉他先运行 `tools/init_project.py` 接入本项目（该脚本会探测项目结构、询问被测服务地址，并生成配置与最小骨架）。
4. 找到配置后**检查索引时效**：索引记录里的 `last_seen` 若距今超过 7 天，提示用户先跑一次
   `tools/scan_api_methods.py` 刷新索引，再开始工作。

配置读取失败（缺 `project_root`、JSON 非法、`api_index.scan_dirs` 指向的目录不存在等）会抛
`skill_utils/config_loader.py` 的 `ConfigError`。把错误信息如实转达用户，不要吞掉、不要改用默认值继续。

## 主流程

按顺序执行，**门禁处硬停**，等用户确认再往下走：

0. **预检** —— 定位 `.api-autotest/config.json`；检查索引时效（`last_seen` 超过 7 天则提示刷新）。
1. **判定任务类型** —— 新增 / 维护。
   用户说了“修复 / 同步最新链路 / 回归更新 / 报错了”即判为**维护**；
   说了“给某个接口写测试 / 补用例 / 新增覆盖”即判为**新增**；
   **只在完全判断不出时才问一句**，不要拿这个问题例行打扰用户。
2. **门禁** —— 先跑完查重链（见下），把结果摆给用户看（“这几条索引里已有，这几条是新的”），
   然后声明**落点 / 方式 / 范围**三件事（见 `doc/preflight_gates_new.md`），**等用户确认后才继续（硬停）**。
3. **读规范** —— 强制，不允许只看本文件摘要就动手：
   - **永远必读** `doc/coding_style_guide.md`
   - **维护任务额外必读** `doc/preflight_gates_maintenance.md`
   - **按选定方式必读** 对应的 `doc/mode_*.md`（见下方“四种新增方式”表）
4. **编写** —— 草稿门禁：抓包草稿与源码分析草稿**必须先经用户确认**（这两种方式产出的是待测接口清单，
   让人先勾选，再写码）；确认后写接口方法与用例。
5. **pytest 闭环** —— 用 `skill_utils/pytest_command.py` 生成命令并执行；
   失败按 `doc/troubleshooting.md` 的优先级逐层定位，循环修复，**最多 5 轮**，超过则停下上报。
6. **输出清单** —— 汇报三件事，缺一不可：新增/维护接口方法（N 个）、新增/维护用例（N 个）、pytest 执行结果。

## 四种新增方式

| 方式 | 适用场景 | 输入 | 详见 |
|---|---|---|---|
| 抓包驱动 | 黑盒、没有文档，只能看真实请求 | 抓包产物 | 规划中（见计划第二份），本版未实现 |
| 参考已有用例 | 项目里已有相似实现，可抄骨架 | 已有文件 + 函数名 | `doc/mode_reference_case.md` |
| cURL 手工 | 手上已经有一条能跑的请求 | cURL + 真实响应 | `doc/mode_curl_manual.md` |
| 源码分析 | 有后端源码，想成批导出接口 | 源码目录（Java / Python / Node） | 规划中（见计划第二份），本版未实现 |

> 抓包驱动与源码分析所需的 `capture/`、`analyzers/` 模块在**计划第二份**才实现，当前版本没有。
> 现在遇到只能靠抓包或源码才能发现的接口，请如实告诉用户“该能力尚未实现”，不要假装能做。

## 新增前必做：查重链

新增接口方法或用例之前，**必须**走完这条链，避免重复实现：

1. 归一化 URL：用 `skill_utils/api_path_match.py` 的 `normalize_path()` 去 host/query，
   再用 `to_pure_path()` 把动态段（纯数字 / UUID / `{x}` / `:name` 等）统一成 `{param}`，得到 `pure_path`。
2. 查索引：用 `skill_utils/api_index_db.py` 的 `find_by_path_method(db_path, pure_path, method)` 查 `(pure_path, method)`。
3. 未命中 → 在接口方法层目录里 grep 该路径片段（多种拼写变体都试）。
4. 仍未命中 → 才认定为**新增**。

需要列出已有接口时用 `list_records(db_path, source=...)`。

## 索引是怎么维护的

索引是一份 SQLite 库，路径由配置里的 `api_index.db_path` 指定，随项目走、建议纳入项目版本管理（它是团队共享资产）。

- 全量重建：`tools/scan_api_methods.py --full`（清空后重写）
- 增量更新：`tools/scan_api_methods.py`（已存在的端点只刷新 `last_seen`）
- 只报条数不写库：`tools/scan_api_methods.py --dry-run`
- 指定配置文件：`tools/scan_api_methods.py` 的 `--config <路径>` 可缺省（省略时按 CWD 向上探测 `.api-autotest/config.json`）；
  `tools/append_extract_rule.py` 的 `--config` 为必填；`tools/init_project.py` 没有 `--config`，用 `--project-root` 指定项目根。

新增接口方法后，**必须**跑一次扫描把新接口补进索引（或让维护者知道索引已过期）。

扫描器认不出的 URL 写法，用 `tools/append_extract_rule.py` 教它一次，以后永久认得：
先 `--rule <规则JSON>` 预览（**不落盘、不落库**），确认无误再加 `--apply` 落盘并增量入库。

## 生成并执行 pytest 命令（务必显式传 `shell`）

**不要手写 pytest 命令**，用 `skill_utils/pytest_command.py` 的 `build_pytest_command()` 生成——
它会自动切到配置里的工作目录（`paths.pytest_workdir`）并设好 `PYTHONPATH`（`pytest.pythonpath`）。

```python
from skill_utils.config_loader import load_config
from skill_utils.pytest_command import build_pytest_command

config = load_config()                       # 或 load_config("<config.json 路径>")
cmd = build_pytest_command(
    "tests/cases/test_user.py::test_create_user",
    config=config,
    shell="bash",                            # ← 必须显式传！见下
)
```

> **必须显式传 `shell=`（`"bash"` 或 `"powershell"`），不要省略。**
>
> `build_pytest_command` 省略 `shell` 时会调用 `detect_shell()` 猜当前 shell，
> 而它靠 `PSModulePath` 这个**Windows 机器级环境变量**判断——该变量在 Git Bash 里同样存在，
> 于是 `detect_shell()` 会误判成 `"powershell"`，生成 `Set-Location` / `$env:` 语法，
> 在真实的 bash 会话里执行会直接失败。
>
> 判断依据是“我现在到底在 bash 还是 PowerShell”，这个只有你（AI）在运行现场知道，
> 函数自己猜不可靠。所以在 bash 里传 `shell="bash"`，在 PowerShell 里传 `shell="powershell"`。

命令模板本身来自配置 `pytest.command_template`（默认 `pytest {target} -v --tb=short`），
改命令格式改配置即可，不要改代码。

## 反假绿约束（硬性）

- 禁止用 `try/except` 吞掉失败。
- 禁止用 `pytest.skip` 当挡箭牌。
- 禁止 `assert x or True` 这类永真断言——断言必须**真的能失败**。
- **两阶段断言**：先写基础断言跑通、取得真实返回，看清结构后再补精确断言，并删掉调试用的 `print`。
- **UTF-8 安全**：写完文件必须重新 Read 确认中文正常、无 BOM 前缀（Windows + 中文路径的老坑）。
  读写统一走 `skill_utils/text_io.py` 的 `read_text_utf8()` / `write_text_utf8()`。
- 任何一次改动，都要给出**三项**：执行命令、关键日志、最终结果。缺一不可。

## 工具速查

| 工具 | 作用 | 关键参数 |
|---|---|---|
| `tools/init_project.py` | 接入引导：探测结构、生成配置与骨架 | `--project-root` / `--answers` / `--dry-run` / `--force` |
| `tools/scan_api_methods.py` | 扫描接口方法层，更新索引 | `--config` / `--full` / `--dry-run` |
| `tools/append_extract_rule.py` | 追加提取规则并按新规则重扫 | `--config` / `--rule` / `--apply` |

模块与函数的完整清单、设计理由见 `doc/core_principles.md`。

## 文档索引

| 文档 | 什么时候读 |
|---|---|
| `doc/core_principles.md` | 理解本 skill 的六条核心原则（配置驱动、查重、索引、闭环、反假绿、复用纪律） |
| `doc/coding_style_guide.md` | 编写接口方法与用例前**必读** |
| `doc/preflight_gates_new.md` | 新增任务的“门禁”怎么走 |
| `doc/preflight_gates_maintenance.md` | 维护任务的“门禁”怎么走 |
| `doc/mode_reference_case.md` | 选定“参考已有用例”方式时 |
| `doc/mode_curl_manual.md` | 选定“cURL 手工”方式时 |
| `doc/troubleshooting.md` | pytest 失败时，按优先级排查 |
