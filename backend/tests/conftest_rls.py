"""
A production-faithful RLS lane for ENDPOINT tests (issue #50, second half).

Why this module exists
----------------------
``app/api/deps.py:get_db`` binds the RLS GUC **once**, at the start of the
request, via ``bind_rls_context()`` (which issues ``SET LOCAL``). ``SET
LOCAL`` is transaction-scoped in PostgreSQL: it is reverted at COMMIT. Any
handler that does ``await db.commit()`` and then reads an RLS-protected
table again therefore reads in a NEW transaction with the GUC **unset** --
which, with FORCE ROW LEVEL SECURITY, is a default-deny state.

The existing test harness hides that completely, via two independent masks:

1. **A global service listener.** ``tests/conftest.py`` registers
   ``@event.listens_for(SyncSession, "after_begin") -> _bind_service_rls``,
   which re-applies ``SET LOCAL app.current_user_id = '0'`` on *every* ORM
   BEGIN, process-wide. It re-binds a GUC production never re-binds, so
   every endpoint test silently runs under the service bypass.
2. **A superuser test role.** The session factory connects as ``asistcv``,
   which is SUPERUSER + BYPASSRLS. Superusers bypass RLS entirely, even
   with FORCE -- so this mask alone defeats the defect regardless of (1).

This module neutralises both for the duration of one test and restores
them afterwards. It generalises the machinery already proven in
``tests/test_adaptation_runner.py::_production_sessions``.

What the lane guarantees
------------------------
* The conftest ``after_begin`` service listener is **removed**, so nothing
  re-binds a GUC on BEGIN.
* Every connection the APP opens (the real ``get_session()`` ->
  ``get_session_factory()`` -> cached ``AsyncEngine`` that ``get_db`` uses)
  runs ``SET ROLE asistcv_rls``: NON-superuser, NOBYPASSRLS, table owner --
  the same shape as the production app role.
* ``get_db`` is **NOT** overridden and no GUC is set by the test. The
  handler under test receives the exact session the real dependency
  produces, and the only GUC binding is the production one.
* Teardown removes the connect listener and re-registers the conftest
  listener, so the other tests in the session are unaffected.

Fail-closed
-----------
Setup asserts the lane is really faithful (right role, not superuser, not
bypassrls, GUC unset on a fresh transaction, table under ENABLE+FORCE). A
green test in a lane that silently lost its fidelity would be worse than no
test at all, so the fixture refuses to hand out a lane it cannot prove.
"""
from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy import text
from sqlalchemy.orm import Session as SyncSession

# `tests.conftest` is already in sys.modules by the time any test module
# imports this one, so RLS_TEST_ROLE is the exact name the harness created.
from tests.conftest import RLS_TEST_ROLE

__all__ = [
    "RlsLane",
    "assert_lane_is_faithful",
    "find_conftest_service_listener",
    "production_rls_lane",
]


def find_conftest_service_listener() -> Any:
    """Return the conftest ``after_begin`` listener, wherever pytest filed it.

    pytest holds ``conftest.py`` under ``tests.conftest`` when the tests
    package is importable and under plain ``conftest`` otherwise, so both
    names are probed and the match is confirmed with ``event.contains``
    rather than by identity of the module attribute.
    """
    for mod_name in ("tests.conftest", "conftest"):
        mod = sys.modules.get(mod_name)
        candidate = getattr(mod, "_bind_service_rls", None) if mod else None
        if candidate is not None and sa_event.contains(
            SyncSession, "after_begin", candidate
        ):
            return candidate
    raise AssertionError(
        "the conftest _bind_service_rls after_begin listener is not registered; "
        "tests/conftest.py changed shape and this lane can no longer prove it "
        "removed the service re-bind (issue #50)"
    )


