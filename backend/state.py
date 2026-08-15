
from __future__ import annotations

# FSM transition tables produced by Stage 3, consumed by the V2 emitter.
_FSM_TRANSITION_TABLES: dict[str, dict] = {}

# Circuits generated at runtime and cached for reuse. Kept SEPARATE from
# known_circuits._KNOWN_HIERARCHIES so generated designs never mutate the
# curated library.
RUNTIME_CIRCUITS: dict[str, dict] = {}
RUNTIME_KEYWORDS: dict[str, list] = {}


def reset_request_state() -> None:
    """Clear per-generation scratch state. Call at the start of a generation."""
    _FSM_TRANSITION_TABLES.clear()