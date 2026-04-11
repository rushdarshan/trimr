"""
Test edge cases and potential failure modes.

Scenario breakdown:
1. High Non-ASCII Content (CJK/Devanagari)
2. Large Scale Repository Performance
3. Non-Markdown Agent Configurations (.json, .yaml, .toml)
4. Dynamic/Runtime Context Injection (static analysis only)
5. False Negatives in Skill Detection (Line 1 rule strictness)
6. Ignored Hidden Context Sources (hardcoded file list)
7. Gitignore Dependency (pathspec library availability)
"""

import pytest
from pathlib import Path
import tempfile
from trimr.audit import Auditor


class TestNonASCIIContent:
    """Scenario 1: High Non-ASCII Content (Language Bias)"""
    
    def test_cjk_content_token_accuracy(self):
        """Test CJK content token counting accuracy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            # Chinese content
            skill_file = target / "skill.md"
            chinese_content = """---
name: 中文技能
description: 这是一个中文技能文件，包含大量汉字内容以测试token计数准确性
---

这是技能主体内容。中文字符串通常比英文占用更多tokens。
让我们添加更多内容来测试：
这里有很多中文内容来测试分词和计数。
""" * 5
            
            skill_file.write_text(chinese_content, encoding="utf-8")
            
            auditor = Auditor(target)
            result = auditor.audit()
            
            # If NON_ASCII_ESTIMATE warning exists, the tool detected >20% non-ASCII
            non_ascii_warnings = [v for v in result.violations 
                                  if v.code.value == "NON_ASCII_ESTIMATE"]
            
            # The tool detects non-ASCII but may undercount tokens
            print(f"CJK content detected non-ASCII warnings: {len(non_ascii_warnings)}")
            print(f"Skill tokens: {result.skills[0].tokens if result.skills else 'No skills'}")
            
            # FLAW EXISTS IF: Token count is significantly lower than actual
            # (CJK characters use 2-3 tokens each, not 1.3x word count)
            return non_ascii_warnings
    
    def test_devanagari_content(self):
        """Test Devanagari script content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            skill_file = target / "hindi.md"
            # Devanagari script
            devanagari_content = """---
name: हिंदी कौशल
description: यह एक हिंदी कौशल फ़ाइल है
---

यह कौशल हिंदी में है। देवनागरी लिपि में सामग्री।
हमारे पास यहाँ बहुत सारा पाठ है।
""" * 3
            
            skill_file.write_text(devanagari_content, encoding="utf-8")
            
            auditor = Auditor(target)
            result = auditor.audit()
            
            print(f"Devanagari skills: {len(result.skills)}")
            print(f"Skills detected: {[s.path for s in result.skills]}")
            
            return result.skills


class TestLargeScalePerformance:
    """Scenario 2: Large Scale Repository Performance"""
    
    def test_massive_node_modules_traversal(self):
        """Test if rglob pre-gathering causes performance issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            # Create a simulated large node_modules structure
            node_modules = target / "node_modules" / "package" / "dist"
            node_modules.mkdir(parents=True)
            
            # Create many files that should be excluded
            for i in range(100):
                file = node_modules / f"file_{i}.js"
                file.write_text("x" * 1000)
            
            # Create actual skill file
            skill_file = target / "skill.md"
            skill_file.write_text("---\nname: Test\ndescription: Test\n---\nBody")
            
            import time
            start = time.time()
            auditor = Auditor(target)
            result = auditor.audit()
            elapsed = time.time() - start
            
            print(f"Audit time with large node_modules: {elapsed:.3f}s")
            print(f"Files found: {len(result.skills)}")
            
            # FLAW EXISTS IF: elapsed time > 1 second for small project
            # Or if node_modules files were counted
            return elapsed


class TestNonMarkdownConfigurations:
    """Scenario 3: Non-Markdown Agent Configurations"""
    
    def test_json_config_missed(self):
        """Test if .json config files are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            # Create a large JSON config (e.g., prompts.json)
            json_config = target / "prompts.json"
            large_json = '{"instructions": "' + ("x" * 5000) + '"}'
            json_config.write_text(large_json)
            
            auditor = Auditor(target)
            result = auditor.audit()
            
            print(f"Global files found: {len(result.global_files)}")
            print(f"Global file paths: {[g.path for g in result.global_files]}")
            
            # FLAW EXISTS IF: prompts.json is not detected
            return "prompts.json" not in str(result.global_files)
    
    def test_yaml_config_missed(self):
        """Test if .yaml/.yml config files are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            yaml_config = target / "config.yaml"
            yaml_config.write_text("system_prompt: " + "x" * 3000)
            
            auditor = Auditor(target)
            result = auditor.audit()
            
            print(f"YAML config detected: {any('config' in g.path for g in result.global_files)}")
            
            return result.global_files
    
    def test_toml_config_missed(self):
        """Test if .toml config files are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            toml_config = target / "pyproject.toml"
            toml_config.write_text("[tool.agent]\nprompt = " + '"' + "x" * 2000 + '"')
            
            auditor = Auditor(target)
            result = auditor.audit()
            
            print(f"TOML file detected: {any('toml' in g.path for g in result.global_files)}")
            
            return result.global_files


