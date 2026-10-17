from pathlib import Path

from analyzers.java_spring import JavaSpringAnalyzer, parse_java_source

SAMPLE = '''
package com.ruoyi.wms.controller;

import org.springframework.web.bind.annotation.*;

/**
 * 库存盘点单据
 */
@Validated
@RestController
@RequestMapping("/wms/checkOrder")
public class CheckOrderController extends BaseController {

    /**
     * 查询库存盘点单据列表
     */
    @SaCheckPermission("wms:check:all")
    @GetMapping("/list")
    public TableDataInfo<CheckOrderVo> list(CheckOrderBo bo, PageQuery pageQuery) {
        return checkOrderService.queryPageList(bo, pageQuery);
    }

    /**
     * 导出库存盘点单据列表
     */
    @Log(title = "库存盘点单据", businessType = BusinessType.EXPORT)
    @PostMapping("/export")
    public void export(CheckOrderBo bo, HttpServletResponse response) {
        ExcelUtil.exportExcel(list, "库存盘点单据", CheckOrderVo.class, response);
    }

    @PostMapping({"add", "save"})
    public R<Void> add(@RequestBody CheckOrderBo bo) {
        return toAjax(checkOrderService.insertByBo(bo));
    }

    @RequestMapping(value = "/status", method = RequestMethod.PUT)
    public R<Void> changeStatus(@RequestBody CheckOrderBo bo) {
        return toAjax(checkOrderService.updateByBo(bo));
    }
}
'''


def test_parses_class_and_method_paths():
    endpoints = parse_java_source(SAMPLE, "CheckOrderController.java")

    paths = [(e.method, e.path) for e in endpoints]

    assert ("GET", "/wms/checkOrder/list") in paths
    assert ("POST", "/wms/checkOrder/export") in paths


def test_multi_path_annotation_takes_first():
    endpoints = parse_java_source(SAMPLE, "CheckOrderController.java")

    assert ("POST", "/wms/checkOrder/add") in [(e.method, e.path) for e in endpoints]
    assert not any(e.path.endswith("/save") for e in endpoints)


def test_request_mapping_with_method_attribute():
    endpoints = parse_java_source(SAMPLE, "CheckOrderController.java")

    assert ("PUT", "/wms/checkOrder/status") in [(e.method, e.path) for e in endpoints]


def test_handler_name_doc_and_line_number():
    endpoints = parse_java_source(SAMPLE, "CheckOrderController.java")
    by_path = {e.path: e for e in endpoints}

    listed = by_path["/wms/checkOrder/list"]
    assert listed.handler == "list"
    assert listed.doc == "查询库存盘点单据列表"
    assert listed.line_no > 0
    assert listed.file_path == "CheckOrderController.java"


def test_category_and_params():
    endpoints = parse_java_source(SAMPLE, "CheckOrderController.java")
    by_path = {e.path: e for e in endpoints}

    assert by_path["/wms/checkOrder/list"].category == "查询/初始化接口"
    assert by_path["/wms/checkOrder/add"].category == "写入/状态变更接口"
    assert any(p.get("kind") == "RequestBody" for p in by_path["/wms/checkOrder/add"].params)


def test_duplicate_same_path_keeps_both():
    source = '''
@RestController
@RequestMapping("/a")
public class TwoController {
    @PostMapping("/x")
    public R<Void> first() { return null; }

    @PostMapping("/x")
    public R<Void> second() { return null; }
}
'''
    endpoints = parse_java_source(source, "TwoController.java")

    handlers = sorted(e.handler for e in endpoints if e.path == "/a/x")
    assert handlers == ["first", "second"]


def test_detect_and_analyze(tmp_path):
    root = tmp_path / "proj"
    (root / "src" / "main" / "java" / "com" / "demo").mkdir(parents=True)
    (root / "src" / "main" / "java" / "com" / "demo" / "UserController.java").write_text(
        SAMPLE, encoding="utf-8"
    )

    analyzer = JavaSpringAnalyzer()

    assert analyzer.detect(root) is True
    endpoints = analyzer.analyze([root / "src" / "main" / "java"], {})
    assert len(endpoints) == 4


def test_apply_prefix_map_in_analyze(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "C.java").write_text(SAMPLE, encoding="utf-8")

    # 用一个**真的能命中**的映射：/wms → /api，否则这条断言恒真、测不到任何东西
    endpoints = JavaSpringAnalyzer().analyze([root / "src"], {"/wms": "/api"})

    paths = [(e.method, e.path) for e in endpoints]
    assert ("GET", "/api/checkOrder/list") in paths
    assert ("POST", "/api/checkOrder/export") in paths
    assert not any(p.startswith("/wms") for _, p in paths)


def test_detect_returns_false_without_controllers(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "Plain.java").write_text("public class Plain {}", encoding="utf-8")

    assert JavaSpringAnalyzer().detect(root) is False


WRAPPED_SIGNATURE_SAMPLE = '''
@RestController
@RequestMapping("/wms/checkOrder")
public class CheckOrderController {

    /**
     * 获取库存盘点单据详细信息
     *
     * @param id 主键
     */
    @GetMapping("/{id}")
    public R<CheckOrderVo> getInfo(@NotNull(message = "主键不能为空")
                                   @PathVariable Long id) {
        return R.ok(checkOrderService.queryById(id));
    }
}
'''


def test_javadoc_takes_first_meaningful_line():
    endpoints = parse_java_source(WRAPPED_SIGNATURE_SAMPLE, "CheckOrderController.java")

    assert endpoints[0].doc == "获取库存盘点单据详细信息"


def test_wrapped_signature_params_are_not_truncated():
    endpoints = parse_java_source(WRAPPED_SIGNATURE_SAMPLE, "CheckOrderController.java")
    params = endpoints[0].params

    assert len(params) == 1
    assert params[0]["kind"] == "普通参数"
    assert params[0]["name"] == "id"
    assert params[0]["type"] == "Long"


DOCUMENTED_THEN_UNDOCUMENTED = '''
@RestController
@RequestMapping("/api")
public class DemoController {

    /**
     * 删除条目
     */
    @DeleteMapping("/del")
    public R<Void> remove(Long id) {
        return null;
    }

    @PostMapping("/update/orderNum")
    public R<Void> updateOrderNum(Long id) {
        return null;
    }
}
'''


def test_undocumented_method_does_not_inherit_previous_javadoc():
    """没有 Javadoc 的方法必须拿到空描述——绝不允许继承上一条方法的注释。"""
    endpoints = parse_java_source(DOCUMENTED_THEN_UNDOCUMENTED, "DemoController.java")
    by_path = {e.path: e for e in endpoints}

    assert by_path["/api/del"].doc == "删除条目"
    assert by_path["/api/update/orderNum"].doc == ""
