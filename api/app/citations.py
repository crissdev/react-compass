"""Validate bare citation numbers without interpreting code or links as citations."""

import re
from collections.abc import Collection

from markdown_it import MarkdownIt

# Keep escaped brackets separate from ordinary text so they are not citations.
_MARKDOWN = MarkdownIt("commonmark").disable("text_join")
_CITATION = re.compile(r"\[([0-9]+)\]")
_SANDPACK_TAG = re.compile(r"</?Sandpack\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>", re.IGNORECASE)


def validate_citations(message: str, available: Collection[int]) -> None:
    # The UI extracts Sandpacks before rendering prose. Their closing tags must
    # not cause Markdown's HTML blocks to hide subsequent prose from validation.
    markdown = _SANDPACK_TAG.sub("", message)
    invalid: set[int] = set()
    for block in _MARKDOWN.parse(markdown):
        link_depth = 0
        for token in block.children or []:
            if token.type == "link_open":
                link_depth += 1
            elif token.type == "link_close":
                link_depth -= 1
            elif token.type == "text" and link_depth == 0:
                invalid.update(
                    int(number)
                    for number in _CITATION.findall(token.content)
                    if int(number) not in available
                )
    if invalid:
        numbers = ", ".join(str(number) for number in sorted(invalid))
        raise ValueError(f"Answer cites unavailable sources: {numbers}")
