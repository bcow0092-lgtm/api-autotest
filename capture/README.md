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
`capture/launch.py`，由它统一读配置、决定端口，所以改配置就能改实际监听端口。

> ⚠️ `capture/` 在 **skill 目录**里，脚本又**必须在项目根目录运行**（它从当前工作目录
> 向上找 `.api-autotest/config.json`）。所以别在项目根写 `python capture/launch.py`——
> 那里没有 `capture/`。正确做法：**工作目录留在项目根 + 脚本用绝对路径**
> （不要 `cd` 到 skill 目录，切走就读不到项目配置了）。

```
# 在**项目根目录**下执行；<skill> 换成 skill 安装目录
python "<skill>/capture/launch.py" start
```

端口优先级（`launch.py` 的 `resolve_port`）：

1. 环境变量 `CAPTURE_PORT`（临时覆盖用）；
2. 配置里的 `capture.listen_port`；
3. 默认 `12138`。

配置读不到时回落默认端口并打印告警，不会崩。

```
set CAPTURE_PORT=8899
C:\Users\<你>\.claude\skills\api-autotest\capture\start.bat
```

> 配置沿**当前工作目录**向上查找 `.api-autotest/config.json`，所以请在**项目根目录**
> 执行脚本，否则会落到默认端口并告警。

## 启停

| 脚本（位于本目录） | 作用 |
| --- | --- |
| `start.bat` | 前台运行 `mitmdump -s capture_addon.py --listen-port <端口>`（`.bat` 用 `%~dp0` 自定位脚本、**不切目录**） |
| `stop.bat` | 按端口查 `netstat` 找到监听进程并 `taskkill /F` |
| `restart.bat` | 先 stop 再 start |

等价的手工命令（在**项目根目录**下、用**绝对路径**调用；勿用相对路径）：

```
python "<skill>/capture/launch.py" start
python "<skill>/capture/launch.py" stop
python "<skill>/capture/launch.py" restart
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
- `login_path_hints`：命中即视为登录/登出请求，**这类请求根本不会落进 JSONL**（在
  `should_capture` 阶段就被拦掉）；它的用途是过滤登录噪声，而非“记下来再打标记”
  （因此落盘记录里 `is_login` 恒为 false）。
- 静态资源后缀（`.js` / `.css` / `.png` 等）始终跳过。
