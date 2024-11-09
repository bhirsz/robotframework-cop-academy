from pathlib import Path
from typing import Annotated, Optional

from rich import print
import typer

from robocop.config import DEFAULT_ISSUE_FORMAT, Config, ConfigManager, LinterConfig
from robocop.linter.rules import RuleFilter, RuleSeverity, filter_rules_by_category, filter_rules_by_pattern
from robocop.linter.runner import RobocopLinter
from robocop.linter.utils.misc import ROBOCOP_RULES_URL, compile_rule_pattern, get_plural_form  # TODO: move higher up
from robocop.linter.reports import print_reports

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
        show_default=False,
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


def parse_rule_severity(value: str):
    return RuleSeverity.parser(value, rule_severity=False)


@app.command(name="check")
def check_files(
    sources: Annotated[list[Path], typer.Argument(show_default="current directory")] = None,
    include: Annotated[list[str], typer.Option(show_default=False)] = None,
    threshold: Annotated[
        RuleSeverity,
        typer.Option(
            "--threshold", "-t", show_default=RuleSeverity.INFO.value, parser=parse_rule_severity, metavar="I/W/E"
        ),
    ] = None,
    config: config_option = None,
    configure: Annotated[
        list[str],
        typer.Option(
            "--configure",
            "-c",
            help="Configure checker or report with parameter value",
            metavar="rule.param=value",
            show_default=False,
        ),
    ] = None,
    reports: Annotated[
        list[str],
        typer.Option(
            "--reports",
            "-r",
            show_default=False,
            help="Generate reports from reported issues. To list available reports use `list reports` command. "
            "Use `all` to enable all reports.",
        ),
    ] = None,
    issue_format: Annotated[str, typer.Option("--issue-format", show_default=DEFAULT_ISSUE_FORMAT)] = None,
    language: Annotated[
        list[str],
        typer.Option(
            "--language",
            "-l",
            show_default="en",
            metavar="LANG",
            help="Parse Robot Framework files using additional languages.",
        ),
    ] = None,
    ext_rules: Annotated[list[str], typer.Option("--ext-rules", show_default=False)] = None,
    ignore_git_dir: Annotated[bool, typer.Option()] = False,
    skip_gitignore: Annotated[bool, typer.Option()] = False,
    root: project_root_option = None,
) -> None:
    """Lint files."""
    linter_config = LinterConfig(
        configure=configure,
        include=include,
        issue_format=issue_format,
        threshold=threshold,
        ext_rules=ext_rules,
        reports=reports,
    )
    overwrite_config = Config(linter=linter_config, language=language)
    config_manager = ConfigManager(
        sources=sources,
        config=config,
        root=root,
        ignore_git_dir=ignore_git_dir,
        skip_gitignore=skip_gitignore,
        overwrite_config=overwrite_config,
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
    """
    List available rules.

    Use `--filter`` option to list only selected rules:

    > robocop list rules --filter DISABLED

    You can also specify the patterns to filter by:

    > robocop list rules --pattern *var*

    Use `robocop rule rule_name` for more detailed information on the rule.
    The output list is affected by default configuration file (if it is found).
    """
    # TODO: support list-configurables (maybe as separate robocop rule <>)
    # TODO: rich support (colorized enabled, severity etc)
    config_manager = ConfigManager()
    runner = RobocopLinter(config_manager)
    runner.check_for_disabled_rules()
    if filter_pattern:
        filter_pattern = compile_rule_pattern(filter_pattern)
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


@list_app.command(name="reports")
def list_reports(
    enabled: Annotated[
        Optional[bool],
        typer.Option(
            "--enabled/--disabled",
            help="List enabled or disabled reports. Reports configuration will be loaded from the default "
            "configuration file or `--reports`` option.",
            show_default=False,
        ),
    ] = None,
    reports: Annotated[
        list[str],
        typer.Option(
            "--reports",
            "-r",
            show_default=False,
            help="Enable selected reports.",
        ),
    ] = None,
) -> None:
    """List available reports."""
    linter_config = LinterConfig(reports=reports)
    config = Config(linter=linter_config)
    config_manager = ConfigManager(overwrite_config=config)
    runner = RobocopLinter(config_manager)
    print(print_reports(runner.reports, enabled))  # TODO: color etc


@list_app.command(name="formatters")
def list_formatters(
    filter_category: Annotated[
        RuleFilter, typer.Option("--filter", case_sensitive=False, help="Filter formatters by category.")
    ] = RuleFilter.DEFAULT,
    filter_pattern: Annotated[Optional[str], typer.Option("--pattern", help="Filter formatters by pattern")] = None,
) -> None:
    """List available formatters."""
    # We will need ConfigManager later for listing based on configuration


@app.command("rule")
def describe_rule(rule: Annotated[str, typer.Argument(help="Rule name")]):
    """Describe a rule."""
    # TODO load external from cli
    config_manager = ConfigManager()
    runner = RobocopLinter(config_manager)
    if rule not in runner.rules:
        print(f"Rule '{rule}' does not exist.")
        raise typer.Exit(code=2)
    print(runner.rules[rule].description_with_configurables)


def main() -> None:
    app()
