"""Command-line entry point.

Errors are reported as a single human-readable line and a non-zero exit.
Tracebacks appear only under --verbose. If a run fails after writing, what was
created is listed first, so nothing made in Jira goes unreported.
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from typing import Annotated, Any

import typer
from rich.console import Console

from .client import JiraClient
from .config import load_config
from .errors import JiraToolError, PartialWriteError
from .execute import execute_plan
from .plan import build_plan
from .report import render_created, render_plan, render_result
from .targets import DEFAULT_BOARD_NAME, DEFAULT_PARENT_ISSUE_TYPE, resolve_target

app = typer.Typer(add_completion=False, no_args_is_help=True)

# Swapped in tests so the pipeline can run without a live Jira.
client_factory = JiraClient


def is_interactive() -> bool:
    """Seam for tests: CliRunner's stdin is never a TTY."""
    return sys.stdin.isatty()


def _parse_sprint(raw: str) -> int | None:
    try:
        value = int(raw.strip())
    except ValueError:
        return None
    return value if value > 0 else None


async def _run(
    *,
    sprint_number: int,
    version: str,
    board_id: int | None,
    board_name: str,
    project: str | None,
    issue_type: str,
    dry_run: bool,
    yes: bool,
    verbose: bool,
    console: Console,
    error_console: Console,
) -> int:
    config = load_config()
    client: Any = client_factory(config)
    try:
        if verbose:
            console.print("Resolving board, sprint, project and issue types...")
        target = await resolve_target(
            client,
            sprint_number=sprint_number,
            board_id=board_id,
            board_name=board_name,
            project=project,
            parent_type_name=issue_type,
        )
        plan = await build_plan(
            client, target, sprint_number=sprint_number, version=version
        )
        render_plan(console, plan)

        if plan.to_create == 0:
            console.print("Release task already complete. Nothing to create.")
            return 0
        if dry_run:
            console.print(f"Dry run: {plan.to_create} issue(s) would be created.")
            return 0
        if not yes:
            if not is_interactive():
                error_console.print(
                    "Error: refusing to create issues without confirmation; "
                    "stdin is not a terminal. Pass --yes."
                )
                return 1
            if not typer.confirm(f"Create {plan.to_create} issue(s)?", default=False):
                console.print("Nothing was created.")
                return 0

        try:
            result = await execute_plan(client, plan)
        except PartialWriteError as exc:
            render_created(console, exc.created, config.base_url)
            raise

        render_result(console, result, config.base_url, target.sprint_name)
        return 0
    finally:
        await client.aclose()


@app.command()
def main(
    sprint: Annotated[
        str, typer.Option("--sprint", help="Sprint number N, for sprint 'reseller N'.")
    ],
    version: Annotated[
        str, typer.Option("--version", help="Release version, e.g. 2.14.0.")
    ],
    board: Annotated[
        int | None,
        typer.Option("--board", help="Board id. Replaces --board-name."),
    ] = None,
    board_name: Annotated[
        str | None,
        typer.Option("--board-name", help=f"Board name (default: {DEFAULT_BOARD_NAME})."),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", help="Project key, if the board spans several."),
    ] = None,
    issue_type: Annotated[
        str, typer.Option("--issue-type", help="Parent issue type name.")
    ] = DEFAULT_PARENT_ISSUE_TYPE,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the plan; create nothing.")
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", help="Create without asking for confirmation.")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Show progress detail and full tracebacks.")
    ] = False,
) -> None:
    """Create 'release N ------- VERSION ---...' and its checklist subtasks in sprint 'reseller N'."""
    console = Console()
    error_console = Console(stderr=True)

    # Validated before any network call, so a bad invocation costs nothing.
    sprint_number = _parse_sprint(sprint)
    if sprint_number is None:
        error_console.print(f"Error: --sprint must be a positive integer, got {sprint!r}.")
        raise typer.Exit(code=2)
    if not version.strip():
        error_console.print("Error: --version must not be empty.")
        raise typer.Exit(code=2)
    if "\n" in version or "\r" in version:
        error_console.print("Error: --version must not contain a line break.")
        raise typer.Exit(code=2)
    if board is not None and board_name is not None:
        error_console.print(
            "Error: --board and --board-name are mutually exclusive; supply one."
        )
        raise typer.Exit(code=2)

    try:
        code = asyncio.run(
            _run(
                sprint_number=sprint_number,
                version=version,
                board_id=board,
                board_name=board_name or DEFAULT_BOARD_NAME,
                project=project,
                issue_type=issue_type,
                dry_run=dry_run,
                yes=yes,
                verbose=verbose,
                console=console,
                error_console=error_console,
            )
        )
    except JiraToolError as exc:
        error_console.print(f"Error: {exc}", markup=False, soft_wrap=True)
        if verbose:
            error_console.print(traceback.format_exc(), markup=False)
        raise typer.Exit(code=1) from None
    except Exception as exc:  # pragma: no cover - unexpected failures
        error_console.print(f"Unexpected error: {exc}", markup=False)
        if verbose:
            error_console.print(traceback.format_exc(), markup=False)
        raise typer.Exit(code=1) from None

    raise typer.Exit(code=code)
