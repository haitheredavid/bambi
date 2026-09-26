from datetime import date

import pytest

from bambi import session


def test_create_fills_template(sessions_dir):
    s = session.create("Phone Stand!", base=sessions_dir, today=date(2026, 9, 26))
    assert s.name == "2026-09-26-phone-stand"
    assert s.config["name"] == "phone-stand"
    assert s.config["created"] == "2026-09-26"
    assert s.config["slice"]["machine"] == "p1s_0.4"
    assert s.exports.is_dir() and s.out.is_dir()
    assert s.status() == "new"


def test_create_refuses_duplicates(sessions_dir):
    session.create("cube", base=sessions_dir, today=date(2026, 9, 26))
    with pytest.raises(FileExistsError):
        session.create("cube", base=sessions_dir, today=date(2026, 9, 26))


def test_resolve_by_substring(sessions_dir):
    session.create("cube", base=sessions_dir, today=date(2026, 9, 26))
    session.create("cube-v2", base=sessions_dir, today=date(2026, 9, 26))
    assert (
        session.resolve("2026-09-26-cube", base=sessions_dir).name == "2026-09-26-cube"
    )
    assert session.resolve("v2", base=sessions_dir).name == "2026-09-26-cube-v2"
    with pytest.raises(LookupError, match="ambiguous"):
        session.resolve("cube", base=sessions_dir)
    with pytest.raises(LookupError, match="no session"):
        session.resolve("nope", base=sessions_dir)


def test_list_skips_template(sessions_dir):
    session.create("a", base=sessions_dir)
    assert [s.name.split("-", 3)[-1] for s in session.list_all(base=sessions_dir)] == [
        "a"
    ]
