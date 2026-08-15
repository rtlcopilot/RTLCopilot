
from __future__ import annotations


class GenerationFailure(Exception):
    """Raised when generation cannot produce a trustworthy circuit."""

    def __init__(self, stage: str, reason: str,
                 details: list[str] | None = None,
                 suggestions: list[str] | None = None):
        self.stage = stage
        self.reason = reason
        self.details = details or []
        self.suggestions = suggestions or []
        super().__init__(f"[{stage}] {reason}")

    def to_response(self) -> dict:
        lines = [f"I couldn't build this circuit reliably, so I've left your "
                 f"canvas unchanged.", "", f"**Where it stopped:** {self.stage}",
                 f"**Why:** {self.reason}"]
        if self.details:
            lines += ["", "**Details:**"] + [f"  - {d}" for d in self.details]
        if self.suggestions:
            lines += ["", "**What would help:**"] + [f"  - {s}" for s in self.suggestions]
        return {
            "explanation":       "\n".join(lines),
            "nodes":             [],
            "edges":             [],
            "generation_failed": True,
            "failure": {
                "stage":       self.stage,
                "reason":      self.reason,
                "details":     self.details,
                "suggestions": self.suggestions,
            },
        }


def unsupported_block(requested: str, supported: list[str]) -> GenerationFailure:
    """The model asked for a block type this tool does not have.

    Previously this was silently rewritten to a `comb` adder, which produced a
    complete-looking circuit that was wrong in a way nothing surfaced.
    """
    return GenerationFailure(
        stage="block mapping",
        reason=f"The design needs a '{requested}' block, which this tool "
               f"does not have as a primitive.",
        details=[f"Supported block types: {', '.join(sorted(supported))}"],
        suggestions=[
            f"Describe how '{requested}' should be built from the supported "
            f"blocks, and I'll wire it up.",
            "Or build it once by hand and save it as a custom block.",
        ],
    )


__all__ = [_n for _n in dir() if not _n.startswith("__")]