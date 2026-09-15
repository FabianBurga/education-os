from app.modules.copilot import access


def test_m23_copilot_permissions_are_explicit():
    source = open(access.__file__, encoding="utf-8").read()
    assert "copilot.use" in source
    assert "copilot.manage" in source
    assert "copilot.action.approve" in source


def test_m23_management_roles_are_frozen():
    assert access.COPILOT_MANAGER_ROLES == {
        "SYSTEM_ADMIN",
        "RECTOR",
        "ACADEMIC_COORDINATOR",
    }
