import pytest

from app.citations import validate_citations


@pytest.mark.parametrize(
    "message",
    [
        "State updates render [1]. Updaters use pending state [1][2].",
        "An explanation without citations.",
        "Use `[99]` or ``values[99]`` in code [1].",
        "Use `<Sandpack>[99]</Sandpack>` literally [1].",
        "```js\nconst values = [99];\n```\n\nState [1].",
        "~~~js\nconst values = [99];\n~~~\n\nState [1].",
        "    const values = [99];\n\nState [1].",
        r"Escaped \[99] and \[99\] are literal text [1].",
        "[99](https://react.dev) and [docs [99]](https://react.dev) [1].",
        "[docs][99]\n\n[99]: https://react.dev\n\nState [1].",
        "![Preview [99]](https://react.dev/image.png) [1].",
        "<Sandpack>\n\n```js\nconst values = [99];\n```\n\n</Sandpack>\nState [1].",
    ],
)
def test_validates_prose_citations_without_rejecting_code_or_links(message: str) -> None:
    validate_citations(message, {1, 2})


@pytest.mark.parametrize(
    "message",
    [
        "An unknown source [99].",
        "A zero source [0].",
        "Adjacent citations [1][99].",
        "**An unknown source [99].**",
        "<Sandpack>\n\n```js\nconst values = [99];\n```\n\n</Sandpack>\nUnknown [99].",
        "<sandpack>\n\n```js\nconst values = [99];\n```\n\n</sandpack>\nUnknown [99].",
    ],
)
def test_rejects_unavailable_prose_citations(message: str) -> None:
    with pytest.raises(ValueError, match="Answer cites unavailable sources"):
        validate_citations(message, {1, 2})
