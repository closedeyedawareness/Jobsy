"""
Guard rails on the shape of the UI package.

The split on 2026-09-03 put the page modules in `ui/pages/`, which is a name
Streamlit reserves: a `pages/` directory beside the entrypoint script becomes
automatic multipage navigation. Every module was listed in the sidebar and
served at its own URL — and reaching one that way runs the module directly,
without ui/app.py, so without `_require_password`. The login screen was intact
and the sidebar next to it walked straight past it.

These tests are cheap and they pin the two facts that mattered.
"""

from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "ui"


def test_there_is_no_pages_directory_beside_the_entrypoint():
    """Streamlit would auto-serve everything in it, outside the password gate."""
    assert not (UI / "pages").exists(), (
        "ui/pages/ is Streamlit's reserved multipage directory: every module in it is "
        "served at its own URL without ui/app.py running, which bypasses the password "
        "gate. The page modules live in ui/views/."
    )


def test_the_page_modules_are_where_app_expects_them():
    modules = {p.stem for p in (UI / "views").glob("*.py")} - {"__init__"}
    assert len(modules) == 12, sorted(modules)
    source = (UI / "app.py").read_text(encoding="utf-8")
    for module in modules:
        assert f"from ui.views.{module} import" in source, f"app.py never imports {module}"


def test_a_view_module_renders_nothing_on_import():
    """Defence in depth: even if a directory is auto-served again, importing a
    view must not draw a page. They define functions and nothing else."""
    import ast
    for path in (UI / "views").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                called = ast.unparse(node.value.func)
                assert not called.startswith("st."), (
                    f"{path.name} calls {called} at import time")