@dataclass
class RlsLane:
    """A handle on the active production-faithful lane.

    Exposes the app engine so tests can open a session with or without a
    GUC -- which is how the control tests observe the deny path that the
    post-commit read lands in.
    """

    role: str
    engine: Any  # app.db.session's cached AsyncEngine

    def _factory(self) -> Any:
        from app.db.session import get_session_factory

        return get_session_factory()

    def session(self) -> Any:
        """An app session with **no** GUC bound.

        This is the exact state a handler lands in after ``commit()``: the
        request-scoped ``SET LOCAL`` is gone, and (mask 1 removed) nothing
        re-binds it.
        """
        return self._factory()()

    @asynccontextmanager
    async def as_user(self, user_id: int, role: str = "job_seeker") -> AsyncIterator[Any]:
        """Bind the RLS context exactly the way production does.

        Delegates to ``app.services.rls_context.bind_rls_context`` -- the same
        call ``get_db`` makes -- so the control tests exercise the production
        GUC spelling rather than a hand-rolled one.
        """
        from app.services.rls_context import bind_rls_context

        async with self.session() as session:
            await bind_rls_context(session, user_id, role)
            yield session


async def assert_lane_is_faithful(lane: RlsLane) -> None:
    """Refuse to continue unless the lane really reproduces production.

    Four independent properties, each of which one of the two masks in the
    module docstring would violate.
    """
    async with lane.engine.connect() as conn:
        who = (await conn.execute(text("SELECT current_user"))).scalar_one()
        if who != lane.role:
            raise AssertionError(
                f"RLS lane is not faithful: app connection runs as {who!r}, "
                f"expected {lane.role!r} (tests/conftest_rls.py)"
            )

        priv = (
            await conn.execute(
                text(
                    "SELECT rolsuper, rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            )
        ).one()
        if priv.rolsuper or priv.rolbypassrls:
            raise AssertionError(
                f"RLS lane is not faithful: role {who!r} has "
                f"rolsuper={priv.rolsuper} rolbypassrls={priv.rolbypassrls}; "
                "superusers and BYPASSRLS roles ignore FORCE ROW LEVEL SECURITY"
            )

        # A brand-new transaction. The conftest after_begin listener would
        # have injected the service GUC right here.
        guc = (
            await conn.execute(
                text("SELECT current_setting('app.current_user_id', true)")
            )
        ).scalar_one()
        if guc is not None:
            raise AssertionError(
                f"RLS lane is not faithful: app.current_user_id={guc!r} on a "
                "fresh transaction; the conftest service after_begin listener "
                "is still active"
            )

        forced = (
            await conn.execute(
                text(
                    "SELECT c.relrowsecurity, c.relforcerowsecurity "
                    "FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE c.relname = 'users_cvs' AND n.nspname = 'public'"
                )
            )
        ).one()
        if not (forced.relrowsecurity and forced.relforcerowsecurity):
            raise AssertionError(
                "RLS lane is not faithful: users_cvs is not under "
                f"ENABLE+FORCE ROW LEVEL SECURITY (rls={forced.relrowsecurity}, "
                f"force={forced.relforcerowsecurity})"
            )


@asynccontextmanager
async def production_rls_lane() -> AsyncIterator[RlsLane]:
    """Yield a :class:`RlsLane` with both harness masks neutralised.

    On exit the app engine is left exactly as it was found and the conftest
    service listener is back in place, so a failure inside a test cannot
    leak the lane into the rest of the session.
    """
    listener = find_conftest_service_listener()
    sa_event.remove(SyncSession, "after_begin", listener)

    # The APP engine, not a private one: this is the engine get_db reaches
    # through get_session() -> get_session_factory(). A separate engine would
    # mean the handler under test never sees these connections.
    from app.db.session import get_engine

    engine = get_engine()
    sync_engine = engine.sync_engine

    @sa_event.listens_for(sync_engine, "connect")
    def _use_rls_role(dbapi_conn: Any, _record: Any) -> None:
        # Session-scoped (no LOCAL) on purpose: every connection the app
        # engine opens must be the non-superuser role for its whole life.
        # The engine is NullPool, so "every connection" is unambiguous.
        cur = dbapi_conn.cursor()
        try:
            cur.execute(f"SET ROLE {RLS_TEST_ROLE}")  # noqa: S608
        finally:
            cur.close()

    try:
        lane = RlsLane(role=RLS_TEST_ROLE, engine=engine)
        await assert_lane_is_faithful(lane)
        yield lane
    finally:
        sa_event.remove(sync_engine, "connect", _use_rls_role)
        sa_event.listen(SyncSession, "after_begin", listener)
