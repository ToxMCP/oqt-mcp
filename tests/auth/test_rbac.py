import json
import logging
import pytest

from src.auth import rbac


@pytest.fixture(autouse=True)
def reload_permissions(monkeypatch, tmp_path):
    # create temporary permissions file
    permissions = {
        "GUEST": ["view_tool"],
        "RESEARCHER": ["view_tool", "edit_tool"],
    }
    path = tmp_path / "tool_permissions.json"
    path.write_text(json.dumps(permissions), encoding="utf-8")

    monkeypatch.setattr(rbac.settings.security, "TOOL_PERMISSIONS_FILE", str(path))
    # reload module-level permissions
    monkeypatch.setattr(rbac, "TOOL_PERMISSIONS", rbac._load_permissions())
    yield


def test_check_permission_allows_known_role(caplog):
    caplog.set_level(logging.INFO, logger="src.auth.rbac")
    allowed = rbac.check_permission(["RESEARCHER"], "edit_tool")
    assert allowed
    assert any("Authorization granted" in record.message for record in caplog.records)


def test_check_permission_denies_unknown_role(caplog):
    caplog.set_level(logging.INFO, logger="src.auth.rbac")
    allowed = rbac.check_permission(["UNKNOWN"], "edit_tool")
    assert not allowed
    assert any("Authorization denied" in record.message for record in caplog.records)


def test_check_permission_allows_when_any_role_matches():
    allowed = rbac.check_permission(["UNKNOWN", "RESEARCHER"], "edit_tool")
    assert allowed


def test_check_permission_denies_unknown_tool():
    allowed = rbac.check_permission(["RESEARCHER"], "nonexistent_tool")
    assert not allowed


def test_load_permissions_invalid_json(monkeypatch, tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{invalid", encoding="utf-8")
    monkeypatch.setattr(rbac.settings.security, "TOOL_PERMISSIONS_FILE", str(bad_file))
    with pytest.raises(json.JSONDecodeError):
        rbac._load_permissions()