class TestDynamicContextInjection:
    """Scenario 4: Dynamic/Runtime Context Injection (Static Analysis Only)"""
    
    def test_cannot_detect_runtime_rag(self):
        """Test that tool only does static analysis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            # Create agent config with reference to external docs
            claude_file = target / "CLAUDE.md"
            claude_file.write_text("""---
name: RAG Agent
---

# Configuration

This agent loads documentation at runtime:

```python
# This code loads 20,000 tokens dynamically
docs = load_from_api("https://api.example.com/docs")
```

But trimr can only see this file statically.
""")
            
            auditor = Auditor(target)
            result = auditor.audit()
            
            # Static analysis shows minimal tokens
            print(f"Static analysis tokens: {result.startup_tokens_current}")
            print(f"Can detect runtime injection: No (static analysis only)")
            
            # FLAW EXISTS: Tool cannot account for 20,000 runtime tokens
            return result.startup_tokens_current < 1000


class TestSkillDetectionRigidity:
    """Scenario 5: False Negatives in Skill Detection (Line 1 Rule)"""
    
    def test_skill_with_title_above_frontmatter(self):
        """Test skill with # title BEFORE frontmatter (Line 2)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            skill_file = target / "skill.md"
            # Common pattern: developers put title above frontmatter
            skill_file.write_text("""# My Skill

---
name: MySkill
description: A skill with title above frontmatter
---

Body content here.
""")
            
            auditor = Auditor(target)
            result = auditor.audit()
            
            print(f"Skills detected: {len(result.skills)}")
            print(f"Skill paths: {[s.path for s in result.skills]}")
            
            # FLAW EXISTS IF: Skill not detected (0 skills found)
            return len(result.skills) == 0
    
    def test_skill_with_blank_line_before_frontmatter(self):
        """Test skill with blank line BEFORE frontmatter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            skill_file = target / "skill.md"
            skill_file.write_text("""

---
name: BlankLineSkill
description: Skill with blank line before frontmatter
---

Body.
""")
            
            auditor = Auditor(target)
            result = auditor.audit()
            
            print(f"Blank line skill detected: {len(result.skills) > 0}")
            
            # FLAW EXISTS IF: Skill not detected
            return len(result.skills) == 0


class TestIgnoredContextSources:
    """Scenario 6: Ignored Hidden Context Sources"""
    
    def test_custom_framework_config_ignored(self):
        """Test if custom framework configs (not in hardcoded list) are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            # Create a custom orchestrator config
            custom_config = target / "orchestrator.cfg"
            custom_config.write_text("system_prompt:\n" + "x" * 3000)
            
            auditor = Auditor(target)
            result = auditor.audit()
            
            print(f"Global files detected: {[g.path for g in result.global_files]}")
            
            # FLAW EXISTS IF: orchestrator.cfg not in global files
            detected = any("orchestrator" in g.path for g in result.global_files)
            print(f"Custom config detected: {detected}")
            
            return detected
    
    def test_hardcoded_file_list_exhaustiveness(self):
        """Test what global file names are supported."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            # Test known files
            known_files = {
                "CLAUDE.md": "✓",
                "AGENTS.md": "✓",
                ".cursorrules": "✓",
                "system.cfg": "❌ Not in hardcoded list"
            }
            
            for fname in known_files.keys():
                fpath = target / fname
                fpath.write_text("x" * 100)
            
            auditor = Auditor(target)
            result = auditor.audit()
            
            print("File detection results:")
            for fname in known_files.keys():
                detected = any(fname in g.path for g in result.global_files)
                print(f"  {fname}: {detected}")
            
            return result.global_files


class TestGitignoredDependency:
    """Scenario 7: Gitignore Dependency"""
    
    def test_gitignore_optional_dependency(self):
        """Test behavior when pathspec library is unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            
            # Create .gitignore
            gitignore = target / ".gitignore"
            gitignore.write_text("node_modules/\n.venv/\n")
            
            # Create files that should be ignored
            node_modules = target / "node_modules"
            node_modules.mkdir()
            (node_modules / "package.json").write_text("x" * 5000)
            
            # Try audit
            auditor = Auditor(target)
            result = auditor.audit()
            
            print(f"Total files scanned: {len(result.skills)}")
            
            # Check if .gitignore was respected
            has_nodemodules_files = any("node_modules" in str(s.path) for s in result.skills)
            print(f"node_modules files included: {has_nodemodules_files}")
            
            # FLAW EXISTS IF: .gitignore not respected (pathspec unavailable)
            return has_nodemodules_files


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
