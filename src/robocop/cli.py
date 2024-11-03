from __future__ import annotations
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from robocop.config import ConfigManager
from robocop.linter.runner import Linter

app = typer.Typer(
    help="Static code analysis tool (linter) and code formatter for Robot Framework. "
    "Full documentation available at https://robocop.readthedocs.io .",
    rich_markup_mode="rich",
)


config_option = Annotated[
    Path,
    typer.Option(
        help="Path to configuration file. It will overridden any configuration file found in the project.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
]
project_root_option = Annotated[
    Path,
    typer.Option(
        help="Project root directory. It is used to find default configuration directory",
        show_default="Automatically found from the sources and current working directory.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
    ),
]


class ListResource(Enum):
    rules = "rules"
    reports = "reports"
    formatters = "formatters"


@app.command(name="check")
def check_files(
    config: config_option = None,
    ignore_git_dir: Annotated[bool, typer.Option()] = False,
    skip_gitignore: Annotated[bool, typer.Option()] = False,
    root: project_root_option = None,
) -> None:
    """Lint files."""
    config_manager = ConfigManager(
        config=config, root=root, ignore_git_dir=ignore_git_dir, skip_gitignore=skip_gitignore
    )


@app.command(name="format")
def format_files(
    config: config_option = None,
    ignore_git_dir: Annotated[bool, typer.Option()] = False,
    skip_gitignore: Annotated[bool, typer.Option()] = False,
    root: project_root_option = None,
) -> None:
    """Format files."""
    config_manager = ConfigManager(
        config=config, root=root, ignore_git_dir=ignore_git_dir, skip_gitignore=skip_gitignore
    )


@app.command(name="list")
def list_rules_or_formatters(
    resource: Annotated[ListResource, typer.Argument(show_default=False)],
    filter_pattern: Annotated[str, typer.Argument(help="Filter list with pattern.")] = None,
) -> None:
    """List available rules or formatters."""
    # We will need ConfigManager later for listing based on configuration
    if resource == ListResource.rules:
        runner = Linter()


# list configurables, reports, rules, formatters


def main() -> None:
    app()
