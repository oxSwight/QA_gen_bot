"""Domain models for generation runs (Mode A / Mode B)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from qa_gen_bot.config import GenerationProfile
from qa_gen_bot.maven_validator import MavenValidationResult
from qa_gen_bot.quality_gate import GateResult
from qa_gen_bot.spec_parser import SpecAnalysis

GenerationMode = Literal["quick_start", "repo"]


@dataclass(frozen=True)
class GenerationRequest:
    """Input for a single generation run (no Telegram/CLI specifics)."""

    analysis: SpecAnalysis
    spec_content: str
    generation_profile: GenerationProfile
    base_url_override: str | None = None
    mode: GenerationMode = "quick_start"
    files_preloaded: dict[str, str] | None = None
    cache_path: str | None = None

    @property
    def uses_wiremock(self) -> bool:
        return self.generation_profile == "contract-mocks"


@dataclass
class GenerationResult:
    """Output of a generation run (same shape as legacy PipelineResult)."""

    files: dict[str, str]
    static_gate: GateResult
    maven: MavenValidationResult | None
    log: list[str] = field(default_factory=list)
    elapsed_sec: int = 0
    generated_files_raw: dict[str, str] | None = None
    mode: GenerationMode = "quick_start"

    @property
    def delivery_ready(self) -> bool:
        if not self.static_gate.passed:
            return False
        if self.maven is None:
            return True
        if self.maven.skipped:
            return False
        return self.maven.passed

    @property
    def zip_shippable(self) -> bool:
        return self.delivery_ready

    @property
    def partial_success(self) -> bool:
        return self.static_gate.passed and not self.delivery_ready
