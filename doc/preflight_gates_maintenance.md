# 维护门禁

维护任务（“接口测试报错了 / 同步最新链路 / 回归更新”）的主流程第 2 步是一道**硬门禁**：
**必须先真真切切跑一次 pytest，拿到失败，再动手修。** 不许凭想象修、不许看到报错就猜。

> 项目结构由项目根下的 `.api-autotest/config.json` 声明（不是由 skill 自身安装位置推导）。
> 工作目录、`PYTHONPATH`、pytest 命令模板都从这份配置来，见下文。

---

## 为什么必须先拿到失败

维护的根因只能从**真实的失败输出**里读出来。没有失败输出就修，等于闭着眼睛改代码：
改对了是运气，改错了还说不清。门禁就是拦住这种“凭感觉修”。

**没有失败就不进入修复。** 如果跑下来全绿，那说明“要维护的东西不存在”，把结果如实告诉用户即可。

---

## 第 1 步：生成并执行 pytest 命令

命令**不要手写**，用 `skill_utils/pytest_command.py` 的 `build_pytest_command()` 生成——
它会按配置切到工作目录并设好 `PYTHONPATH`：

- 工作目录来自配置 `paths.pytest_workdir`
- `PYTHONPATH` 来自配置 `pytest.pythonpath`
- 命令模板来自配置 `pytest.command_template`（默认 `pytest {target} -v --tb=short`）

```python
from skill_utils.config_loader import load_config
from skill_utils.pytest_command import build_pytest_command

config = load_config()
cmd = build_pytest_command("<要跑的用例或目录>", config=config, shell="bash")  # 必须显式传 shell
```

> **`shell=` 必须显式传**（`"bash"` 或 `"powershell"`）。省略时 `build_pytest_command` 会调
> `detect_shell()` 去猜，而它依据的 `PSModulePath` 是 Windows 机器级环境变量（Git Bash 里也有），
> 会误判成 PowerShell 并生成 `Set-Location` / `$env:` 语法，在真实 bash 会话里跑不起来。

先跑**失败的那一个用例**拿最小现场；范围不清时再全量跑，用 `--tb=short` 看清栈。

---

## 第 2 步：判定修的是哪一类

拿到失败输出后，先分类，**不要急着改**：

| 现象 | 判断 |
|---|---|
| 接口行为确实变了 / 后端有 BUG | **功能 BUG**：报告用户，不擅自“改用例让它绿” |
| 接口没变，是用例写法/数据过期了 | **用例待维护**：继续第 3 步 |
| 看不出是哪一类 | 明确说“**不明确**”，把失败原文给用户，让他定；**不许猜** |

关键纪律：**只能依据“最后一次 pytest 的中断报错”判断**，不能凭对业务的印象断言“这肯定是后端的问题”。

---

## 第 3 步：按优先级定位根因

用 `doc/troubleshooting.md` 的排查优先级逐层查（导入路径 → 编码 → 装饰器/插入位置 → fixture →
登录态 → 断言 → payload 结构 → 返回层级）。按顺序走，别跳。

---

## 第 4 步：最小补丁 → 重跑

- 改**最小的一处**，别顺手重构。维护任务的目的是让测试回到绿，不是改造测试。
- 重跑同一条命令。循环最多 **5 轮**，超过就停下上报——“修不动”本身也是要报告的信息。
- 每一轮都留下证据：**执行命令、关键日志、最终结果**，三项缺一不可。

---

## 第 5 步：同步索引（如果接口本身变了）

如果维护过程中发现接口新增/改名/换方法（而不只是用例数据过期），跑
`tools/scan_api_methods.py` 更新索引，保持索引与代码一致。

---

## 维护门禁自检

- [ ] **真的跑过** pytest 并拿到了失败输出，不是凭描述猜的。
- [ ] 判断过是“功能问题 / 用例待维护 / 不明确”，判断不了时如实说“不明确”。
- [ ] 命令由 `build_pytest_command()` 生成且**显式传了 `shell=`**。
- [ ] 修改是**最小补丁**，没有顺手重构。
- [ ] 给出了执行命令 + 关键日志 + 最终结果三项证据。
