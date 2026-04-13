from pathlib import Path

from trimr.adapters import OpenAIAdapter as ExportedOpenAIAdapter
from trimr.adapters.openai_adapter import OpenAIAdapter


FIXTURES = Path(__file__).parent / "fixtures"


def test_openai_adapter_is_exported():
    assert ExportedOpenAIAdapter is OpenAIAdapter


def test_detect_framework_from_assistant_json(tmp_path):
    (tmp_path / "assistant.json").write_text(
        '{"instructions": "Answer support questions using retrieved context."}',
        encoding="utf-8",
    )

    assert OpenAIAdapter(tmp_path).detect_framework() is True


def test_detect_framework_from_env_api_key(tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")

    assert OpenAIAdapter(tmp_path).detect_framework() is True


def test_detect_framework_returns_false_for_empty_project(tmp_path):
    assert OpenAIAdapter(tmp_path).detect_framework() is False


def test_walk_files_includes_root_env_file(tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "ignored.txt").write_text("ignore", encoding="utf-8")

    files = [p.name for p in OpenAIAdapter(tmp_path).walk_files()]

    assert ".env" in files
    assert "ignored.txt" not in files


def test_assistant_json_with_instructions_is_system_prompt_config(tmp_path):
    assistant = tmp_path / "assistant.json"
    assistant.write_text(
        '{"name": "Support", "instructions": "Use retrieval context before answering."}',
        encoding="utf-8",
    )

    adapter = OpenAIAdapter(tmp_path)

    assert adapter.is_config_with_system_prompt(assistant, assistant.read_text(encoding="utf-8")) is True


def test_get_global_files_classifies_assistant_json(tmp_path):
    assistant = tmp_path / "assistant.json"
    content = '{"instructions": "Use retrieval context before answering."}'
    assistant.write_text(content, encoding="utf-8")

    info = OpenAIAdapter(tmp_path).get_global_files(assistant, content)

    assert info == {"type": "assistant_json"}


def test_env_system_prompt_is_global_config(tmp_path):
    env_file = tmp_path / ".env"
    content = (
        "OPENAI_API_KEY=sk-test\n"
        "OPENAI_SYSTEM_PROMPT=\"You are the support assistant. Use policy, retrieval evidence, and account permissions before answering.\"\n"
    )
    env_file.write_text(content, encoding="utf-8")

    adapter = OpenAIAdapter(tmp_path)

    assert adapter.has_openai_credentials(content) is True
    assert adapter.is_config_with_system_prompt(env_file, content) is True
    assert adapter.get_global_files(env_file, content) == {"type": "env", "subtype": "system_prompt"}


def test_detects_markdown_skill_and_metadata(tmp_path):
    skill_file = tmp_path / "skills" / "retrieval" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    content = "---\nname: Retrieval\ndescription: Query file search before answering.\n---\n\nBody"
    skill_file.write_text(content, encoding="utf-8")

    adapter = OpenAIAdapter(tmp_path)
    info = adapter.get_skill_info(skill_file, content, tokens=20)

    assert adapter.is_skill_file(skill_file, content) is True
    assert info is not None
    assert info["name"] == "Retrieval"
    assert info["ungated"] is True
    assert info["vaultable"] is True


def test_vaulted_markdown_skill_is_not_ungated(tmp_path):
    skill_file = tmp_path / ".vault" / "skills" / "safety" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    content = "---\nname: Safety\ndescription: Check support answers for privacy risk.\n---\n\nBody"
    skill_file.write_text(content, encoding="utf-8")

    info = OpenAIAdapter(tmp_path).get_skill_info(skill_file, content, tokens=20)

    assert info is not None
    assert info["ungated"] is False
    assert info["vaultable"] is False


def test_detects_openai_function_tool_json(tmp_path):
    tool_file = tmp_path / "tools" / "lookup_ticket.json"
    tool_file.parent.mkdir(parents=True)
    content = """{
  "type": "function",
  "function": {
    "name": "lookup_ticket",
    "description": "Fetch ticket status and recent customer support activity.",
    "parameters": {"type": "object"}
  }
}"""
    tool_file.write_text(content, encoding="utf-8")

    adapter = OpenAIAdapter(tmp_path)
    info = adapter.get_skill_info(tool_file, content, tokens=45)

    assert adapter.is_skill_file(tool_file, content) is True
    assert info is not None
    assert info["name"] == "lookup_ticket"
    assert info["description_length"] > 10
    assert info["body_tokens"] == 45


def test_assistant_json_is_not_misclassified_as_tool_skill(tmp_path):
    assistant = tmp_path / "assistant.json"
    content = """{
  "name": "support-copilot",
  "description": "General support assistant configuration.",
  "instructions": "Use retrieval context before answering."
}"""
    assistant.write_text(content, encoding="utf-8")

    adapter = OpenAIAdapter(tmp_path)

    assert adapter.is_skill_file(assistant, content) is False
    assert adapter.get_skill_info(assistant, content, tokens=50) is None


def test_openai_fixture_contains_expected_project_mix():
    fixture = FIXTURES / "openai_project"
    adapter = OpenAIAdapter(fixture)

    files = adapter.walk_files()
    skill_files = []
    global_files = []
    for file_path in files:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        if adapter.is_skill_file(file_path, content):
            skill_files.append(file_path.relative_to(fixture).as_posix())
        global_info = adapter.get_global_files(file_path, content)
        if global_info:
            global_files.append(file_path.relative_to(fixture).as_posix())

    assert adapter.detect_framework() is True
    assert "assistant.json" in global_files
    assert ".env" in global_files
    assert "tools/lookup_ticket.json" in skill_files
    assert "functions/create_followup.json" in skill_files
    assert "skills/file-search/SKILL.md" in skill_files
    assert "skills/orphan_notes.md" not in skill_files
