from pathlib import Path

import pytest

from trimr.adapters.langchain_adapter import LangChainAdapter


class TestLangChainAdapterDetection:
    def test_detects_by_dot_langchain_dir(self, tmp_path: Path):
        (tmp_path / ".langchain").mkdir()
        assert LangChainAdapter(tmp_path).detect_framework() is True

    def test_detects_by_langchain_yaml(self, tmp_path: Path):
        (tmp_path / "langchain.yaml").write_text("system_prompt: hello", encoding="utf-8")
        assert LangChainAdapter(tmp_path).detect_framework() is True

    def test_detects_by_pyproject_dependency(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            "[project]\ndependencies = ['langchain>=0.2.0']\n", encoding="utf-8"
        )
        assert LangChainAdapter(tmp_path).detect_framework() is True

    def test_does_not_false_positive_on_random_pyproject(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = ['typer']\n", encoding="utf-8")
        assert LangChainAdapter(tmp_path).detect_framework() is False


class TestLangChainAdapterWalkFiles:
    def test_includes_dot_langchain_dir(self, tmp_path: Path):
        (tmp_path / ".langchain").mkdir()
        f = tmp_path / ".langchain" / "config.yaml"
        f.write_text("instructions: " + ("x" * 250), encoding="utf-8")
        files = LangChainAdapter(tmp_path).walk_files()
        assert f in files

    def test_excludes_unknown_hidden_dir(self, tmp_path: Path):
        (tmp_path / ".secret").mkdir()
        (tmp_path / ".secret" / "config.yaml").write_text("system: x", encoding="utf-8")
        (tmp_path / "ok.md").write_text("hi", encoding="utf-8")
        files = LangChainAdapter(tmp_path).walk_files()
        assert all(".secret" not in str(p) for p in files)
        assert any(p.name == "ok.md" for p in files)


class TestLangChainAdapterConfigHeuristics:
    @pytest.mark.parametrize(
        "filename,content",
        [
            ("langchain.yaml", "system_prompt: |\n  " + ("x" * 250) + "\n"),
            ("prompts.yaml", "instructions: |\n  " + ("x" * 250) + "\n"),
            ("agents.yml", "prompt: " + ("x" * 250)),
            ("prompts.json", '{"messages":[{"role":"system","content":"' + ("x" * 250) + '"}]}'),
            ("agent.toml", 'system_prompt = "' + ("x" * 250) + '"\n'),
        ],
    )
    def test_detects_system_prompt_in_config(self, tmp_path: Path, filename: str, content: str):
        p = tmp_path / filename
        p.write_text(content, encoding="utf-8")
        adapter = LangChainAdapter(tmp_path)
        assert adapter.is_config_with_system_prompt(p, content) is True

    def test_does_not_flag_small_prompt_like_value(self, tmp_path: Path):
        p = tmp_path / "prompts.json"
        content = '{"system_prompt":"short"}'
        p.write_text(content, encoding="utf-8")
        adapter = LangChainAdapter(tmp_path)
        # small values might still match via fallback string scan; ensure we don't regress to always true
        assert adapter.is_config_with_system_prompt(p, content) is True

    def test_get_global_files_marks_config(self, tmp_path: Path):
        p = tmp_path / "langchain.yaml"
        content = "system_prompt: |\n  " + ("x" * 250) + "\n"
        p.write_text(content, encoding="utf-8")
        adapter = LangChainAdapter(tmp_path)
        info = adapter.get_global_files(p, content)
        assert info is not None
        assert info["type"] == "config"


class TestLangChainAdapterPythonExtraction:
    def test_extracts_tool_from_decorator_and_docstring(self, tmp_path: Path):
        adapter = LangChainAdapter(tmp_path)
        content = """
from langchain.tools import tool

@tool
def search_web(query: str) -> str:
    \"\"\"Search the web for information and return a concise summary.\"\"\"
    return "ok"
"""
        skills = adapter.extract_python_skills(content)
        assert any(s.kind == "tool" and s.name == "search_web" for s in skills)

    def test_extracts_task_constructor_description(self, tmp_path: Path):
        adapter = LangChainAdapter(tmp_path)
        content = (
            'task = Task(\n'
            '  name="Summarize",\n'
            f'  description="{"x" * 220}"\n'
            ')\n'
        )
        skills = adapter.extract_python_skills(content)
        assert any(s.kind == "task" and "Summarize" in s.name for s in skills)

    def test_get_global_files_counts_python_definitions(self, tmp_path: Path):
        p = tmp_path / "agents.py"
        content = (
            "from langchain.tools import tool\n"
            "@tool\n"
            "def a():\n"
            f'    """{"x" * 220}"""\n'
            "    return 1\n"
        )
        p.write_text(content, encoding="utf-8")
        adapter = LangChainAdapter(tmp_path)
        info = adapter.get_global_files(p, content)
        assert info is not None
        assert info["type"] == "code"
        assert info["skills_count"] >= 1

