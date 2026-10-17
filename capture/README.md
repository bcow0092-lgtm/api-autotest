# capture —— 抓包驱动（方式①）

用 mitmproxy 把真实 HTTP 请求录成 JSONL，供 `tools/match_captures.py` 与接口索引比对。

## 依赖

```
pip install mitmproxy
```

`mitmdump` 需要能在 PATH 上找到。

## 端口

监听端口**来自项目配置** `config.capture.listen_port`（即
`<project>/.api-autotest/config.json` 的 `capture.listen_port`）。三个启停脚本都委派给
`capture/launch.py`，由它统一读配置、决定端口，所以改配置就能改实际监听端口：

```
python capture/launch.py start
```

端口优先级（`launch.py` 的 `resolve_port`）：

1. 环境变量 `CAPTURE_PORT`（临时覆盖用）；
2. 配置里的 `capture.listen_port`；
3. 默认 `12138`。

配置读不到时回落默认端口并打印告警，不会崩。

```
set CAPTURE_PORT=8899
start.bat
```

> 配置沿**当前工作目录**向上查找 `.api-autotest/config.json`，所以请在**项目根目录**
> 执行脚本（或先 `cd` 到项目根），否则会落到默认端口并告警。

## 启停

| 脚本 | 作用 |
| --- | --- |
| `start.bat` | 前台运行 `python launch.py start`（即 `mitmdump -s capture_addon.py --listen-port <端口>`） |
| `stop.bat` | 运行 `python launch.py stop`：按端口查 `netstat` 找到监听进程并 `taskkill /F` |
| `restart.bat` | 运行 `python launch.py restart`：先 stop 再 start |

等价的手工命令：

```
python capture/launch.py start
python capture/launch.py stop
python capture/launch.py restart
```

底层仍是 `mitmdump -s capture_addon.py --listen-port <config.capture.listen_port>`。

## 产物

记录落在 `config.paths.runtime_temp_dir/latest.jsonl`，每行一条 JSON。

## 记录内容与脱敏

- 敏感头（`Cookie` / `Authorization`）只存**摘要**：前 20 字符 + `|len=<总长>`，
  不落原始值。
- **二进制响应**（`image/*`、`video/*`、`audio/*`、`application/pdf`、各种
  `application/*zip` 等）不落 body，仅写 `<BINARY_SKIPPED ...>`。
- **超大文本响应**（超过 1 MiB）截断到 1 MiB，置 `body_truncated=true`。
- 疑似大块编码数据（base64 / 十六进制，超过 2 KiB）判定为 `encoded-blob`，
  跳过 body。

## 过滤规则（全部来自配置，无硬编码）

`capture` 节可配：

- `baseurl`：只记录该 host 的请求；
- `include_prefixes` / `exclude_prefixes`：路径前缀白/黑名单；
- `login_path_hints`：命中即视为登录请求，默认不记录（记录里 `is_login=true`）。
- 静态资源后缀（`.js` / `.css` / `.png` 等）始终跳过。
