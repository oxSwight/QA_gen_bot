"""Core generation API (transport-agnostic)."""
from qa_gen_bot.core.models import GenerationMode, GenerationRequest, GenerationResult

__all__ = [
    "GenerationMode",
    "GenerationRequest",
    "GenerationResult",
    "run_generation",
]


def __getattr__(name: str):
    if name == "run_generation":
        from qa_gen_bot.core.runner import run_generation

        return run_generation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
