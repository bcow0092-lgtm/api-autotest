# 维护主路径：pytest 驱动修复

> 路径约定：文中 `tools/` 等指 **skill 安装目录**（非被测项目同名目录），详见 `SKILL.md` 顶部。

**适用场景**：已有的接口测试红了（“报错了 / 帮我修 / 同步最新链路 / 回归更新”）。
本方式从**最后一次 pytest 失败**出发，一路修到绿。

> 维护的判定、三分法与纪律见 `doc/maintenance_context.md`；硬门禁见
> `doc/preflight_gates_maintenance.md`。本文件只讲**怎么一步步做**。
> 命令的 shell、工作目录、`PYTHONPATH` 都来自项目配置 `.api-autotest/config.json`。

---

## 主路径一览

```
最后一次 pytest 失败
  → 生成并执行命令（build_pytest_command，显式 shell=）
  → 按 doc/troubleshooting.md 的八级优先级定位根因
  → 最小补丁
  → 重跑
  → 最多 5 轮，超过则停下上报
```

---

## 第 1 步：生成并执行 pytest 命令

命令**不要手写**，用 `skill_utils/pytest_command.py` 的 `build_pytest_command()` 生成——
它会按配置切到工作目录（`paths.pytest_workdir`）并设好 `PYTHONPATH`（`pytest.pythonpath`）：

```python
from skill_utils.config_loader import load_config
from skill_utils.pytest_command import build_pytest_command

config = load_config()                                   # 或 load_config("<config.json 路径>")
cmd = build_pytest_command("<要跑的用例或目录>", config=config, shell="bash")   # 必须显式传 shell
```

> **`shell=` 必须显式传**（`"bash"` 或 `"powershell"`）。省略时 `build_pytest_command` 会调
> `detect_shell()` 去猜，而它依据的 `PSModulePath` 是 Windows 机器级环境变量（Git Bash 里也有），
> 会误判成 PowerShell、生成 `Set-Location` / `$env:` 语法，在真实 bash 会话里跑不起来。
> 你现在到底在哪个 shell 里，只有你自己知道。

先跑**失败的那一个用例**拿最小现场；范围不清时再全量跑，配 `--tb=short` 看清栈。

---

## 第 2 步：拿到失败 → 三分法判定

**必须先拿到失败输出再动手。** 拿到后按 `doc/maintenance_context.md` 的三分法分类：

| 现象 | 判断 | 怎么办 |
|---|---|---|
| 接口行为确实变了 / 后端有 BUG | **功能 BUG** | 报告用户，不擅自改用例 |
| 接口没变，是用例写法 / 数据过期了 | **用例待维护** | 继续第 3 步 |
| 看不出是哪一类 | **不明确** | 说明“不明确”，把失败原文交用户定夺；不许猜 |

**判断只依据“最后一次 pytest 的中断报错”**，不凭对业务或代码的印象。

---

## 第 3 步：按八级优先级定位根因

用 `doc/troubleshooting.md` 的排查优先级**从上往下**逐层查，别跳：

1. 导入路径（`ModuleNotFoundError` / `ImportError`）
2. 编码（中文乱码 / 解析失败）
3. 装饰器误挂 / 插入位置错误
4. fixture / 前置依赖
5. 登录态 / token / 会话
6. 断言与真实返回不匹配
7. payload 结构不匹配
8. 返回层级误判

顺序本身就是价值：越靠上的越基础，也越容易伪装成别的问题。第 6～8 层的问题常常是第 1～2 层
问题装出来的。

---

## 第 4 步：最小补丁 → 重跑

- 改**最小的一处**，别顺手重构。维护的目的是让测试回到绿，不是改造测试。
- 重跑**同一条命令**。循环**最多 5 轮**，超过就停下上报——“修不动”本身也是要报告的信息。
- 每一轮都留下证据：**执行命令、关键日志、最终结果**，三项缺一不可。

---

## 第 5 步：同步索引（接口本身变了才做）

如果维护中发现接口新增 / 改名 / 换方法（而不只是用例数据过期），跑
`tools/scan_api_methods.py` 更新索引，保持索引与代码一致。

---

## 完成前自检

- [ ] **真的跑过** pytest 并拿到了失败输出，不是凭描述猜的。
- [ ] 判过类别（功能 BUG / 用例待维护 / 不明确），判不了就如实说“不明确”。
- [ ] 命令由 `build_pytest_command()` 生成且**显式传了 `shell=`**。
- [ ] 修改是**最小补丁**，没有顺手重构。
- [ ] 给出了**执行命令 + 关键日志 + 最终结果**三项证据。
- [ ] 循环没有超过 5 轮；接口有变更时索引已同步。
