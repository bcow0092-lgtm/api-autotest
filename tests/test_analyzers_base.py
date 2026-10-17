from analyzers.base import (
    ApiEndpoint,
    apply_prefix_map,
    classify_endpoint,
    first_string_arg,
    join_url_paths,
)


def test_api_endpoint_required_and_optional_fields():
    endpoint = ApiEndpoint(method="GET", path="/a", handler="list", file_path="A.java", line_no=10)

    assert endpoint.method == "GET"
    assert endpoint.doc == ""
    assert endpoint.params == []
    assert endpoint.category == ""
    assert endpoint.extra == {}


def test_join_url_paths():
    assert join_url_paths("/wms/checkOrder", "/list") == "/wms/checkOrder/list"
    assert join_url_paths("/wms/checkOrder/", "list") == "/wms/checkOrder/list"
    assert join_url_paths("", "/list") == "/list"
    assert join_url_paths("/wms/checkOrder", "") == "/wms/checkOrder"
    assert join_url_paths("/a//b", "//c") == "/a/b/c"


def test_apply_prefix_map_strips_matching_prefix():
    assert apply_prefix_map("/dev-api/wms/list", {"/dev-api": ""}) == "/wms/list"
    assert apply_prefix_map("/dev-api/wms/list", {"/dev-api": "/api"}) == "/api/wms/list"
    assert apply_prefix_map("/wms/list", {"/dev-api": ""}) == "/wms/list"


def test_apply_prefix_map_respects_segment_boundary():
    """前缀匹配必须落在路径段边界上：`/dev-api` 不能命中 `/dev-api-v2/list`。"""
    assert apply_prefix_map("/dev-api-v2/list", {"/dev-api": ""}) == "/dev-api-v2/list"
    assert apply_prefix_map("/dev-api/wms/list", {"/dev-api": ""}) == "/wms/list"
    assert apply_prefix_map("/dev-api", {"/dev-api": ""}) == "/"


def test_annotation_args():
    from analyzers.base import annotation_args

    assert annotation_args('@GetMapping("/list")') == '"/list"'
    assert annotation_args("@GetMapping") == ""
    assert annotation_args('@RequestMapping(value = "/x", method = RequestMethod.POST)') == (
        'value = "/x", method = RequestMethod.POST'
    )


def test_first_string_arg():
    assert first_string_arg('"/list"') == "/list"
    assert first_string_arg('value = "/x", method = RequestMethod.POST') == "/x"
    assert first_string_arg("{ \"/a\", \"/b\" }") == "/a"
    assert first_string_arg("") == ""


def test_classify_endpoint():
    assert classify_endpoint("GET", "list", "/wms/list", []) == "查询/初始化接口"
    assert classify_endpoint("POST", "createOrder", "/wms/order", []) == "写入/状态变更接口"
    assert classify_endpoint("POST", "upload", "/wms/file", []) == "特殊参数接口"
    assert classify_endpoint("POST", "foo", "/wms/foo", [{"kind": "HttpServletRequest"}]) == "特殊参数接口"
    assert classify_endpoint("POST", "bar", "/wms/bar", []) == "独立业务接口"
