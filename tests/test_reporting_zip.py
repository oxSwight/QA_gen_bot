"""ZIP delivery only includes sources when Maven + static gate pass."""
import zipfile
from pathlib import Path

from qa_gen_bot.maven_validator import MavenValidationResult
from qa_gen_bot.pipeline import PipelineResult
from qa_gen_bot.quality_gate import GateResult
from qa_gen_bot.reporting import write_project_zip


def test_zip_excludes_sources_when_maven_fails(tmp_path: Path):
    files = {"pom.xml": "<project/>", "src/test/Foo.java": "class Foo {}"}
    result = PipelineResult(
        files=files,
        static_gate=GateResult(passed=True),
        maven=MavenValidationResult(passed=False, errors=["compile"]),
    )
    zip_path = write_project_zip(
        tmp_path,
        result,
        package_hint="demo",
        analysis_title="Demo",
        ops_count=1,
    )
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert "pom.xml" not in names
    assert any("GENERATION" in n for n in names)


def test_zip_includes_sources_when_delivery_ready(tmp_path: Path):
    files = {"pom.xml": "<project/>"}
    result = PipelineResult(
        files=files,
        static_gate=GateResult(passed=True),
        maven=MavenValidationResult(passed=True, tests_run=3),
    )
    zip_path = write_project_zip(
        tmp_path,
        result,
        package_hint="demo",
        analysis_title="Demo",
        ops_count=1,
    )
    with zipfile.ZipFile(zip_path) as zf:
        assert "pom.xml" in zf.namelist()
