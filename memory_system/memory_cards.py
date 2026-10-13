"""Convert NOVA memory data into categories and display-friendly cards."""

from __future__ import annotations

from typing import Any

CATEGORY_LABELS = {
    "identity": "Identity",
    "preferences": "Preferences",
    "projects": "Projects",
    "goals": "Goals",
    "notes": "Notes",
    "facts": "Facts",
    "conversation": "Conversation",
}

CATEGORY_DESCRIPTIONS = {
    "identity": "Profile and personal context",
    "preferences": "Choices and response preferences",
    "projects": "Projects and ongoing work",
    "goals": "Plans and objectives",
    "notes": "Other saved notes",
    "facts": "Individual remembered facts",
    "conversation": "Recent conversation records",
}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list, tuple)):
        import json
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def build_memory_cards(memory: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the supported memory.json structure into cards."""
    cards: list[dict[str, Any]] = []
    long_term = memory.get("long_term", {})
    if not isinstance(long_term, dict):
        long_term = {}

    user_name = _as_text(memory.get("user_name"))
    if user_name:
        cards.append({
            "id": "profile:user_name",
            "category": "identity",
            "category_label": CATEGORY_LABELS["identity"],
            "title": "User name",
            "content": user_name,
            "kind": "profile",
        })

    for category, entries in long_term.items():
        if isinstance(entries, dict):
            iterable = entries.items()
        elif isinstance(entries, list):
            iterable = [(f"Item {i + 1}", item) for i, item in enumerate(entries)]
        else:
            iterable = [("Saved item", entries)]
        label = CATEGORY_LABELS.get(category, category.replace("_", " ").title())
        for key, value in iterable:
            content = _as_text(value)
            if not content:
                continue
            cards.append({
                "id": f"long_term:{category}:{key}",
                "category": category,
                "category_label": label,
                "title": _as_text(key) or "Untitled memory",
                "content": content,
                "kind": "long_term",
            })

    facts = memory.get("facts", [])
    if isinstance(facts, list):
        for index, item in enumerate(facts):
            if isinstance(item, dict):
                title = _as_text(item.get("title") or item.get("key") or f"Fact {index + 1}")
                content = _as_text(item.get("content") or item.get("value") or item.get("fact") or item)
            else:
                title, content = f"Fact {index + 1}", _as_text(item)
            if content:
                cards.append({
                    "id": f"fact:{index}",
                    "category": "facts",
                    "category_label": CATEGORY_LABELS["facts"],
                    "title": title,
                    "content": content,
                    "kind": "fact",
                })

    conversation = memory.get("conversation", [])
    if isinstance(conversation, list):
        # Show newest entries first while preserving the original memory file.
        for index, item in reversed(list(enumerate(conversation[-50:]))):
            if isinstance(item, dict):
                title = _as_text(item.get("title") or item.get("role") or f"Conversation {index + 1}")
                content = _as_text(item.get("content") or item.get("text") or item.get("message") or item)
            else:
                title, content = f"Conversation {index + 1}", _as_text(item)
            if content:
                cards.append({
                    "id": f"conversation:{index}",
                    "category": "conversation",
                    "category_label": CATEGORY_LABELS["conversation"],
                    "title": title,
                    "content": content,
                    "kind": "conversation",
                })

    return cards


def build_categories(memory: dict[str, Any]) -> list[dict[str, Any]]:
    """Return visible categories, including custom long-term categories."""
    cards = build_memory_cards(memory)
    counts: dict[str, int] = {}
    for card in cards:
        category = card["category"]
        counts[category] = counts.get(category, 0) + 1

    order = ["identity", "preferences", "projects", "goals", "notes", "facts", "conversation"]
    for category in memory.get("long_term", {}):
        if category not in order:
            order.append(category)
    for category in counts:
        if category not in order:
            order.append(category)

    result = []
    for category in order:
        label = CATEGORY_LABELS.get(category, category.replace("_", " ").title())
        result.append({
            "id": category,
            "label": label,
            "description": CATEGORY_DESCRIPTIONS.get(category, "Saved memories"),
            "count": counts.get(category, 0),
        })
    return result
