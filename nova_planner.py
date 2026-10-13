
"""NOVA task planner.

Creates small, allowlisted computer-action plans.
This module does not execute arbitrary code.
"""

import re
from urllib.parse import quote_plus

from nova_computer import (
    APP_ALIASES,
    WEBSITE_ALIASES,
    FOLDER_ALIASES,
)


def _normalize(text):
    text = text.strip().lower()
    text = re.sub(r"[.!?,]+$", "", text)
    return re.sub(r"\s+", " ", text)


def _is_allowed_target(target):
    target = _normalize(target)

    return (
        target in APP_ALIASES
        or target in WEBSITE_ALIASES
        or target in FOLDER_ALIASES
    )


def build_computer_plan(user_input):
    """Return a list of approved computer commands, or None.

    None means this planner does not recognize the request.
    """

    if not isinstance(user_input, str) or not user_input.strip():
        return None

    original = user_input.strip()

    # Example: "유튜브에서 Python 강좌 검색해줘"
    youtube_search = re.match(
        r"^(?:유튜브|youtube)(?:에서|에)?\s+(.+?)"
        r"\s+(?:검색해\s*줘|검색해|검색|찾아\s*줘)$",
        original,
        flags=re.IGNORECASE,
    )

    if youtube_search:
        query = youtube_search.group(1).strip()

        if not query:
            return None

        url = (
            "https://www.youtube.com/results?search_query="
            + quote_plus(query)
        )

        return [f"열어줘 {url}"]

    # Example: "메모장 열고 계산기 열어줘"
    compound = re.match(
        r"^(.+?)\s+열고\s+(.+?)\s+(?:열어\s*줘|열어)$",
        original,
        flags=re.IGNORECASE,
    )

    if compound:
        first = compound.group(1).strip()
        second = compound.group(2).strip()

        if not (
            _is_allowed_target(first)
            and _is_allowed_target(second)
        ):
            return None

        return [
            f"열어줘 {first}",
            f"열어줘 {second}",
        ]

    return None
