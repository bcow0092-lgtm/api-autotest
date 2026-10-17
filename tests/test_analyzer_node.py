from pathlib import Path

from analyzers.node_web import NodeWebAnalyzer, parse_node_source

EXPRESS = '''
const express = require('express')
const router = express.Router()

router.get('/list', (req, res) => {
  res.json([])
})

router.post('/create', (req, res) => {
  res.json({ ok: true })
})

app.delete('/items/:id', (req, res) => {
  res.json({ ok: true })
})

module.exports = router
'''

NEST = '''
import { Controller, Get, Post, Param } from '@nestjs/common'

@Controller('users')
export class UsersController {
  @Get()
  findAll() {
    return []
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return {}
  }

  @Post()
  create() {
    return {}
  }
}
'''


def test_express_paths_and_methods():
    endpoints = parse_node_source(EXPRESS, "routes/items.js")

    assert [(e.method, e.path) for e in endpoints] == [
        ("GET", "/list"),
        ("POST", "/create"),
        ("DELETE", "/items/{id}"),
    ]


def test_express_handler_is_commented_out_or_empty():
    endpoints = parse_node_source(EXPRESS, "routes/items.js")

    assert endpoints[0].handler == ""


def test_nestjs_controller_prefix_and_methods():
    endpoints = parse_node_source(NEST, "users.controller.ts")

    assert [(e.method, e.path) for e in endpoints] == [
        ("GET", "/users"),
        ("GET", "/users/{id}"),
        ("POST", "/users"),
    ]


def test_nestjs_handler_names():
    endpoints = parse_node_source(NEST, "users.controller.ts")

    assert [e.handler for e in endpoints] == ["findAll", "findOne", "create"]


def test_detect_and_analyze(tmp_path):
    root = tmp_path / "proj"
    (root / "routes").mkdir(parents=True)
    (root / "routes" / "items.js").write_text(EXPRESS, encoding="utf-8")

    analyzer = NodeWebAnalyzer()

    assert analyzer.detect(root) is True
    assert len(analyzer.analyze([root], {})) == 3


def test_detect_returns_false_for_plain_js(tmp_path):
    root = tmp_path / "proj"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "util.js").write_text("module.exports = { add: (a, b) => a + b }\n", encoding="utf-8")

    assert NodeWebAnalyzer().detect(root) is False


def test_generic_get_calls_in_plain_js_are_not_endpoints(tmp_path):
    """`X.get("字面量")` 在普通 JS 里遍地都是（Map.get / cache.get / config.get），
    必须靠"文件里有没有 express"这道门禁挡住，否则会产出成片的假接口。"""
    source = "const cache = new Map()\ncache.get('user')\ncity.get('config', 'base')\n"

    assert parse_node_source(source, "cache.js") == []

    root = tmp_path / "proj"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "cache.js").write_text(source, encoding="utf-8")
    assert NodeWebAnalyzer().detect(root) is False


def test_express_router_prefix_is_not_inferred():
    """Express 的挂载前缀写在 app.use('/', router) 里，本版不跨文件推断——如实反映在文档里。"""
    endpoints = parse_node_source(EXPRESS, "routes/items.js")

    assert endpoints[0].path == "/list"


def test_express_file_with_incidental_single_arg_get_calls_stays_clean():
    """真实路由文件里 req.get / res.get / app.get / config.get 遍地都是，且都是单参调用；
    路由注册必然是"路径 + 处理函数"两个参数。"""
    source = '''
const express = require('express')
const router = express.Router()
const config = require('config')

router.get('/orders', (req, res) => {
  const token = req.get('Authorization')
  const env = app.get('env')
  const host = config.get('db.host')
  res.get('Content-Type')
  res.json({ token, env, host })
})
'''
    endpoints = parse_node_source(source, "routes/orders.js")

    assert [(e.method, e.path) for e in endpoints] == [("GET", "/orders")]


def test_single_arg_get_on_a_router_is_not_a_route():
    source = "const express = require('express')\nconst router = express.Router()\nrouter.get('/health')\n"

    assert parse_node_source(source, "r.js") == []


def test_express_router_with_options_binding_is_recognized():
    """`express.Router({ mergeParams: true })` 是常见写法，绑定的路由器上路由不能被漏报。"""
    source = (
        "const express = require('express')\n"
        "const api = express.Router({ mergeParams: true })\n"
        "api.get('/opt', h)\n"
    )

    endpoints = parse_node_source(source, "routes/opt.js")

    assert [(e.method, e.path) for e in endpoints] == [("GET", "/opt")]


def test_nest_multiple_controllers_are_skipped():
    source = '''
import { Controller, Get } from '@nestjs/common'

@Controller('a')
export class AController {
  @Get('x')
  ax() { return 1 }
}

@Controller('b')
export class BController {
  @Get('y')
  by() { return 2 }
}
'''
    assert parse_node_source(source, "two.controller.ts") == []


def test_detect_finds_express_in_a_typescript_project(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "routes.ts").write_text(
        "import express from 'express'\nconst router = express.Router()\nrouter.get('/a', handler)\n",
        encoding="utf-8",
    )

    assert NodeWebAnalyzer().detect(root) is True
