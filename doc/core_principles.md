# 核心原则

本 skill 的所有行为都从下面六条原则推导出来。遇到 SKILL.md 没写清的细节时，照这六条自己判断。

---

## 原则 1：项目结构由配置声明，不靠 skill 位置推导

本 skill 安装在用户级目录（`~/.claude/skills/api-autotest/`），不属于任何项目。
往上三层去找项目根是没有意义的（那是用户主目录）。所以项目结构**只能**由项目自己声明：

- 项目根下放一份 **`.api-autotest/config.json`**，声明接口方法目录、用例目录、索引库路径等一切结构信息。
- `skill_utils/project_locator.py` 的 `find_config(Path.cwd())` 从**当前工作目录**逐级向上查找这份配置；
  `find_project_root(Path.cwd())` 返回包含它的目录。
- 找到配置后，`skill_utils/config_loader.py` 的 `load_config()` 负责读取、校验、并把配置里的**相对路径一律相对
  `project_root` 解析**成绝对路径（`load_config()` 可不传参，是这里唯一真正无参的入口，
  内部会调用 `find_config(Path.cwd())` 定位配置）。
- 找不到配置时，`missing_config_guidance(Path.cwd())` 给出“先运行 `tools/init_project.py`”的指引，**停下，不要瞎跑**。

**禁止对目录名产生硬依赖**——即不允许“换个目录名就跑不起来”。为此，目录名不能写进代码逻辑、成为运行前提；
出现 `test/API_TEST` 这类**示例默认值**并不违反本原则，违反的是把它当成必须存在的固定结构。
目录叫什么是项目的事，配置说了算——这才是本 skill 能被“任意项目”复用的前提。

## 原则 2：写之前先查重

新增接口方法或用例之前，必须走完查重链，否则会写出重复实现：

1. 归一化 URL → `pure_path`
   用 `skill_utils/api_path_match.py` 的 `normalize_path()`（去 scheme/host/query），
   再 `to_pure_path()`（动态段 → `{param}`）。
2. 查索引 `(pure_path, method)`
   用 `skill_utils/api_index_db.py` 的 `find_by_path_method(db_path, pure_path, method)`。
3. 未命中 → 在接口方法层目录里 grep 路径片段（换几种拼写变体）。
4. 仍未命中 → 才认定为新增。

门禁阶段要把查重结果展示给用户看：“这几条索引里已有，这几条是新的”。

## 原则 3：索引是团队资产

接口索引不是缓存，是**团队共享的资产**——“哪些接口还没覆盖”对整个团队都有价值。

- 索引库路径由配置 `api_index.db_path` 指定，解析到**项目根**之下（随项目走，不随 skill 走），
  建议提交进项目仓库。
- 新增接口方法后必须同步更新索引：跑 `tools/scan_api_methods.py`（增量）或 `--full`（全量重建）。
- 索引里的 `source` 字段记录“这个接口最早是从哪知道的”（`scan` / `capture` / `source_analysis` / `manual`），
  `last_seen` 记录“它最近一次被看到是什么时候”。同一端点被其它来源再次发现时只刷新 `last_seen`，
  不改写 `source`——唯一键是 `(pure_path, method)`，一个端点一行。
- 索引时效超过 7 天要在预检时提示刷新。

## 原则 4：测试必须闭环

任何一次改动，都要给出**三项**证据，缺一不可：

1. **执行命令**（怎么跑的）
2. **关键日志**（跑出来什么）
3. **最终结果**（通过还是失败，失败在哪）

执行命令**由 `skill_utils/pytest_command.py` 的 `build_pytest_command()` 生成，不要手写**——
它会按配置切好工作目录、设好 `PYTHONPATH`，并适配 shell 语法。
（注意：调用时**必须显式传 `shell=`**，理由见 SKILL.md。）

失败就按 `doc/troubleshooting.md` 的优先级定位根因，改最小的一处，重跑。循环**最多 5 轮**。

## 原则 5：反假绿

“测试通过”必须意味着被测行为真的正确，不允许任何形式的自我欺骗：

- 禁止用 `try/except` 吞掉失败——把异常藏起来不等于修好了。
- 禁止用 `pytest.skip` 当挡箭牌——跳过的用例不算通过。
- 禁止 `assert x or True`、`assert response`（非空即真）这类**永真断言**——断言必须真的能失败。
- **两阶段断言**：先写基础断言跑通、取得真实返回，看清返回结构，再补精确断言，最后删掉调试 `print`。
- **UTF-8 安全**：写完文件重新 Read 一次，确认中文正常、无 BOM。读写统一走
  `skill_utils/text_io.py` 的 `read_text_utf8()` / `write_text_utf8()`。

## 原则 6：复用代码放 `skill_utils/`

被两个及以上模块复用的函数或常量，统一放进 `skill_utils/`，**不得复制粘贴**。当前已有的可复用能力：

| 模块 | 导出 | 职责 |
|---|---|---|
| `skill_utils/project_locator.py` | `find_config` / `find_project_root` / `missing_config_guidance` / `CONFIG_DIR_NAME` | 向上定位 `.api-autotest/config.json` |
| `skill_utils/config_loader.py` | `load_config` / `ConfigError` / `ApiTestConfig` | 读取、校验配置，相对路径 → 绝对路径 |
| `skill_utils/pytest_command.py` | `build_pytest_command` / `detect_shell` | 跨 shell 生成 pytest 命令 |
| `skill_utils/api_path_match.py` | `normalize_path` / `to_pure_path` / `api_path_matches` | URL 归一化与 `{n}` 通配匹配 |
| `skill_utils/api_index_db.py` | `replace_index` / `upsert_many` / `find_by_path_method` / `list_records` | 索引库读写 |
| `skill_utils/text_io.py` | `read_text_utf8` / `write_text_utf8` | UTF-8 无 BOM 读写 |

`ApiTestConfig` 的字段名与配置 JSON 的对应关系：

| 配置 JSON 键 | 字段（解析后为绝对路径） |
|---|---|
| `project_root` | `project_root`（必填） |
| `paths.api_method_dirs` | `api_method_dirs` |
| `paths.test_case_dirs` | `test_case_dirs` |
| `paths.pytest_workdir` | `pytest_workdir` |
| `paths.runtime_temp_dir` | `runtime_temp_dir` |
| `api_index.scan_dirs` | `api_scan_dirs`（目录不存在会报错） |
| `api_index.db_path` | `api_index_db_path` |
| `api_index.extract_rules_path` | `extract_rules_path` |
| `pytest.pythonpath` | `pytest_pythonpath` |
| `pytest.command_template` | `pytest_command_template` |
| `capture.*` | `capture`（dict，抓包驱动相关，见 `doc/mode_capture_driven.md`） |
| `source_analysis.*` | `source_analysis`（dict，源码分析相关，见 `doc/mode_source_analysis.md`） |
