from pathlib import Path

import pytest

from trimr.adapters.crewai_adapter import CrewAIAdapter


class TestCrewAIAdapterDetection:
    def test_detects_by_dot_crewai_dir(self, tmp_path: Path):
        (tmp_path / ".crewai").mkdir()
        assert CrewAIAdapter(tmp_path).detect_framework() is True

    def test_detects_by_crew_structure(self, tmp_path: Path):
        (tmp_path / "crew.py").write_text("from crewai import Crew\n", encoding="utf-8")
        (tmp_path / "agents.py").write_text("from crewai import Agent\n", encoding="utf-8")
        assert CrewAIAdapter(tmp_path).detect_framework() is True

    def test_detects_by_pyproject_dependency(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            "[project]\ndependencies = ['crewai>=0.30.0']\n", encoding="utf-8"
        )
        assert CrewAIAdapter(tmp_path).detect_framework() is True

    def test_does_not_false_positive_on_random_pyproject(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = ['pytest']\n", encoding="utf-8")
        assert CrewAIAdapter(tmp_path).detect_framework() is False


class TestCrewAIAdapterWalkFiles:
    def test_includes_dot_crewai_dir(self, tmp_path: Path):
        (tmp_path / ".crewai").mkdir()
        f = tmp_path / ".crewai" / "config.yaml"
        f.write_text("system_prompt: " + ("x" * 250), encoding="utf-8")
        files = CrewAIAdapter(tmp_path).walk_files()
        assert f in files

    def test_excludes_unknown_hidden_dir(self, tmp_path: Path):
        (tmp_path / ".private").mkdir()
        (tmp_path / ".private" / "x.json").write_text('{"system_prompt":"x"}', encoding="utf-8")
        (tmp_path / "ok.md").write_text("hi", encoding="utf-8")
        files = CrewAIAdapter(tmp_path).walk_files()
        assert all(".private" not in str(p) for p in files)
        assert any(p.name == "ok.md" for p in files)


class TestCrewAIAdapterConfigHeuristics:
    @pytest.mark.parametrize(
        "filename,content",
        [
            ("config.yaml", "instructions: |\n  " + ("x" * 250) + "\n"),
            ("agents.yml", "system_prompt: " + ("x" * 250)),
            ("crew.json", '{"system":{"prompt":"' + ("x" * 250) + '"}}'),
            ("crew.toml", 'prompt = "' + ("x" * 250) + '"\n'),
        ],
    )
    def test_detects_system_prompt_in_config(self, tmp_path: Path, filename: str, content: str):
        p = tmp_path / filename
        p.write_text(content, encoding="utf-8")
        adapter = CrewAIAdapter(tmp_path)
        assert adapter.is_config_with_system_prompt(p, content) is True

    def test_get_global_files_marks_python_entrypoints(self, tmp_path: Path):
        p = tmp_path / "crew.py"
        content = (
            "from crewai import Crew, Agent, Task\n\n"
            f'my_agent = Agent(role="Researcher", goal="{"x" * 220}")\n'
        )
        p.write_text(content, encoding="utf-8")
        adapter = CrewAIAdapter(tmp_path)
        info = adapter.get_global_files(p, content)
        assert info is not None
        assert info["type"] == "code"
        assert info["definitions_count"] >= 1


class TestCrewAIAdapterPythonExtraction:
    def test_extracts_tool_from_decorator_and_docstring(self, tmp_path: Path):
        adapter = CrewAIAdapter(tmp_path)
        content = """
from crewai_tools import tool

@tool
def fetch(url: str) -> str:
    \"\"\"Fetch a URL and return extracted text content for analysis.\"\"\"
    return "ok"
"""
        defs_ = adapter.extract_definitions(content)
        assert any(d.kind == "tool" and d.name == "fetch" for d in defs_)

    def test_extracts_agent_goal(self, tmp_path: Path):
        adapter = CrewAIAdapter(tmp_path)
        content = (
            "from crewai import Agent\n"
            f'agent = Agent(role="Analyst", goal="{"x" * 220}")\n'
        )
        defs_ = adapter.extract_definitions(content)
        assert any(d.kind == "agent" and "Analyst" in d.name for d in defs_)

    def test_extracts_task_description(self, tmp_path: Path):
        adapter = CrewAIAdapter(tmp_path)
        content = (
            "from crewai import Task\n"
            f'task = Task(name="Summarize", description="{"x" * 220}")\n'
        )
        defs_ = adapter.extract_definitions(content)
        assert any(d.kind == "task" and "Summarize" in d.name for d in defs_)

