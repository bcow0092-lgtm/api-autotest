# api-autotest

一个通用的**接口自动化测试 skill**，面向 **python + pytest + requests**：把任意项目接入后，
帮你在新增/维护接口测试时做接入引导、接口索引与查重、以及 pytest 报错驱动的修复闭环。

被测系统可以用任何语言写（Java / Python / Node 等），只要它能通过 HTTP 访问——
测试代码永远跑在 Python 侧，只用被测服务的接口地址。

## 安装位置与方式

本 skill 装在**用户级目录**，不属于任何项目：

```
~/.claude/skills/api-autotest/          # Windows: C:\Users\<你>\.claude\skills\api-autotest\
```

安装方式就是把这个目录放到上面这个位置（Claude Code 会自动识别 `~/.claude/skills/` 下的
skill）。目录里包含 `SKILL.md`、`tools/`、`skill_utils/`、`doc/`、`config.example.json` 与
本文件。它**不假设、也不推导任何项目目录结构**：项目结构一律由项目自己的
`.api-autotest/config.json` 声明。

> 依赖：Python 3.10+，以及 `pytest` / `requests`。索引是本地 SQLite，无需额外服务。

## 三步接入（新项目上手）

以下命令都假定：`<项目根>` 是你要接入的项目的根目录，`<skill>` 是本 skill 的安装目录
（如 `~/.claude/skills/api-autotest`）。

### 第一步：跑接入引导，生成配置与骨架

```bash
# 交互式：会打印探测到的项目结构，再逐项问你（被测服务地址等）
python "<skill>/tools/init_project.py" --project-root "<项目根>"

# 只想先看看会生成什么、不落盘：
python "<skill>/tools/init_project.py" --project-root "<项目根>" --dry-run
```

它会：探测项目结构（语言、可能的接口目录）→ 询问 `baseurl` 与目录 →
生成 `<项目根>/.api-autotest/config.json`、建好接口目录/用例目录，并放入一个带 `TODO`
的 `conftest.py` 骨架（登录 fixture 因项目而异，需你自己按后端登录接口补全）。

命令名与参数：`tools/init_project.py` 支持 `--project-root` / `--answers` / `--dry-run` / `--force`
（`--force` 用于按本次答案覆盖已存在的配置；不加时重跑只读现有配置做自检、**不覆盖**用户改动）。

### 第二步：编辑 `.api-autotest/config.json`

打开 `<项目根>/.api-autotest/config.json`，**重点核对两处**：

- `project_root`：必须是**被测项目的绝对路径**。
- `api_index.scan_dirs`：必须指向**真正存放接口方法的目录**。
  这个目录写错是本 skill 最常见的坑——写错的直接后果是“扫 0 条却不报错”，
  所以 `config_loader` 会校验该目录**必须存在**，否则直接报 `ConfigError`。

其余字段的默认值通常可用，速查表见下节。

### 第三步：跑一次扫描，把已有接口收进索引

```bash
# 全量重建（首次接入用这个）
python "<skill>/tools/scan_api_methods.py" --config "<项目根>/.api-autotest/config.json" --full
```

看到类似 `[scan_api_methods] mode=full scanned=<文件数> written=<接口数>` 即成功。
如果打印 `WARN: 未扫到任何接口`，说明 `api_index.scan_dirs` 没指向真正的接口方法层，
回到第二步修正后再跑。

### 怎么算“接好了”：两条自检

```bash
# 自检 1：只看条数、不写库
python "<skill>/tools/scan_api_methods.py" --config "<项目根>/.api-autotest/config.json" --dry-run
#   期望：scanned=<非 0>。若 records=0，说明目录配错或写法不被识别。

# 自检 2：直接查索引库，确认端点确实落库
python -c "import sqlite3;c=sqlite3.connect(r'<项目根>/test/API_TEST/.index/api_index.sqlite3');print(c.execute('SELECT api_url, method FROM api_methods').fetchall())"
#   期望：打印出你项目里已有的接口 (路径, 方法) 列表。
```

（自检 2 的库路径以你 `config.json` 里 `api_index.db_path` 为准：相对路径相对 `project_root` 解析。）

## 日常使用

接入完成后，后续维护只需两件事：

- **扫描**：接口方法层有新增后，跑 `tools/scan_api_methods.py`（不加 `--full` 即增量，
  已存在的端点只刷新 `last_seen`）。`--config` 可缺省：省略时按 CWD 向上探测
  `.api-autotest/config.json`；需要显式指定时用 `--config <配置>`。
  （区分记法：`tools/append_extract_rule.py` 的 `--config` 为**必填**；
  `tools/init_project.py` **没有** `--config`，用 `--project-root` 指定项目根。）
- **扫描器认不出的 URL 写法**：用 `tools/append_extract_rule.py --config <配置> --rule <规则JSON>`
  先把新规则**预览**（不落盘、不落库），确认无误再加 `--apply` 落盘并增量入库。

