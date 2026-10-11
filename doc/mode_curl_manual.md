# 方式③：cURL 手工

**适用场景**：用户手上已经有一条**能跑通的请求**（通常是从浏览器开发者工具里 Copy as cURL 出来的），
你知道它返回什么，只想把它固化成一条可回归的测试。这是信息最完整的一种新增方式——
URL、方法、请求头、body、真实响应全都有了。

> 落点由 `.api-autotest/config.json` 的 `paths.api_method_dirs` / `paths.test_case_dirs` 决定。

---

## 步骤

### 1. 拆解 cURL

一条 cURL 大致长这样，逐段读出信息：

```bash
curl 'http://host:8080/api/user/create' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <token>' \
  --data-raw '{"name":"alice","roles":["viewer"]}'
```

- `http://host:8080/api/user/create` → **相对路径** `/api/user/create`，**方法** POST（`--data-raw` 或 `-X POST` 表示 POST；无 `-X` 且无 body 通常是 GET）
- `-H` 头 → 哪些是**通用**头（`Content-Type`、鉴权），哪些是**业务**头
- `--data-raw` / `-d` → 请求 body（JSON 或表单）

**把 host 摘掉**：测试里只用相对路径，域名由 fixture 的 base url 决定。

### 2. 判断鉴权怎么来

- 如果 cURL 里带了 `Authorization` / `Cookie`，那这条请求是**带登录态**的。
  测试里**不要**把这串 token 写死——改用项目统一的 `api_session` fixture（它负责登录）。
- 看不出鉴权方式 → 去读后端登录接口，按项目实际实现补 fixture，别猜。

### 3. 写接口方法

在接口方法层新增一个函数（命名、结构照 `doc/coding_style_guide.md`）：

```python
# -*- coding: utf-8 -*-
"""用户模块接口。"""

import requests


def create_user(session, payload: dict) -> requests.Response:
    """创建用户。"""
    url = "/api/user/create"
    return session.post(url, json=payload)
```

- 第一个参数 `session` 由用例层把登录好的 `api_session` 传进来（接口层不自己登录）。
- body 作为参数 `payload` 传入，**不要写死在函数里**（写死就没法参数化了）。
- 返回 `requests.Response` 本身，不在这里剥层。

### 4. 写用例

用 cURL 的真实响应来定断言。先跑一次拿实际返回：

```python
response = create_user(api_session, {"name": "alice", "roles": ["viewer"]})
print(response.status_code, response.text)     # 对齐 cURL 里看到的结构
```

确认层级后写精确断言（`status_code` / 业务 `code` / 关键字段），删掉 `print`。

### 5. 参数化（能省就省）

cURL 里那条是一组具体值。把变化的部分抽成 `@pytest.mark.parametrize`：

```python
@pytest.mark.parametrize("payload", [
    {"name": "alice", "roles": ["viewer"]},
    {"name": "bob", "roles": ["admin"]},
])
def test_create_user(api_session, payload):
    response = create_user(api_session, payload)
    assert response.status_code == 200
    assert response.json()["data"]["name"] == payload["name"]
```

### 6. 查重 + 跑闭环 + 更新索引

走查重链确认是新增；用 `build_pytest_command()` 生成命令（**显式传 `shell=`**）跑 pytest；
新增接口用 `tools/scan_api_methods.py` 补进索引。

---

## 常见坑

- **把 host 写死**：`http://localhost:8080/api/...` 换环境就废，必须只留相对路径。
- **抄了 cURL 的请求头**：`User-Agent`、`Referer`、`Origin` 这类头通常不需要，别一股脑搬进来。
- **token 写死**：`Authorization` 里的值会过期，必须走 fixture。
- **列表字段写成字符串**：cURL 的 JSON 里 `"roles":["viewer"]` 是列表，写用例时别退化成 `"viewer"`。
- **断言写反层级**：先看清 cURL 返回是 `{code,data}` 还是纯 `{data}`，再决定断哪一层。

---

## 完成前自检

- [ ] 路径是相对的，没有 host。
- [ ] 鉴权走 `api_session` fixture，没有写死 token。
- [ ] body 是参数，不是写死常量。
- [ ] 查重链跑过；pytest 闭环通过；索引已更新。
