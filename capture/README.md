# capture —— 抓包驱动（方式①）

用 mitmproxy 把真实 HTTP 请求录成 JSONL，供 `tools/match_captures.py` 与接口索引比对。

## 依赖

```
pip install mitmproxy
```

`mitmdump` 需要能在 PATH 上找到。

## 端口

监听端口取自项目配置 `config.capture.listen_port`（即
`<project>/.api-autotest/config.json` 的 `capture.listen_port`）。
可用环境变量 `CAPTURE_PORT` 临时覆盖：

```
set CAPTURE_PORT=8899
start.bat
```

## 启停

| 脚本 | 作用 |
| --- | --- |
| `start.bat` | 前台启动 `mitmdump -s capture_addon.py --listen-port <端口>` |
| `stop.bat` | 按端口查 `netstat` 找到监听进程并 `taskkill /F` |
| `restart.bat` | 先 stop 再 start |

等价的手工命令：

```
mitmdump -s capture_addon.py --listen-port <config.capture.listen_port>
```

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