执行用例时**不要手写 pytest 命令**，用 `skill_utils/pytest_command.py` 的
`build_pytest_command()` 生成——它会按配置切到 `paths.pytest_workdir` 并设好 `PYTHONPATH`。
在 bash 会话里记得显式传 `shell="bash"`（在 PowerShell 里传 `"powershell"`）。

完整主流程（预检 → 门禁 → 读规范 → 编写 → pytest 闭环）见 `SKILL.md`；
六条核心原则与模块清单见 `doc/core_principles.md`。

## 配置字段速查表

对应 `config.example.json`（顶层字段与 `skill_utils/config_loader.py` 解析的 schema 一致）。
配置里出现的**相对路径一律相对 `project_root` 解析**。

| 字段 | 含义 | 备注 |
|---|---|---|
| `project_root` | 被测项目根目录（绝对路径） | **必填**，目录不存在直接报错 |
| `framework` | 测试框架标识 | 默认 `pytest_requests` |
| `paths.api_method_dirs` | 接口方法层目录（放 `*_api.py`） | 相对 `project_root` |
| `paths.test_case_dirs` | 用例目录（放 `test_*.py`） | 相对 `project_root` |
| `paths.pytest_workdir` | 跑 pytest 的工作目录 | 生成命令时自动 `cd` 到这里 |
| `paths.runtime_temp_dir` | 运行时临时目录 | 抓包/源码分析等中间产物用 |
| `api_index.db_path` | 索引 SQLite 库路径 | 团队共享资产，建议入库 |
| `api_index.scan_dirs` | 扫描器要扫的目录 | **必须存在**，否则报 `ConfigError` |
| `api_index.extract_rules_path` | 提取规则文件路径 | 由 `append_extract_rule.py` 追加 |
| `pytest.pythonpath` | 执行 pytest 时的 `PYTHONPATH` | 默认 `.` |
| `pytest.command_template` | pytest 命令模板 | `{target}` 是占位符 |
| `capture.listen_port` | 抓包监听端口 | 抓包服务用；可用环境变量 `CAPTURE_PORT` 临时覆盖 |
| `capture.baseurl` | 被测服务地址 | 接入引导会问；抓包只录该 host |
| `capture.include_prefixes` | 只抓这些前缀的请求 | 抓包服务用（白名单） |
| `capture.exclude_prefixes` | 排除这些前缀 | 抓包服务用（黑名单） |
| `capture.login_path_hints` | 登录接口路径提示 | 命中即视为登录请求，默认不记录 |
| `capture.session_cookie_names` | 会话 cookie 名 | 本版仅解析保留，暂未参与过滤 |
| `source_analysis` | 源码分析配置（`language` / `roots` / `url_prefix_map`） | `tools/analyze_source.py` 用 |

## 版本管理建议

**把 `.api-autotest/config.json` 和索引库（`api_index.db_path` 指向的文件）提交进项目仓库。**
索引是**团队共享资产**：它记录了本项目已覆盖的接口，团队里每个人的查重、报错定位都依赖它；
只放在某个人本地会让其他人反复重复实现已有接口。配置文件同理，它是团队的接入契约。

（`paths.runtime_temp_dir` 这类运行时中间产物目录则应加入 `.gitignore`，不要提交。）

## 抓包驱动与源码分析

除了「参考已有用例」「cURL 手工」两种方式，本版还实现了两种**成批发现接口**的方式：

- **抓包驱动**（`capture/`）：用 mitmproxy 把真实 HTTP 请求录成 JSONL，再比对索引生成勾选草稿。
  启动 `capture/start.bat`（端口来自 `capture.listen_port`，可用 `CAPTURE_PORT` 覆盖），
  产物 `<runtime_temp_dir>/latest.jsonl`，比对用 `python tools/match_captures.py` →
  `capture_selection.md`；服务状态用 `python tools/check_capture_server.py --config <配置>` 检查。
  详见 `doc/mode_capture_driven.md`。
- **源码分析**（`analyzers/`）：支持 Java/Spring、Python（FastAPI/Flask/Django）、
  Node（Express/NestJS），用 `python tools/analyze_source.py [--language ...] [--dry-run]`
  成批导出接口，产物 `<runtime_temp_dir>/source_analysis_result.md`。详见 `doc/mode_source_analysis.md`。

这两种方式产出的都是**待测接口清单草稿**——必须交给用户勾选后，才继续写用例（草稿门禁）。

预检索引时效用 `python tools/preflight_check.py`（只读不写）。四种新增方式与工具速查见 `SKILL.md`。

## 许可

MIT License，衍生自 [`buer2233/ai-api-test-skill`](https://github.com/buer2233/ai-api-test-skill)。
详见仓库根目录的 `LICENSE`。
