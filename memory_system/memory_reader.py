"""Read NOVA's existing memory.json without changing its contents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def default_memory_path() -> Path:
    """Return the project's root memory.json path by default."""
    return Path(__file__).resolve().parent.parent / "memory.json"


def empty_memory() -> dict[str, Any]:
    return {
        "user_name": "",
        "facts": [],
        "conversation": [],
        "long_term": {
            "identity": {},
            "preferences": {},
            "projects": {},
            "goals": {},
            "notes": {},
        },
    }


def load_memory(
    memory_file: str | Path | None = None,
    memory: dict[str, Any] | None = None,
    memory_provider: Callable[[], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Load the latest in-memory data when available, otherwise read JSON.

    `memory_provider` is useful when NOVA replaces its memory dictionary after
    saving. The returned value is copied so the viewer cannot mutate NOVA's
    live memory accidentally.
    """
    current = None
    if memory_provider is not None:
        try:
            current = memory_provider()
        except Exception:
            current = None
    if current is None:
        current = memory
    if isinstance(current, dict):
        return _normalise_root(current)

    path = Path(memory_file) if memory_file else default_memory_path()
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            return _normalise_root(data)
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError) as exc:
        # Keep the UI usable if the file is temporarily being rewritten or
        # contains malformed JSON. The caller can show the warning to the user.
        result = empty_memory()
        result["_load_error"] = f"Could not read {path.name}: {exc}"
        return result

    result = empty_memory()
    result["_load_error"] = f"Memory file not found: {path}"
    return result


def _normalise_root(data: dict[str, Any]) -> dict[str, Any]:
    """Copy data and ensure the expected top-level containers exist."""
    import copy

    result = copy.deepcopy(data)
    result.setdefault("user_name", "")
    if not isinstance(result.get("facts"), list):
        result["facts"] = []
    if not isinstance(result.get("conversation"), list):
        result["conversation"] = []
    if not isinstance(result.get("long_term"), dict):
        result["long_term"] = {}
    for category, value in list(result["long_term"].items()):
        if not isinstance(value, (dict, list)):
            result["long_term"][category] = {"Saved item": value}
    for category in ("identity", "preferences", "projects", "goals", "notes"):
        result["long_term"].setdefault(category, {})
    return result
