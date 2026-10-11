from skill_utils.api_path_match import (
    api_path_matches,
    normalize_path,
    to_pure_path,
)


def test_normalize_strips_scheme_host_query_fragment():
    assert normalize_path("https://x.com/a/b?c=1#d") == "/a/b"
    assert normalize_path("/a/b/") == "/a/b"
    assert normalize_path("a/b") == "/a/b"
    assert normalize_path("/a//b") == "/a/b"


def test_normalize_handles_placeholder_host():
    assert normalize_path("https://{self.base_url}/api/users/create") == "/api/users/create"


def test_to_pure_path_replaces_dynamic_segments():
    assert to_pure_path("/wms/warehouse/123/detail") == "/wms/warehouse/{param}/detail"
    assert to_pure_path("/wms/warehouse/{id}/detail") == "/wms/warehouse/{param}/detail"


def test_plain_word_segment_is_not_dynamic():
    # 防止把普通路径段误判成动态段（8 位以内的纯字母词不得被吞）
    assert to_pure_path("/api/orders/list") == "/api/orders/list"
    assert to_pure_path("/api/dead/beef") == "/api/dead/beef"


def test_api_path_matches_cross_segment_wildcard():
    pattern = "/api/inc/{1}data/cloudTitle/queryList"
    assert api_path_matches(pattern, "/api/inc/foo/data/cloudTitle/queryList") is True
    assert api_path_matches(pattern, "/api/inc/data/cloudTitle/queryList") is True
    assert api_path_matches(pattern, "/api/inc/foo/data/cloudTitle/queryList/extra") is False


def test_api_path_matches_requires_literal_segments_to_agree():
    assert api_path_matches("/api/{1}/list", "/api/orders/list") is True
    assert api_path_matches("/api/{1}/list", "/api/orders/detail") is False
