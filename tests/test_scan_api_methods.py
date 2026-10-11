import json

import tools.scan_api_methods as scan_api_methods
from skill_utils import config_loader


def test_parse_file_extracts_url_method_and_metadata(tmp_path):
    sample = tmp_path / "sample_api.py"
    sample.write_text(
        '''
class EsbApi:
    def action_getLightActionFLowList(self, ETEAMSID, **kwargs):
        """
        esb中心-动作流-新建动作流-根据模块id获取动作流模板
        :param ETEAMSID:
        :return:
        """
        # Author: liuxin
        # Create Date: 2025-08-13
        url = 'https://{0}/api/bs/esb/setting/flow/design/getLightActionFLowList'.format(self.base_url)
        response = requests.request("GET", url)
        return response.json()
'''.strip(),
        encoding="utf-8",
    )

    records = scan_api_methods._parse_file(str(sample))

    assert len(records) == 1
    assert records[0]["pure_path"] == "/api/bs/esb/setting/flow/design/getLightActionFLowList"
    assert records[0]["api_desc"] == "esb中心-动作流-新建动作流-根据模块id获取动作流模板"
    assert records[0]["author"] == "liuxin"
    assert records[0]["create_date"] == "2025-08-13"
    assert records[0]["http_method"] == "GET"


def test_parse_file_strips_desc_prefix_and_reads_def_name(tmp_path):
    sample = tmp_path / "sample_api.py"
    sample.write_text(
        '''
class DwApi:
    def getDatasetAndDataGroupsByGroupIdAndPage_dataDevelopmentGroup(self, ETEAMSID):
        """
        desc: 数据开发-查询所有数据开发数据集 以及文件夹-不分页
        entrace: 数据开发->分组点击查询
        """
        # Author: qiumingwu
        # Create Date: 2023-09-19
        url = f'https://{self.base_url}/api/dw/dataDevelopmentGroup/getDatasetAndDataGroupsByGroupIdAndPage'
        response = requests.request("POST", url)
        return response.json()
'''.strip(),
        encoding="utf-8",
    )

    records = scan_api_methods._parse_file(str(sample))

    assert records[0]["pure_path"] == "/api/dw/dataDevelopmentGroup/getDatasetAndDataGroupsByGroupIdAndPage"
    assert records[0]["api_desc"] == "数据开发-查询所有数据开发数据集 以及文件夹-不分页"
    assert records[0]["api_name"] == "getDatasetAndDataGroupsByGroupIdAndPage_dataDevelopmentGroup"
    assert records[0]["http_method"] == "POST"


def test_parse_file_supports_self_http_shortcut(tmp_path):
    sample = tmp_path / "gbif_api.py"
    sample.write_text(
        '''
class GbifAPI:
    def species_search(self, status_code=200, **kwargs):
        """按关键词搜索物种"""
        # Create Date: 2026-06-10
        url = "/api/species/search"
        payload = {}
        payload.update(kwargs)
        return self.get(url, status_code=status_code, params=payload)
'''.strip(),
        encoding="utf-8",
    )

    records = scan_api_methods._parse_file(str(sample))

    assert len(records) == 1
    assert records[0]["api_url"] == "/api/species/search"
    assert records[0]["http_method"] == "GET"


def test_parse_file_supports_session_verb_style(tmp_path):
    """接口层按文档写法接收登录好的 session 并调用 session.<verb> 时，扫描器必须识别。

    这是 doc/coding_style_guide.md 与 doc/mode_curl_manual.md 推荐的写法。
    若扫描器不认 session.<verb>(，新增接口会被静默漏扫（不报错），
    导致索引少一条、下次查重查不到、进而重复实现。
    """
    sample = tmp_path / "user_api.py"
    sample.write_text(
        '''
class UserApi:
    def create_user(self, session, payload):
        """创建用户"""
        url = "/api/users/create"
        return session.post(url, json=payload)
'''.strip(),
        encoding="utf-8",
    )

    records = scan_api_methods._parse_file(str(sample))

    assert len(records) == 1
    assert records[0]["api_url"] == "/api/users/create"
    assert records[0]["http_method"] == "POST"
    assert records[0]["api_name"] == "create_user"


