# 失败排查

pytest 报错时，**按下面的优先级从上往下查**。顺序本身就是价值：越靠上的问题越基础、
越容易排查、也越容易伪装成别的问题。跳着查会把简单问题拖成大问题。

> 排查第一步永远是拿到**真实的失败输出**：用 `skill_utils/pytest_command.py` 的
> `build_pytest_command()` 生成命令（**显式传 `shell=`**）跑，配 `--tb=short` 看栈。
> 维护任务必须先跑到失败再动手——这是维护门禁的要求。

---

## 排查优先级（按此顺序）

### 1. 导入路径（`ModuleNotFoundError` / `ImportError`）

**症状**：`ModuleNotFoundError: No module named 'xxx'` 或 `cannot import name 'yyy'`。

**原因**：`PYTHONPATH` 没设对，或 import 的模块名/路径写错。

**怎么办**：
- 确认工作目录是配置里的 `paths.pytest_workdir`、`PYTHONPATH` 是 `pytest.pythonpath`——
  这正是 `build_pytest_command()` 帮你做掉的事，所以**用它生成命令，别手写**。
- 检查 import 的模块相对位置对不对（是 `from api.user import ...` 还是 `from user import ...`）。
- 确认被 import 的模块里没有语法错误导致整个模块 import 失败。

### 2. 编码（中文乱码 / 解析失败）

**症状**：`SyntaxError` 指向看似正常的一行；中文变成 `???` / `锟斤拷` / ``；
`UnicodeDecodeError`。

**原因**：文件带了 BOM、被存成了非 UTF-8、或换行是 CRLF。

**怎么办**：
- 用 `skill_utils/text_io.py` 的 `read_text_utf8()` 读文件，它能吞 BOM 并统一换行。
- 写文件用 `write_text_utf8()`，保证 **UTF-8 无 BOM、换行 `\n`**。
- 手工确认：写完重新 Read 一次，看中文是否正常、有没有 BOM 前缀方块。

### 3. 装饰器误挂 / 插入位置错误

**症状**：fixture 参数到处是 `TypeError: missing argument`；某个用例莫名没有被收集；
新增的函数混进了错误的缩进层级。

**原因**：`@pytest.mark.parametrize` 挂错了函数；新函数被粘进了另一个函数体内部（缩进错了）；
装饰器顺序不对。

**怎么办**：
- 看 pytest 收集数量：`pytest --collect-only`，确认你的用例**被收集到**了。
- 检查新函数与上一个函数之间的空行和缩进——它必须是模块级 `def`，不能缩进。

### 4. fixture / 前置依赖

**症状**：`fixture 'xxx' not found`；fixture 里 `yield` 之前抛错；setup 阶段失败。

**原因**：fixture 没定义、定义在不可见的作用域、或没写进 `conftest.py`；`scope` 用错。

**怎么办**：
- 确认 fixture 定义在用例能看到的 `conftest.py` 里（pytest 按目录向上找 `conftest.py`）。
- 骨架 `conftest.py` 里的 `api_session` 若还是 `TODO` 状态，必须按项目鉴权方式补全。
- 检查 `scope`：会话级 fixture 里不要依赖函数级的东西。

### 5. 登录态 / token / 会话

**症状**：接口返回未登录 / 无权限（业务码如 401、`code != 0`）；`api_session` 里没有 Cookie。

**原因**：登录没成功、token 过期、`api_session` 没把登录结果带上。

**怎么办**：
- 打印 `api_session.cookies` / `api_session.headers`，确认登录态真的挂上了。
- 登录失败时，用 `doc/mode_curl_manual.md` 的方法读后端登录接口，核对登录路径与字段。
- token 别写死；让它每次会话现登现取。

### 6. 断言与真实返回不匹配

**症状**：`AssertionError`，且左边右边都“看着对”。

**原因**：断言了错误的层级或错误的字段；期望值写错（类型、大小写）。

**怎么办**：
- 打印真实返回 `print(response.text)`，对照断言逐字看。
- 用**两阶段断言**：先只断 `status_code` 跑通，看清结构，再补精确断言。

### 7. payload 结构不匹配

**症状**：接口返回参数校验错误（如 `code` 为参数错误）；字段缺失 / 类型错。

**原因**：列表字段写成了字符串；数字写成了字符串；必填字段漏了；字段名大小写不对。

**怎么办**：
- 对照接口实际要的结构（最好是参考一条能跑的 cURL，见 `doc/mode_curl_manual.md`），逐字段核对。
- 列表一律传列表：`"roles": ["viewer"]`，不要传 `"viewer"`。

### 8. 返回层级误判

**症状**：`KeyError` / `TypeError: list indices must be integers`，或断言取到的值总是 None。

**原因**：返回是 `{code, msg, data}`，你却按纯 `data` 取；或反过来。

**怎么办**：
- 先打印完整返回，数清楚有几层，再决定 `response.json()["data"]["list"]` 到底该取到哪。
- 不要凭对业务的印象猜层级。

---

## 排查纪律

- **按顺序查，别跳**。第 6～8 层的问题经常是第 1～2 层问题伪装出来的。
- **一次改一处，改完立刻重跑**，别一次改一堆然后不知道是哪处生效了。
- **循环上限 5 轮**：超过还没绿，停下，把“执行命令 + 关键日志 + 已试过的修改”整理好上报。
- **证据三项**：执行命令、关键日志、最终结果，任何时候汇报都缺一不可。
