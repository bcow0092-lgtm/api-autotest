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