def test_load_and_apply_custom_extract_rules(tmp_path):
    rules_file = tmp_path / "api_extract_rules.json"
    rules_file.write_text(
        json.dumps(
            {
                "url_extract_rules": [
                    {"name": "path_assignment", "pattern": r"\bpath\s*=\s*['\"](/api/[^'\"]+)['\"]", "group": 1}
                ],
                "method_extract_rules": [
                    {"name": "client_request_method", "pattern": r"\.client\.request\(\s*['\"]([A-Za-z]+)['\"]", "group": 1}
                ],
            }
        ),
        encoding="utf-8",
    )

    url_rules, method_rules = scan_api_methods._load_extract_rules(str(rules_file))
    source = 'path = "/api/custom/create"\nreturn self.client.request("POST", path)'

    assert scan_api_methods._extract_urls_from_source(source, url_rules) == ["/api/custom/create"]
    assert scan_api_methods._extract_http_method(source, method_rules) == "POST"


def test_parse_file_with_explicit_rules_uses_them_as_is(tmp_path):
    api_file = tmp_path / "custom_api.py"
    api_file.write_text(
        '''
class CustomApi:
    def create_custom(self):
        """创建自定义资源"""
        path = "/api/custom/create"
        return self.client.request("POST", path)
'''.strip(),
        encoding="utf-8",
    )
    url_rules = [
        {
            "name": "path_assignment",
            "pattern": scan_api_methods.re.compile(r"\bpath\s*=\s*['\"](/api/[^'\"]+)['\"]"),
            "group": 1,
        }
    ]
    method_rules = [scan_api_methods.re.compile(r"\.client\.request\(\s*['\"]([A-Za-z]+)['\"]")]

    records = scan_api_methods._parse_file(
        str(api_file), url_rules=url_rules, method_rules=method_rules
    )

    assert len(records) == 1
    assert records[0]["api_url"] == "/api/custom/create"
    assert records[0]["http_method"] == "POST"


def test_scan_all_records_file_relative_to_project_root(tmp_path):
    project = tmp_path / "project"
    api_dir = project / "src" / "clients"
    api_dir.mkdir(parents=True)
    (api_dir / "user_api.py").write_text(
        '''
import requests


class UserApi:
    def create_user(self):
        """创建用户"""
        # Author: tester
        # Create Date: 2026-06-01
        url = f"https://{self.base_url}/api/users/create"
        return requests.post(url, json={})
'''.strip(),
        encoding="utf-8",
    )

    records, scanned_files = scan_api_methods._scan_all(str(project), [str(api_dir)])

    assert scanned_files == 1
    assert len(records) == 1
    assert records[0]["api_url"] == "/api/users/create"
    assert records[0]["http_method"] == "POST"
    assert records[0]["file"] == "src/clients/user_api.py"


def test_resolve_scan_roots_reads_config(tmp_path, monkeypatch):
    project = tmp_path / "project"
    api_dir = project / "custom_api"
    api_dir.mkdir(parents=True)
    (api_dir / "order_api.py").write_text(
        '''
import requests


class OrderApi:
    def list_orders(self):
        """查询订单"""
        # Create Date: 2026-06-01
        url = "https://example.com/api/orders/list"
        return requests.get(url)
'''.strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(project),
                "paths": {"api_method_dirs": ["custom_api"], "pytest_workdir": "."},
                "api_index": {"scan_dirs": ["custom_api"]},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_loader, "DEFAULT_CONFIG_PATH", config_path)

    repo_root, scan_dirs = scan_api_methods._resolve_scan_roots()
    records, scanned_files = scan_api_methods._scan_all(repo_root, scan_dirs)

    assert repo_root == str(project.resolve())
    assert scan_dirs == [str(api_dir.resolve())]
    assert scanned_files == 1
    assert records[0]["api_url"] == "/api/orders/list"


def test_scan_empty_dir_returns_zero_without_error(tmp_path):
    project = tmp_path / "project"
    empty = project / "api"
    empty.mkdir(parents=True)

    records, scanned_files = scan_api_methods._scan_all(str(project), [str(empty)])

    assert records == []
    assert scanned_files == 0


def test_main_dry_run_reports_count_without_writing(tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    api_dir = project / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "user_api.py").write_text(
        '''
import requests


class UserApi:
    def create_user(self):
        """创建用户"""
        url = "https://example.com/api/users/create"
        return requests.post(url, json={})
'''.strip(),
        encoding="utf-8",
    )
    db_path = project / ".api-autotest" / "api_index.sqlite3"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(project),
                "paths": {"api_method_dirs": ["api"], "pytest_workdir": "."},
                "api_index": {"scan_dirs": ["api"], "db_path": str(db_path)},
            }
        ),
        encoding="utf-8",
    )

    exit_code = scan_api_methods.main(["--config", str(config_path), "--dry-run"])

    assert exit_code == 0
    assert not db_path.exists()
    assert "1" in capsys.readouterr().out
