from pathlib import Path
from typing import Annotated, Optional

import typer

from robocop.config import ConfigManager
from robocop.linter.rules import RuleFilter, filter_rules_by_category, filter_rules_by_pattern
from robocop.linter.runner import RobocopLinter
from robocop.linter.utils.misc import ROBOCOP_RULES_URL, get_plural_form  # TODO: move higher up

app = typer.Typer(
    help="Static code analysis tool (linter) and code formatter for Robot Framework. "
    "Full documentation available at https://robocop.readthedocs.io .",
    rich_markup_mode="rich",
)
list_app = typer.Typer(help="List available rules, reports or formatters.")
app.add_typer(list_app, name="list")


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
    runner = RobocopLinter(config_manager)
    runner.run()


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


@list_app.command(name="rules")
def list_rules(
    filter_category: Annotated[
        RuleFilter, typer.Option("--filter", case_sensitive=False, help="Filter rules by category.")
    ] = RuleFilter.DEFAULT,
    filter_pattern: Annotated[Optional[str], typer.Option("--pattern", help="Filter rules by pattern")] = None,
) -> None:
    """List available rules."""
    # TODO: support list-configurables (maybe as separate robocop rule <>)
    # TODO: rich support (colorized enabled, severity etc)
    config_manager = ConfigManager()
    runner = RobocopLinter(config_manager)
    if filter_pattern:
        rules = filter_rules_by_pattern(runner.rules, filter_pattern)
    else:
        rules = filter_rules_by_category(runner.rules, filter_category)
    severity_counter = {"E": 0, "W": 0, "I": 0}
    for rule in rules:
        print(rule)
        severity_counter[rule.severity.value] += 1
    configurable_rules_sum = sum(severity_counter.values())
    plural = get_plural_form(configurable_rules_sum)
    print(
        f"\nAltogether {configurable_rules_sum} rule{plural} with following severity:\n"
        f"    {severity_counter['E']} error rule{get_plural_form(severity_counter['E'])},\n"
        f"    {severity_counter['W']} warning rule{get_plural_form(severity_counter['W'])},\n"
        f"    {severity_counter['I']} info rule{get_plural_form(severity_counter['I'])}.\n"
    )
    print(f"Visit {ROBOCOP_RULES_URL.format(version='stable')} page for detailed documentation.")


@list_app.command(name="formatters")
def list_formatters(
    filter_category: Annotated[
        RuleFilter, typer.Option("--filter", case_sensitive=False, help="Filter formatters by category.")
    ] = RuleFilter.DEFAULT,
    filter_pattern: Annotated[Optional[str], typer.Option("--pattern", help="Filter formatters by pattern")] = None,
) -> None:
    """List available formatters."""
    # We will need ConfigManager later for listing based on configuration


def main() -> None:
    app()
