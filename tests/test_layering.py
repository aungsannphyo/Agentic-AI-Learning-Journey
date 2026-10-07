import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _imports(package: str) -> set[str]:
    found: set[str] = set()
    for path in (APP / package).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.add(node.module)
    return found


def _any_prefix(modules: set[str], prefix: str) -> list[str]:
    return sorted(m for m in modules if m == prefix or m.startswith(prefix + "."))


def test_agent_does_not_import_provider_sdk() -> None:
    assert _any_prefix(_imports("agent"), "openai") == []


def test_llm_does_not_import_agent() -> None:
    assert _any_prefix(_imports("llm"), "app.agent") == []


def test_tools_do_not_import_agent_or_llm() -> None:
    imports = _imports("tools")
    assert _any_prefix(imports, "app.agent") == []
    assert _any_prefix(imports, "app.llm") == []


def test_app_does_not_import_evals() -> None:
    for package in ("agent", "llm", "tools"):
        assert _any_prefix(_imports(package), "evals") == []

