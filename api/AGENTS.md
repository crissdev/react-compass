# API agent instructions

## Required verification

After implementing a feature, fixing a bug, or refactoring API code, run these
commands from the `api/` directory before marking the work complete or committing:

1. Format the code: `uv run ruff format .`
2. Verify formatting: `uv run ruff format --check .`
3. Run lint checks: `uv run ruff check .`
4. Run the full test suite: `uv run pytest`

Fix any failures and rerun verification after the final code change. Do not skip
checks, weaken tests, or disable rules to make verification pass.

If a check fails or cannot run, report the failing command and the reason. Do not
mark the implementation complete or commit it until all checks pass.

In the final response, summarize the implementation and report each verification
command and its result. Passing these checks does not replace verifying that the
implemented behavior meets the request.
