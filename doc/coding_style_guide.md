# 编码规范

编写接口方法与用例前**必读**。目标是让本项目里所有测试文件长得一样，任何人接手都能一眼看懂。

> 具体落到哪个目录、哪个文件，由 `.api-autotest/config.json` 的 `paths.api_method_dirs` 与
> `paths.test_case_dirs` 决定。下面的“接口方法层”“用例层”指的就是这两处。

---

## 一、接口方法层：一段接口调用封装成一个函数

接口方法层负责“把一次 HTTP 调用写成可复用的函数”，不写断言。

### 文件结构

```python
# -*- coding: utf-8 -*-
"""用户模块接口。"""

import requests


def create_user(session, payload: dict) -> requests.Response:
    """创建用户。

    Desc: 创建用户
    """
    url = "/api/user/create"
    return session.post(url, json=payload)
```

- 文件头写 `# -*- coding: utf-8 -*-` 与模块 docstring。
- 一个接口一个函数，函数名用**动词 + 名词**的小写下划线写法（`create_user` / `query_order_list` / `update_profile`）。
- 第一个参数 `session` 是 `requests.Session`，**由用例层把登录好的 `api_session` fixture 传进来**。
  接口方法自己不登录、不持有全局会话——登录态只在用例层注入，接口层保持无状态、可复用。
- URL 用**赋值给变量**的写法（`url = "/api/..."`）。扫描器 `tools/scan_api_methods.py` 的内置规则
  能识别 `url = ...` 以及 `requests.get(...)` 直接内联两种写法；把 URL 抽成变量可读性更好，也让扫描更稳。
- 路径只写**相对路径**（`/api/user/create`），不要写死 `http://host:port`——域名由 fixture 里的 base url 决定。

### payload 组织

- payload 作为函数参数传入（`payload: dict`），**不要在函数体里拼死数据**，否则用例没法参数化。
- 参数默认值给“最小可用值”。列表类字段一律用列表（`"roles": ["viewer"]`），不要图省事传字符串。
- 需要多段路径参数时用 f-string：`url = f"/api/user/{user_id}"`。

### 返回层级处理

- 接口方法**直接返回 `requests.Response`**，不在这里 `.json()`、不在这里取 `data`。
  “返回第几层”是用例层要知道的事，接口层擅自剥层会让用例失去原始信息。
- 需要看真实返回结构时：先写基础断言把请求跑通，打印 `response.text` 看清层级，再在用例层决定取哪一层。
  切忌凭猜写 `response.json()["data"]["list"]`。

### 方法命名清单

| 动作 | 前缀 | 例 |
|---|---|---|
| 新增 | `create_` / `add_` | `create_user` |
| 查询单条 | `get_` / `query_` | `get_user_detail` |
| 查询列表 | `list_` / `query_..._list` | `query_order_list` |
| 更新 | `update_` | `update_profile` |
| 删除 | `delete_` / `remove_` | `delete_user` |

命名要能扫一眼看出“对什么资源做什么动作”，不要出现 `test1` / `do_api` 这类名字。

---

## 二、用例层：一个用例验证一个行为

用例层调用接口方法，负责组装数据、发请求、做断言。

### 文件结构

```python
# -*- coding: utf-8 -*-
"""用户模块用例。"""

import pytest

from <接口方法层模块> import create_user, get_user_detail   # 模块路径以项目实际布局为准


@pytest.mark.parametrize("payload", [
    {"name": "alice", "roles": ["viewer"]},
    {"name": "bob", "roles": ["admin"]},
])
def test_create_user(api_session, payload):
    """创建用户后可按名称查到。"""
    response = create_user(api_session, payload)

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["name"] == payload["name"]
```

- 文件头同样写编码声明与模块 docstring。
- **用例函数名以 `test_` 开头**，后面跟“被测行为”，用英文小写下划线（`test_create_user`）。
- 函数 docstring 用一句中文说清“这个用例保证什么”。
- 登录态通过 fixture 拿（如 `api_session`），**不要在用例里手工登一次**。
  骨架 `conftest.py` 里给了带 `TODO` 的 fixture 模板——鉴权方式因项目而异（Sa-Token / JWT / Basic 等），
  由你读后端登录接口后按项目实际补全，不要照抄示例。

### 参数化写法

- 用 `@pytest.mark.parametrize`，第一参数是参数名，第二参数是**用例数据列表**。
- 数据多时抽到模块顶部常量或独立数据文件，不要在装饰器里堆一大坨。
- 给参数化用例配 `ids=`，让 pytest 输出里每一行都有人能看懂的名字：

```python
@pytest.mark.parametrize("payload", CREATE_CASES, ids=[c["name"] for c in CREATE_CASES])
```

### 断言风格

- 断言要**具体、能失败**：断言状态码、业务码、关键字段值，而不是 `assert response`。
- 分层断言，失败时能立刻定位：
  1. `assert response.status_code == 200`
  2. `assert body["code"] == 0`
  3. `assert body["data"][...] == 期望值`
- **禁止**永真断言（`assert x or True`）、**禁止**用 `try/except` 吞异常、**禁止**用 `pytest.skip` 绕过失败。
- 两阶段断言：先跑通拿真实返回，再补精确断言，最后删掉调试 `print`。

---

## 三、编写前必检清单

动手写之前，逐项确认：

- [ ] **风格对齐** —— 读过接口方法层和用例层里已有的同模块文件，本次新增的命名、文件组织、断言层级跟它们一致。
- [ ] **接口查重** —— 走完查重链（`normalize_path` → `to_pure_path` → `find_by_path_method` → grep 路径片段），确认要写的接口与用例**在索引和代码里都不存在**。
- [ ] **编码校验** —— 文件写为 **UTF-8 无 BOM、换行 `\n`**；写完用 `read_text_utf8()` 或重新 Read 确认中文正常显示，没有乱码（替换字符或成串问号）。
- [ ] **落点确认** —— 文件放在配置声明的 `paths.api_method_dirs` / `paths.test_case_dirs` 里，不是随手新建一个目录。
- [ ] **登录态来源** —— 用例用的是项目既有的 `api_session` fixture，不是自己临时 `requests.post("/login")`。
