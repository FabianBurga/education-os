from __future__ import annotations

import ast
import inspect
from types import SimpleNamespace

from app.modules.automation import service


class _FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, str]]] = []

    def exec_driver_sql(
        self,
        statement: str,
        parameters: tuple[str, str],
    ) -> None:
        self.calls.append((statement, parameters))


class _FakeSession:
    def __init__(self) -> None:
        self.connection_object = _FakeConnection()

    def connection(self) -> _FakeConnection:
        return self.connection_object


def test_restore_rls_context_after_commit_sets_all_principal_dimensions() -> None:
    session = _FakeSession()
    principal = SimpleNamespace(
        organization_id="11111111-1111-1111-1111-111111111111",
        institution_id="22222222-2222-2222-2222-222222222222",
        user_id="33333333-3333-3333-3333-333333333333",
    )

    service._restore_rls_context_after_commit(session, principal)

    assert session.connection_object.calls == [
        (
            "SELECT set_config(%s, %s, true)",
            ("app.organization_id", principal.organization_id),
        ),
        (
            "SELECT set_config(%s, %s, true)",
            ("app.institution_id", principal.institution_id),
        ),
        (
            "SELECT set_config(%s, %s, true)",
            ("app.user_id", principal.user_id),
        ),
    ]


def test_acknowledge_and_complete_restore_rls_between_commit_and_refresh() -> None:
    for fn in (service.acknowledge_task, service.complete_task):
        source = inspect.getsource(fn)
        ast.parse(source)
        lines = [line.strip() for line in source.splitlines() if line.strip()]
        expected = [
            "session.commit()",
            "_restore_rls_context_after_commit(session, principal)",
            "session.refresh(task)",
        ]
        assert any(lines[index : index + 3] == expected for index in range(len(lines) - 2)), (
            fn.__name__
        )
