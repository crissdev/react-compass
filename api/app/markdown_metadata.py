"""Lossless extraction of React docs examples and page context before section splitting."""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import TypedDict

from langchain_core.documents import Document

FENCE_PATTERN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})([^\r\n]*)")
SECTION_PATTERN = re.compile(r"^ {0,3}##[ \t]+", re.MULTILINE)
REFERENCE_PATTERN = re.compile(r"\[(Sandpack|CodeSnippet): ([^\]\s]+)\]")
EXAMPLE_METADATA_KEYS = {"Sandpack": "sandpacks", "CodeSnippet": "code_snippets"}
PAGE_NOTICE_COMPONENTS = {"deprecated": "Deprecated", "experimental": "Experimental"}


class MarkdownMetadata(TypedDict):
    sandpacks: dict[str, dict[str, str]]
    code_snippets: dict[str, dict[str, str]]
    intro: str
    deprecated: str
    experimental: str


@dataclass(frozen=True)
class _Block:
    start: int
    end: int
    body_start: int
    body_end: int
    info: str = ""


def _fenced_blocks(content: str) -> list[_Block]:
    blocks: list[_Block] = []
    opening: tuple[int, int, str, str] | None = None
    offset = 0
    for line in content.splitlines(keepends=True):
        if opening is None:
            match = FENCE_PATTERN.match(line)
            if match and not (match[1][0] == "`" and "`" in match[2]):
                opening = (offset, offset + len(line), match[1], match[2])
        else:
            start, body_start, fence, info = opening
            closing = line.strip()
            indentation = len(line) - len(line.lstrip(" \t"))
            if indentation <= 3 and len(closing) >= len(fence) and set(closing) == {fence[0]}:
                blocks.append(
                    _Block(start, offset + len(line.rstrip("\r\n")), body_start, offset, info)
                )
                opening = None
        offset += len(line)
    if opening is not None:
        start, body_start, _, info = opening
        blocks.append(_Block(start, len(content), body_start, len(content), info))
    return blocks


def _component_blocks(content: str, name: str) -> list[_Block]:
    # Tags inside code are source text, including closing tags in Sandpack files.
    fences = iter(_fenced_blocks(content))
    fence = next(fences, None)
    tag_pattern = re.compile(rf"<(/?){name}\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>")
    blocks: list[_Block] = []
    openings: list[re.Match[str]] = []
    for tag in tag_pattern.finditer(content):
        while fence is not None and fence.end <= tag.start():
            fence = next(fences, None)
        if fence is not None and fence.start <= tag.start() < fence.end:
            continue
        if tag[0].endswith("/>"):
            continue
        if not tag[1]:
            openings.append(tag)
        elif openings:
            opening = openings.pop()
            if not openings:
                blocks.append(_Block(opening.start(), tag.end(), opening.end(), tag.start()))
    return blocks


def _replace_examples(
    content: str, blocks: list[_Block], kind: str, source: str
) -> tuple[str, dict[str, dict[str, str]]]:
    records: dict[str, dict[str, str]] = {}
    parts: list[str] = []
    offset = 0
    for index, block in enumerate(blocks):
        original = content[block.start : block.end]
        identity = json.dumps([source, kind, index, original], ensure_ascii=False)
        reference = hashlib.sha256(identity.encode()).hexdigest()[:16]
        record = {"content": original}
        if kind == "CodeSnippet":
            tokens = block.info.strip().split(maxsplit=1)
            record.update(
                info=block.info,
                language=tokens[0] if tokens else "",
                meta=tokens[1] if len(tokens) > 1 else "",
                code=content[block.body_start : block.body_end],
            )
        records[reference] = record
        parts.extend([content[offset : block.start], f"[{kind}: {reference}]"])
        offset = block.end
    parts.append(content[offset:])
    return "".join(parts), records


def _preamble_components(
    content: str, sandpacks: list[_Block], components: dict[str, str]
) -> dict[str, str]:
    examples = sorted([*sandpacks, *_fenced_blocks(content)], key=lambda block: block.start)
    section_start = len(content)
    for heading in SECTION_PATTERN.finditer(content):
        if not any(block.start <= heading.start() < block.end for block in examples):
            section_start = heading.start()
            break
    preamble = content[:section_start]
    return {
        key: "\n\n".join(
            preamble[block.body_start : block.body_end].strip()
            for block in _component_blocks(preamble, component)
            if not any(example.start <= block.start < example.end for example in examples)
        )
        for key, component in components.items()
    }


def extract_markdown_metadata(content: str, source: str) -> tuple[str, MarkdownMetadata]:
    """Extract Sandpacks first, so their file fences remain part of the example."""
    sandpack_blocks = _component_blocks(content, "Sandpack")
    notices = _preamble_components(content, sandpack_blocks, PAGE_NOTICE_COMPONENTS)
    content, sandpacks = _replace_examples(content, sandpack_blocks, "Sandpack", source)
    content, snippets = _replace_examples(content, _fenced_blocks(content), "CodeSnippet", source)
    intro = _preamble_components(content, [], {"intro": "Intro"})["intro"]
    return content, {
        "sandpacks": sandpacks,
        "code_snippets": snippets,
        "intro": intro,
        "deprecated": notices["deprecated"],
        "experimental": notices["experimental"],
    }


def add_markdown_metadata(documents: list[Document], metadata: MarkdownMetadata) -> None:
    """Store each chunk's examples and shared page context as Chroma-compatible scalars."""
    intro_references = REFERENCE_PATTERN.findall(metadata["intro"])
    for document in documents:
        references = [*intro_references, *REFERENCE_PATTERN.findall(document.page_content)]
        for kind, key in EXAMPLE_METADATA_KEYS.items():
            records = {
                reference: metadata[key][reference]
                for reference_kind, reference in references
                if reference_kind == kind and reference in metadata[key]
            }
            if records:
                document.metadata[key] = json.dumps(records, ensure_ascii=False)
        for key in ("intro", *PAGE_NOTICE_COMPONENTS):
            if metadata[key]:
                document.metadata[key] = metadata[key]
