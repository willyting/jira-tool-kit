"""Command-line entry point.

Errors are reported as a single human-readable line and a non-zero exit.
Tracebacks appear only under --verbose: a stack trace is noise when the actual
problem is an unset environment variable.
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Annotated, Any

import typer
from rich.console import Console

from .aggregate import aggregate
from .client import JiraClient
from .config import load_config
from .done import detect_completions
from .errors import ConfigError, JiraToolError, NotFoundError
from .issues import fetch_candidate_issues
from .report import render
from .sprints import resolve_sprint

app = typer.Typer(add_completion=False, no_args_is_help=True)

# Swapped in tests so the pipeline can run without a live Jira.
client_factory = JiraClient


async def _run(
    sprint_name: str,
    board_id: int | None,
    board_name: str | None,
    verbose: bool,
    console: Console,
) -> None:
    config = load_config()

    client: Any = client_factory(config)
    try:
        resolved_board_id = board_id
        if resolved_board_id is None:
            assert board_name is not None
            boards = await client.list_boards(name=board_name)
            matches = [b for b in boards if str(b.get("name")) == board_name]
            if not matches:
                raise NotFoundError(f"No board named {board_name!r} was found.")
            if len(matches) > 1:
                listed = ", ".join(f"id={b.get('id')}" for b in matches)
                raise ConfigError(
                    f"{len(matches)} boards are named {board_name!r} ({listed}). "
                    "Use --board <id> instead."
                )
            resolved_board_id = int(matches[0]["id"])

        if verbose:
            console.print(f"Resolving sprint {sprint_name!r} on board {resolved_board_id}...")

        sprints = await client.list_sprints(resolved_board_id)
        sprint = resolve_sprint(sprints, sprint_name)

        if verbose:
            console.print(f"Fetching issues for sprint {sprint.id}...")

        candidates = await fetch_candidate_issues(client, sprint.id)

        if verbose:
            console.print(
                f"Reading changelogs for {len(candidates)} candidate issue(s)..."
            )

        categories = await client.get_statuses()
        detection = await detect_completions(
            client, candidates.issues, categories, sprint
        )
        result = aggregate(detection.completions)

        render(
            console,
            sprint,
            result,
            candidates=candidates,
            skipped=detection.skipped,
            verbose=verbose,
        )
    finally:
        await client.aclose()


@app.command()
def main(
    sprint: Annotated[
        str, typer.Option("--sprint", help="Sprint name, e.g. 'Sprint 42'.")
    ],
    board: Annotated[
        int | None,
        typer.Option("--board", help="Board id. Mutually exclusive with --board-name."),
    ] = None,
    board_name: Annotated[
        str | None,
        typer.Option("--board-name", help="Board name. Mutually exclusive with --board."),
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Show progress detail and full tracebacks.")
    ] = False,
) -> None:
    """Total the original estimates of work completed during a Jira sprint."""
    console = Console()
    error_console = Console(stderr=True)

    # Validated before any network call, so a bad invocation costs nothing.
    if board is not None and board_name is not None:
        error_console.print(
            "Error: --board and --board-name are mutually exclusive; supply one."
        )
        raise typer.Exit(code=2)
    if board is None and board_name is None:
        error_console.print(
            "Error: supply a board with either --board <id> or --board-name <name>."
        )
        raise typer.Exit(code=2)

    try:
        asyncio.run(_run(sprint, board, board_name, verbose, console))
    except JiraToolError as exc:
        error_console.print(f"Error: {exc}")
        if verbose:
            error_console.print(traceback.format_exc())
        raise typer.Exit(code=1) from None
    except Exception as exc:  # pragma: no cover - unexpected failures
        error_console.print(f"Unexpected error: {exc}")
        if verbose:
            error_console.print(traceback.format_exc())
        raise typer.Exit(code=1) from None
