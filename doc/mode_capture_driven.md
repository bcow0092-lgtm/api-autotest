# 方式①：抓包驱动

> **路径约定**：本文档里出现的 `tools/`、`capture/`、`analyzers/`、`doc/` 一律指
> **本 skill 安装目录**下的子目录（默认 `~/.claude/skills/api-autotest/`），
> **不是被测项目里的同名目录**。照抄执行时，请把脚本路径换成 skill 目录下的**绝对路径**
> （`.bat` 已用 `%~dp0` 自定位，可直接用）；而**工作目录**通常要落在被测项目的根，
> 因为配置 `.api-autotest/config.json` 是按 CWD 向上查找的。

**适用场景**：**黑盒**——没有接口文档、拿不到源码，只能看真实请求。让你先正常操作被测系统，
把流经代理的真实 HTTP 请求录下来，再从流量里挑出接口写成用例。这是信息最贴近真实的一种方式。

> 端口、被测服务地址、过滤规则全部来自项目配置 `<project>/.api-autotest/config.json` 的
> `capture` 节，没有硬编码。抓包产物落到该配置的 `paths.runtime_temp_dir` 下。

---

## 依赖：mitmproxy

抓包依赖 **mitmproxy**（提供 `mitmdump` 命令）。**安装请按 mitmproxy 官方文档来**——
它和 Python 版本、操作系统强相关，不是一句 `pip install mitmproxy` 就能保证装好、装对的
（版本不匹配会在导入或运行时才暴露）。装好后确认 `mitmdump` 在 `PATH` 上：

```
mitmdump --version
```

（本机开发环境当前装的是 mitmproxy 12.2.3，仅供参考，不代表任何项目直接可用。）

---

## 启动抓包服务

三个批处理脚本都委派给 `capture/launch.py`，由它统一读配置、决定端口：

| 脚本（位于 skill 目录 `capture/` 下） | 作用 |
|---|---|
| `start.bat` | 前台运行 `mitmdump -s capture_addon.py --listen-port <端口>` |
| `stop.bat` | 按端口查监听进程并杀掉 |
| `restart.bat` | 先 stop 再 start |

> ⚠️ **两个前提别踩反**：`capture/` 在 **skill 目录**里，不在你的项目里；而脚本又**必须
> 在项目根目录运行**（它从当前工作目录向上找 `.api-autotest/config.json`）。所以
> `python capture/launch.py start` 这种**相对路径写法在你项目根下必然失败**——你的项目根下
> 没有 `capture/` 这个目录。正确姿势是：**工作目录留在项目根 + 脚本用绝对路径**。
> 不要 `cd` 到 skill 目录，切走就读不到项目配置了。

在**你的项目根目录**下，用绝对路径执行（bash；`<skill>` 换成 skill 安装目录）：

```bash
python "<skill>/capture/launch.py" start
python "<skill>/capture/launch.py" stop
python "<skill>/capture/launch.py" restart
```

Windows 上也可直接调用批处理（`.bat` 用 `%~dp0` 自定位脚本、**不切目录**，在项目根跑正好）：

```bat
:: 在**你的项目根目录**下执行
C:\Users\<你>\.claude\skills\api-autotest\capture\start.bat
```

> 一定要在项目根启动，否则按 CWD 向上找不到 `.api-autotest/config.json`，会回落默认端口并打印告警。

### 端口

监听端口**来自配置** `capture.listen_port`。优先级（`capture/launch.py` 的 `resolve_port`）：

1. 环境变量 `CAPTURE_PORT`（临时覆盖用）；
2. 配置里的 `capture.listen_port`；
3. 默认 `12138`。

所以临时换端口不用改配置，用环境变量即可（仍在**项目根目录**下、脚本用绝对路径）：

```bat
set CAPTURE_PORT=8899
C:\Users\<你>\.claude\skills\api-autotest\capture\start.bat
```

### 检查服务是否在跑

用 `tools/check_capture_server.py`（默认检查 `127.0.0.1`）：

```
python tools/check_capture_server.py --config <项目根>/.api-autotest/config.json
```

退出码语义（**区分清楚，别想当然**）：

| 退出码 | 含义 |
|---|---|
| `0` | 服务在运行（监听进程的可执行名含 `mitm` 或 `python`） |
| `1` | 服务没在运行（端口无监听） |
| `2` | **端口被占**（被别的进程监听），**或**显式指定的配置文件非法 |

`2` 是**两种原因共用**的：想区分到底是被占还是配置非法，**要看输出**——配置非法会把
`ERROR: ...` 打到 **stderr**，端口被占会把 `PORT_OCCUPIED pid=... exe=...` 打到 **stdout**。
不要把它当成“2 只表示端口被占”。
（只有**显式传了 `--config`** 且配置非法才返回 `2`；不传 `--config` 时配置读不到会回落默认端口，不报错。）

---

## 配置项（`capture` 节，均无硬编码）

