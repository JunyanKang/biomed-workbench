import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseSurfaceTests(unittest.TestCase):
    def test_skill_description_is_trigger_only(self):
        text = (ROOT / "skills" / "biomed-workbench" / "SKILL.md").read_text()
        frontmatter = text.split("---", 2)[1]
        description = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE).group(1)

        self.assertTrue(description.startswith("Use when"))
        self.assertNotIn("Routes", description)
        self.assertLess(len(description), 500)

    def test_skill_resolves_tools_from_its_own_plugin_root(self):
        text = (ROOT / "skills" / "biomed-workbench" / "SKILL.md").read_text()

        self.assertIn("WORKBENCH_ROOT", text)
        self.assertIn('$WORKBENCH_ROOT/tools/workbench" doctor --strict', text)
        self.assertIn('$WORKBENCH_ROOT/tools/workbench" route', text)
        self.assertNotIn("From the plugin root", text)

    def test_public_release_has_license_and_consistent_versions(self):
        plugin = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
        catalog = json.loads((ROOT / "tools" / "catalog.json").read_text())

        self.assertTrue((ROOT / "LICENSE").exists())
        self.assertEqual(plugin["license"], "Apache-2.0")
        self.assertEqual(plugin["version"], "0.2.11")
        self.assertEqual(plugin["version"], catalog["version"])

        chinese_readme = (ROOT / "README.md").read_text(encoding="utf-8")
        english_readme = (ROOT / "README.en.md").read_text(encoding="utf-8")
        self.assertIn("docs/capabilities/README.zh-CN.md", chinese_readme)
        self.assertIn("docs/capabilities/README.md", english_readme)
        self.assertIn("assets/readme/biomed-workbench-editorial-hero.zh-CN.png", chinese_readme)
        self.assertIn("assets/readme/biomed-workbench-editorial-hero.en.png", english_readme)
        self.assertTrue((ROOT / "assets" / "readme" / "biomed-workbench-editorial-hero.zh-CN.png").exists())
        self.assertTrue((ROOT / "assets" / "readme" / "biomed-workbench-editorial-hero.en.png").exists())

    def test_public_figure_delivery_is_visible_in_both_languages(self):
        chinese = (ROOT / "docs" / "capabilities" / "scientific-figure-standards.zh-CN.md").read_text(encoding="utf-8")
        english = (ROOT / "docs" / "capabilities" / "scientific-figure-standards.md").read_text(encoding="utf-8")
        chinese_release = (ROOT / "docs" / "releases" / "2026-08-24-0.2.3.zh-CN.md").read_text(encoding="utf-8")
        english_release = (ROOT / "docs" / "releases" / "2026-08-24-0.2.3.md").read_text(encoding="utf-8")

        for text in (chinese, chinese_release):
            self.assertIn("600-dpi PNG", text)
            self.assertIn("作图数据", text)
        for text in (english, english_release):
            self.assertIn("600-dpi PNG", text)
            self.assertIn("source data", text)
        self.assertIn("1,228", chinese_release)
        self.assertIn("1,228", english_release)

    def test_quantitative_imaging_is_separate_from_project_wide_figure_support(self):
        chinese_readme = (ROOT / "README.md").read_text(encoding="utf-8")
        english_readme = (ROOT / "README.en.md").read_text(encoding="utf-8")
        chinese_imaging = (ROOT / "docs" / "capabilities" / "quantitative-imaging.zh-CN.md").read_text(encoding="utf-8")
        english_imaging = (ROOT / "docs" / "capabilities" / "quantitative-imaging.md").read_text(encoding="utf-8")
        chinese_figures = (ROOT / "docs" / "capabilities" / "scientific-figure-standards.zh-CN.md").read_text(encoding="utf-8")
        english_figures = (ROOT / "docs" / "capabilities" / "scientific-figure-standards.md").read_text(encoding="utf-8")
        legacy_chinese = (ROOT / "docs" / "capabilities" / "imaging-and-visualization.zh-CN.md").read_text(encoding="utf-8")
        legacy_english = (ROOT / "docs" / "capabilities" / "imaging-and-visualization.md").read_text(encoding="utf-8")

        self.assertIn("### 数据与研究对象", chinese_readme)
        self.assertIn("### 贯穿全项目的支撑能力", chinese_readme)
        self.assertIn("[定量图像分析]", chinese_readme)
        self.assertIn("[科学作图规范与图件交付]", chinese_readme)
        self.assertNotIn("[成像与科学可视化]", chinese_readme)
        self.assertIn("### Data scales and research objects", english_readme)
        self.assertIn("### Project-wide support", english_readme)
        self.assertIn("[Quantitative image analysis]", english_readme)
        self.assertIn("[Scientific figure standards and delivery]", english_readme)
        self.assertNotIn("[Imaging and scientific visualisation]", english_readme)

        self.assertIn("## 当前能力", chinese_imaging)
        self.assertIn("## Current Capabilities", english_imaging)
        self.assertIn("## 一张图在制作前需要明确什么", chinese_figures)
        self.assertIn("## What Must Be Defined Before Rendering", english_figures)
        self.assertNotIn("## 科学可视化", chinese_imaging)
        self.assertNotIn("## Scientific Visualisation", english_imaging)
        for link in ("quantitative-imaging.zh-CN.md", "scientific-figure-standards.zh-CN.md"):
            self.assertIn(link, legacy_chinese)
        for link in ("quantitative-imaging.md", "scientific-figure-standards.md"):
            self.assertIn(link, legacy_english)

    def test_taxonomy_correction_release_is_documented_bilingually(self):
        chinese = (ROOT / "docs" / "releases" / "2026-08-24-0.2.4.zh-CN.md").read_text(encoding="utf-8")
        english = (ROOT / "docs" / "releases" / "2026-08-24-0.2.4.md").read_text(encoding="utf-8")
        chinese_index = (ROOT / "docs" / "releases" / "README.zh-CN.md").read_text(encoding="utf-8")
        english_index = (ROOT / "docs" / "releases" / "README.md").read_text(encoding="utf-8")

        for term in ("定量图像分析", "全项目", "科学作图", "科研传播图像"):
            self.assertIn(term, chinese)
        for term in ("quantitative image analysis", "project-wide", "scientific figures", "scientific communication images"):
            self.assertIn(term, english)
        self.assertIn("2026-08-24-0.2.4.zh-CN.md", chinese_index)
        self.assertIn("2026-08-24-0.2.4.md", english_index)

    def test_proposal_and_scientific_routing_release_is_documented_bilingually(self):
        chinese = (ROOT / "docs" / "releases" / "2026-08-26-0.2.5.zh-CN.md").read_text(encoding="utf-8")
        english = (ROOT / "docs" / "releases" / "2026-08-26-0.2.5.md").read_text(encoding="utf-8")
        chinese_index = (ROOT / "docs" / "releases" / "README.zh-CN.md").read_text(encoding="utf-8")
        english_index = (ROOT / "docs" / "releases" / "README.md").read_text(encoding="utf-8")

        for term in ("复杂科学语义", "RNA 加工与可变剪接", "青年 C", "青年 B", "面上", "可编辑"):
            self.assertIn(term, chinese)
        for term in ("complex scientific semantics", "RNA processing and alternative splicing", "Young C", "Young B", "General", "editable"):
            self.assertIn(term, english)
        self.assertIn("2026-08-26-0.2.5.zh-CN.md", chinese_index)
        self.assertIn("2026-08-26-0.2.5.md", english_index)

    def test_readme_and_academic_voice_release_is_documented_bilingually(self):
        chinese = (ROOT / "docs" / "releases" / "2026-08-27-0.2.6.zh-CN.md").read_text(encoding="utf-8")
        english = (ROOT / "docs" / "releases" / "2026-08-27-0.2.6.md").read_text(encoding="utf-8")
        chinese_index = (ROOT / "docs" / "releases" / "README.zh-CN.md").read_text(encoding="utf-8")
        english_index = (ROOT / "docs" / "releases" / "README.md").read_text(encoding="utf-8")

        for term in ("中英文项目首页", "学术表达修订", "400 字", "英文摘要", "1,327"):
            self.assertIn(term, chinese)
        english_lower = english.lower()
        for term in ("bilingual project introduction", "academic voice revision", "400 characters", "English abstract", "1,327"):
            self.assertIn(term.lower(), english_lower)
        self.assertIn("2026-08-27-0.2.6.zh-CN.md", chinese_index)
        self.assertIn("2026-08-27-0.2.6.md", english_index)

    def test_analysis_environment_release_is_documented_bilingually(self):
        chinese = (ROOT / "docs" / "releases" / "2026-08-27-0.2.7.zh-CN.md").read_text(encoding="utf-8")
        english = (ROOT / "docs" / "releases" / "2026-08-27-0.2.7.md").read_text(encoding="utf-8")
        for term in ("分析环境身份", "重复分析", "环境漂移", "外部流水线"):
            self.assertIn(term, chinese)
        for term in ("analysis-environment identity", "repeat analysis", "environment", "external workflows"):
            self.assertIn(term, english.lower())

    def test_top_level_help_discovers_the_complete_project_command_surface(self):
        completed = subprocess.run(
            [str(ROOT / "tools" / "workbench"), "help"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        for command in (
            "prepare-revision",
            "migrate-state-v1",
            "upgrade-state-migration-1-1",
        ):
            self.assertIn(command, completed.stdout)
        self.assertIn("tools/workbench project --help", completed.stdout)
        self.assertIn("tools/workbench environment --project-root", completed.stdout)

        project_help = subprocess.run(
            [str(ROOT / "tools" / "workbench"), "project", "--help"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        for command in (
            "prepare-revision",
            "migrate-state-v1",
            "upgrade-state-migration-1-1",
        ):
            self.assertIn(command, project_help.stdout)

    def test_independent_modules_replace_workflow_reference_bridges(self):
        module_files = sorted((ROOT / "biomed_workbench" / "modules" / "builtin").glob("*/module.json"))
        catalog = json.loads((ROOT / "tools" / "catalog.json").read_text())

        self.assertEqual(len(module_files), catalog["entry_count"])
        self.assertFalse((ROOT / "biomed_workbench" / "capability_specs").exists())
        self.assertFalse((ROOT / "tools" / "add_capability.py").exists())
        self.assertFalse((ROOT / "references").exists())

    def test_public_readme_keeps_user_install_separate_from_maintainer_commands(self):
        readme = (ROOT / "README.md").read_text()
        english_readme = (ROOT / "README.en.md").read_text()
        development = (ROOT / "docs" / "development.md").read_text()

        repository_link = "[JunyanKang/biomed-workbench](https://github.com/JunyanKang/biomed-workbench)"
        self.assertIn(f"安装 {repository_link} 这个仓库的当前发布版本", readme)
        self.assertIn(f"Install the current release of {repository_link}", english_readme)
        self.assertIn("当前发布版本以 Codex 为主要使用环境", readme)
        self.assertIn("需要具备自己的文件访问、流程执行和结果读取能力", readme)
        self.assertIn("uses Codex as its primary supported environment", english_readme)
        self.assertIn("need their own file access, workflow execution and output-reading support", english_readme)
        self.assertNotIn("codex plugin marketplace add", readme)
        self.assertNotIn("codex plugin add", readme)
        self.assertIn("开启一个新的研究任务", readme)
        self.assertIn("open a new task", english_readme)
        self.assertNotIn("python3 ", readme)
        self.assertIn("python3 -m unittest discover -s tests -v", development)

    def test_public_documents_do_not_expose_journal_catalog_maintenance_metadata(self):
        public_paths = [ROOT / "README.md", ROOT / "README.en.md"]
        public_paths.extend(sorted((ROOT / "docs").rglob("*.md")))
        public_paths.append(ROOT / "skills" / "biomed-workbench" / "SKILL.md")
        forbidden = (
            "catalog_lifecycle",
            "draft/released",
            "draft and released",
            "数据采用明确的来源层级",
            "actual metric source",
            "每一行都显示实际采用的指标来源",
            "bibliometric fields",
            "期刊指标",
            "catalogue currently covers",
            "catalog currently covers",
            "规范库当前覆盖",
            "期刊规范库",
        )
        forbidden_patterns = (
            r"\b\d+\s+(?:biomedical|life[- ]science)\s+journals?\b",
            r"\d+\s*本[\u4e00-\u9fff]{0,12}期刊",
            r"\bjournal[- ]standards catalog(?:ue)?\b",
            r"\bjournal catalog(?:ue)?\b",
        )

        for path in public_paths:
            text = path.read_text(encoding="utf-8").lower()
            for phrase in forbidden:
                self.assertNotIn(phrase.lower(), text, f"{phrase!r} leaked into {path.relative_to(ROOT)}")
            for pattern in forbidden_patterns:
                self.assertIsNone(
                    re.search(pattern, text, flags=re.IGNORECASE),
                    f"journal catalogue metadata matching {pattern!r} leaked into {path.relative_to(ROOT)}",
                )

        skill_text = (ROOT / "skills" / "biomed-workbench" / "SKILL.md").read_text(encoding="utf-8").lower()
        for phrase in ("versioned catalog", "catalog version"):
            self.assertNotIn(phrase, skill_text)

    def test_bilingual_public_entrypoints_expose_complete_writing_capabilities(self):
        chinese_readme = (ROOT / "README.md").read_text(encoding="utf-8")
        english_readme = (ROOT / "README.en.md").read_text(encoding="utf-8")
        chinese_usage = (ROOT / "docs" / "using-biomed-workbench.zh-CN.md").read_text(encoding="utf-8")
        english_usage = (ROOT / "docs" / "using-biomed-workbench.md").read_text(encoding="utf-8")

        self.assertIn("## 论文写作与科研交付", chinese_readme)
        self.assertIn("## Academic Writing And Research Delivery", english_readme)
        self.assertIn("## 论文、基金和投稿任务怎样提出", chinese_usage)
        self.assertIn("## How To Request Manuscript, Proposal, And Submission Work", english_usage)

        for term in ("全文中英对照精读", "科研项目申请", "学术表达", "统计报告", "数据可用性", "审稿", "专利"):
            self.assertIn(term, chinese_readme)
        self.assertIn("完成中英文摘要", chinese_readme)
        self.assertIn("自然、严谨的生命科学语言", chinese_readme)
        for term in ("full-paper bilingual reading", "proposal", "scholarly prose", "statistical reporting", "data and code availability", "peer review", "patent"):
            self.assertIn(term, english_readme.lower())
        self.assertIn("aligned Chinese and English abstracts", english_readme)
        self.assertIn("natural, rigorous life-science language", english_readme)

        capability_link = "docs/capabilities/publication-and-translation"
        self.assertIn(f"{capability_link}.zh-CN.md", chinese_readme)
        self.assertIn(f"{capability_link}.md", english_readme)

        chinese_proposal = (ROOT / "docs" / "capabilities" / "nsfc-proposal-writing.zh-CN.md").read_text(encoding="utf-8")
        english_proposal = (ROOT / "docs" / "capabilities" / "nsfc-proposal-writing.md").read_text(encoding="utf-8")
        for term in ("中文摘要一般控制在 400 字以内", "英文摘要以中文摘要为科学基准", "不单独设置字数限制", "工程开发、审计管理", "生命科学同行"):
            self.assertIn(term, chinese_proposal)
        for term in ("within 400 Chinese characters", "not a word-for-word translation", "Engineering-development, audit-management", "life-science reviewer"):
            self.assertIn(term, english_proposal)


if __name__ == "__main__":
    unittest.main()
