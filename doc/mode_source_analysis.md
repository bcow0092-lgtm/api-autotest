# 方式④：源码分析

> **路径约定**：本文档里出现的 `tools/`、`capture/`、`analyzers/`、`doc/` 一律指
> **本 skill 安装目录**下的子目录（默认 `~/.claude/skills/api-autotest/`），
> **不是被测项目里的同名目录**。照抄执行时，请把脚本路径换成 skill 目录下的**绝对路径**
> （`.bat` 已用 `%~dp0` 自定位，可直接用）；而**工作目录**通常要落在被测项目的根，
> 因为配置 `.api-autotest/config.json` 是按 CWD 向上查找的。

**适用场景**：有**后端源码**，想成批导出接口，而不是一条条手抄。适合接一个新项目、
或对某个模块做全面覆盖时先摸清“这个服务到底有哪些接口”。

> 分析根目录与语言由 `.api-autotest/config.json` 的 `source_analysis` 节声明（不是由 skill 安装位置推导）。
> 分析产物落到该配置的 `paths.runtime_temp_dir` 下。

---

## 支持的框架

| 语言 | 框架 | 识别依据 |
|---|---|---|
| Java | Spring | `@RestController` / `@Controller` 类 + `@RequestMapping` / `@GetMapping` / `@PostMapping` / `@PutMapping` / `@DeleteMapping` / `@PatchMapping` |
| Python | FastAPI / Flask / Django | `@router.get(...)` / `@app.route(..., methods=[...])` / `urlpatterns = [path(...)]` |
| Node | Express / NestJS | `router.get('/x', ...)` / `@Controller('users')` + `@Get()` |

分析器都在 `analyzers/` 目录里，共享同一套接口（`analyzers/base.py` 的 `ApiEndpoint` 数据类和
`BaseAnalyzer` 协议）：`JavaSpringAnalyzer`（`analyzers/java_spring.py`）、
`PythonWebAnalyzer`（`analyzers/python_web.py`）、`NodeWebAnalyzer`（`analyzers/node_web.py`）。

---

## 配置

`source_analysis` 节（见 `config.example.json`）：

- `language`：`java` / `python` / `node` / `auto`（默认 `auto`，逐个分析器试 `detect()`）。
- `roots`：要扫描的目录，相对 `project_root` 解析（如 `src/main/java`）。**目录必须存在**，
  否则直接报错退出——避免配错目录后静默扫出 0 个接口、写出一份“看着合法”的空草稿。
- `url_prefix_map`（可选）：把前端代理前缀映射回后端真实前缀，如 `{"/dev-api": ""}`
  会把 `/dev-api/wms/list` 还原成 `/wms/list`。

---

## 命令

```
python tools/analyze_source.py                    # 按 config.source_analysis 跑
python tools/analyze_source.py --language java    # 覆盖配置里的语言
python tools/analyze_source.py --dry-run          # 只报数，不写草稿
python tools/analyze_source.py --out <路径>        # 草稿写到指定路径
python tools/analyze_source.py --config <配置>     # 显式指定配置（省略则按 CWD 向上探测）
```

成功时打印一行汇总：

```
[analyze_source] analyzer=java endpoints=<接口数> uncovered=<未覆盖数> draft=<草稿路径>
```

`endpoints=0` 会额外在 stderr 告警，提示检查 `source_analysis.roots` 是否指向真正的后端源码目录。

---

## 产物：草稿，不是待办清单

默认写到 `config.paths.runtime_temp_dir/source_analysis_result.md`。草稿把接口分成两区：

- **一、未覆盖接口候选（默认勾选）**：索引里查不到 `(pure_path, method)` 的。
- **二、已覆盖接口（默认不勾选）**：索引里已有的。

“是否已覆盖”以接口索引的 `(pure_path, method)` 为准（`skill_utils/api_index_db.py` 的
`list_records()` 读索引，调度器里的 `cross_check()` 负责比对）；**索引为空时全部算新**。

### ⚠️ 草稿门禁（硬停）

**草稿只是一份候选清单，不是你要写的用例列表。** 必须把它摆给用户，让用户自己勾选哪些接口
这次要写，**等用户回“已勾选”之后才继续编写接口方法与用例**。这是主流程第 4 步的草稿门禁——
**抓包与源码分析这两种方式产出的才是“待用户勾选的清单”**；cURL 与参考已有用例没有这一步，
但它们同样要遵守新增门禁的落点 / 方式 / 范围确认。

---

## 已知限制（如实记录，别假装能做到）

- **Express 的挂载前缀本版不推断**：`app.use('/api', router)` 这种前缀写在**别的文件**里，
  跨文件推断不在本版范围内——分析器只取路由文件内写的路径。所以 Express 工程导出的路径
  可能缺少外层挂载前缀，需要你结合 `url_prefix_map` 或手工补全。
- **Django 路由没有 HTTP 方法**：`path("users/", view)` 本身不含方法信息，一律记为 `ANY`；
  并且**只有包含 `urlpatterns` 的文件**才会被解析。Django 工程导出的 `ANY` 接口需要你按实际
  实现补齐真正的方法再写用例。
- **Express 接收者判据较严**：只有当 `.get()` / `.post()` 的接收者是
  `express.Router(...)` / `express()` 绑定出来的名字，或惯用名 `router` / `app` 时才识别
  （**带 options 的 `express.Router({ mergeParams: true })` 也已识别**）——非路由器对象上的
  同名调用一律不报，宁可漏，不错报。
- **NestJS 一个文件多个 `@Controller` 时整份跳过**：无法把路由准确归属到各自前缀，宁可漏报
  也不产出错路径（Nest 惯例是一文件一控制器，正常项目不受影响）。
- **Python 分析器没有接收者门禁**：它按 `@<对象>.<动词>('路径')` 的**装饰器形态**识别路由，
  **不校验接收者是不是真的路由器对象**。因此一个恰好长成这个形状的非路由装饰器会被误报成
  接口。（Node 分析器有接收者白名单门禁，两者在此**不对称**。）这是**误报方向**，与上面几条
  相反；之所以不加门禁，是因为"绑定自 `APIRouter` 的名字"与"裸 `api = APIRouter()`（无 prefix，
  现有 `_ROUTER_PREFIX` 抓不到）"很难区分，加门禁容易把合法的 FastAPI 写法误伤成漏报——
  用一个小概率的误报换一个更常见的漏报，不划算。

上面除 Python 那条外都是**漏报方向**（少报接口，不会造出不存在的接口）；Python 那条是**误报
方向**（可能多报一个假接口）——两者都如实记录，不假装覆盖全。

---

## 常见坑

- **`source_analysis.roots` 写错**：指向不存在的目录会直接报错；指到没有接口代码的目录会扫出 0 条并告警。
- **把草稿当待办**：草稿是候选，必须经用户勾选。跳过门禁直接写一堆用例 = 违反主流程。
- **前缀映射遗漏**：前端请求走 `/dev-api` 之类的代理前缀时，用 `url_prefix_map` 还原，否则路径对不上索引。

---

## 完成前自检

- [ ] 分析根目录与语言确实来自 `config.source_analysis`（没有硬编码）。
- [ ] 草稿已给用户看过，并等到了“已勾选”的确认。
- [ ] 勾选的接口按 `doc/coding_style_guide.md` 写成接口方法与用例。
- [ ] 走 pytest 闭环，命令由 `build_pytest_command()` 生成（**显式传 `shell=`**）。
- [ ] 新接口用 `tools/scan_api_methods.py` 补进索引。