- `baseurl`：只记录该 host 的请求（留空 = 不过滤 host）。
- `include_prefixes`：只记录路径命中这些前缀的请求（白名单）。
- `exclude_prefixes`：排除路径命中这些前缀的请求（黑名单）。
- `login_path_hints`：命中即视为登录/登出请求，**这类请求根本不会落进 JSONL**——
  在 `should_capture` 阶段就被拦掉。它的用途是过滤登录噪声，而不是“记下来再打标记”
  （因此落盘记录里的 `is_login` 恒为 false）。
- `session_cookie_names`：会话 cookie 名。**本版仅解析保留**——addon 目前尚未用它做任何
  过滤或标记，配了不影响行为（声明出来是给后续版本用的）。

静态资源后缀（`.js` / `.css` / `.png` 等）始终跳过。

---

## 产物与比对

记录落在 `config.paths.runtime_temp_dir/latest.jsonl`，每行一条 JSON。把它与接口索引比对，
生成勾选草稿：

```
python tools/match_captures.py                       # 用配置里的路径
python tools/match_captures.py --jsonl <路径>         # 指定抓包文件
python tools/match_captures.py --out <路径>           # 指定草稿输出
python tools/match_captures.py --config <配置>
```

产物 `config.paths.runtime_temp_dir/capture_selection.md`，分四类：

- **新接口（推荐勾选）**：索引里查不到 `(pure_path, method)` 的。
- **已实现接口（如需重跑请手动勾选）**。
- **特殊处理接口**：二进制 / 文件响应，需手工处理。
- **已自动忽略的登录/登出接口**。

抓包条目会先按 `(method, pure_path)` 去重（保留最后一条）。索引为空时会告警，并把所有抓到的
接口都当作新接口。

### ⚠️ 草稿门禁（硬停）

**`capture_selection.md` 是草稿，不是待办清单。** 把它摆给用户，让用户勾选这次要写的接口，
**等用户回“已勾选”之后才继续编写用例**。这是主流程第 4 步的草稿门禁。

---

## 脱敏（addon 已内置）

- **敏感头**（`Cookie` / `Authorization`）只存**摘要**：前 20 字符 + `|len=<总长>`，不落原始值。
- **二进制响应**（`image/*` / `video/*` / `audio/*` / `application/pdf` / 各种 `application/*zip` 等）
  不落 body，仅写 `<BINARY_SKIPPED ...>`。
- **超大文本响应**（超过 1 MiB）截断到 1 MiB，置 `body_truncated=true`。
- 疑似大块编码数据（base64 / 十六进制，超过 2 KiB）判定为 `encoded-blob`，跳过 body。

---

## 验收状态与边界（诚实声明）

抓包链路（addon 录制、启停脚本、服务状态检查、比对生成草稿）已实现并通过单元测试，
**并做过一次最小的真实端到端验收**：本地起一个 `python -m http.server` 当被测系统，
按项目配置启动 mitmdump，用 `curl -x` 经代理发一条真实请求（`GET /wms/probe`），
addon 把请求如实落盘到 `latest.jsonl`（`method=GET`、`pure_path=/wms/probe`、`status=404`），
再用 `match_captures.py` 读出并生成 `capture_selection.md` 勾选草稿——即“启动抓包 → 真实请求
→ 录 JSONL → 比对成草稿”这条链路已跑通。

**验收边界**：这是**被测系统本地化**（`http.server`）的一次最小端到端验证，**不是**在一个
生产级真实项目上、对着真实前端操作跑过的完整验收；“启动抓包 → 用户在真实前端操作 → 大批量
录制 → 勾选”这一更大规模、更贴近实战的路径仍待验证。第一次在真项目上用，遇到问题按
`doc/troubleshooting.md` 排查并如实反馈。

---

## 常见坑

- **在错误的目录启动**：不在项目根启动会找不到配置，落到默认端口且只告警——抓到的数据可能进错地方。
- **`baseurl` 没配**：会把所有 host 的请求都录进来（其他站点的噪声也混入），建议配好只抓目标服务。
- **把草稿当待办**：必须经用户勾选，跳过门禁直接写用例违反主流程。
- **依赖当已装好**：mitmproxy 版本不匹配会在运行期才炸，务必先 `mitmdump --version` 确认。

---

## 完成前自检

- [ ] `mitmdump` 在 PATH 上，抓包服务确实起来了（`check_capture_server.py` 返回 0）。
- [ ] 端口来自 `capture.listen_port`（或 `CAPTURE_PORT`），没有写死。
- [ ] 草稿已给用户看过，并等到了“已勾选”的确认。
- [ ] 勾选的接口按 `doc/coding_style_guide.md` 写成接口方法与用例。
- [ ] 走 pytest 闭环，命令由 `build_pytest_command()` 生成（**显式传 `shell=`**）。
- [ ] 新接口用 `tools/scan_api_methods.py` 补进索引。
