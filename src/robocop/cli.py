from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from robocop import config
from robocop.formatter.runner import RobocopFormatter
from robocop.linter.reports import print_reports
from robocop.linter.rules import RuleFilter, RuleSeverity, filter_rules_by_category, filter_rules_by_pattern
from robocop.linter.runner import RobocopLinter
from robocop.linter.utils.misc import ROBOCOP_RULES_URL, compile_rule_pattern, get_plural_form  # TODO: move higher up

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
        "--config",
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
    include: Annotated[list[str], typer.Option("--include", "-i", show_default=str(config.DEFAULT_INCLUDE))] = None,
    extend_include: Annotated[list[str], typer.Option("--extend-include", show_default=False)] = None,
    exclude: Annotated[list[str], typer.Option("--exclude", "-e", show_default=str(config.DEFAULT_EXCLUDE))] = None,
    extend_exclude: Annotated[list[str], typer.Option("--extend-exclude", show_default=False)] = None,
    select: Annotated[list[str], typer.Option("--select", "-s", show_default=False)] = None,
    ignore: Annotated[list[str], typer.Option("--ignore", "-ig", show_default=False)] = None,
    threshold: Annotated[
        RuleSeverity,
        typer.Option(
            "--threshold", "-t", show_default=RuleSeverity.INFO.value, parser=parse_rule_severity, metavar="I/W/E"
        ),
    ] = None,
    configuration_file: config_option = None,
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
    issue_format: Annotated[str, typer.Option("--issue-format", show_default=config.DEFAULT_ISSUE_FORMAT)] = None,
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
    persistent: Annotated[
        bool, typer.Option(help="Use this flag to save Robocop reports in cache directory for later comparison.")
    ] = None,
    compare: Annotated[
        bool, typer.Option(help="Compare reports results with previous results (saved with --persistent)")
    ] = None,
    exit_zero: Annotated[
        bool,
        typer.Option(help="Always exit with 0 unless Robocop terminates abnormally.", show_default="--no-exit-zero"),
    ] = None,
    root: project_root_option = None,
) -> None:
    """Lint files."""
    linter_config = config.LinterConfig(
        configure=configure,
        select=select,
        ignore=ignore,
        issue_format=issue_format,
        threshold=threshold,
        ext_rules=ext_rules,
        reports=reports,
        persistent=persistent,
        compare=compare,
    )
    file_filters = config.FileFiltersOptions(
        include=include, extend_include=extend_include, exclude=exclude, extend_exclude=extend_exclude
    )
    overwrite_config = config.Config(
        linter=linter_config, formatter=None, file_filters=file_filters, language=language, exit_zero=exit_zero
    )
    config_manager = config.ConfigManager(
        sources=sources,
        config=configuration_file,
        root=root,
        ignore_git_dir=ignore_git_dir,
        skip_gitignore=skip_gitignore,
        overwrite_config=overwrite_config,
    )
    runner = RobocopLinter(config_manager)
    runner.run()


@app.command(name="format")
def format_files(
    sources: Annotated[list[Path], typer.Argument(show_default="current directory")] = None,
    select: Annotated[
        list[str], typer.Option(show_default=False, metavar="FORMATTER", help="Select formatters to run.")
    ] = None,
    custom_formatters: Annotated[
        list[str], typer.Option(show_default=False, metavar="FORMATTER", help="Run custom formatters.")
    ] = None,
    include: Annotated[list[str], typer.Option("--include", "-i", show_default=str(config.DEFAULT_INCLUDE))] = None,
    extend_include: Annotated[list[str], typer.Option("--extend-include", show_default=False)] = None,
    exclude: Annotated[list[str], typer.Option("--exclude", "-e", show_default=str(config.DEFAULT_EXCLUDE))] = None,
    extend_exclude: Annotated[list[str], typer.Option("--extend-exclude", show_default=False)] = None,
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
    configuration_file: config_option = None,
    overwrite: bool = None,
    diff: bool = None,
    check: bool = None,
    output: Path = None,
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
    space_count: Annotated[int, typer.Option(show_default="4")] = None,
    indent: Annotated[int, typer.Option(show_default="same as space-count")] = None,
    continuation_indent: Annotated[int, typer.Option(show_default="same as space-count")] = None,
    line_length: Annotated[int, typer.Option(show_default="120")] = None,
    separator: Annotated[str, typer.Option(show_default="space")] = None,
    line_ending: Annotated[str, typer.Option(show_default="native")] = None,
    start_line: Annotated[int, typer.Option(show_default=False)] = None,
    end_line: Annotated[int, typer.Option(show_default=False)] = None,
    target_version: Annotated[config.TargetVersion, typer.Option(case_sensitive=False)] = None,
    ignore_git_dir: Annotated[bool, typer.Option()] = False,
    skip_gitignore: Annotated[bool, typer.Option()] = False,
    root: project_root_option = None,
) -> None:
    """Format files."""
    whitespace_config = config.WhitespaceConfig(
        space_count=space_count,  # TODO
        indent=indent,
        continuation_indent=continuation_indent,
        line_ending=line_ending,
        separator=separator,
        line_length=line_length,
    )
    formatter_config = config.FormatterConfig(
        select=select,
        custom_formatters=custom_formatters,
        whitespace_config=whitespace_config,
        configure=configure,
        overwrite=overwrite,
        output=output,
        show_diff=diff,
        check=check,
        start_line=start_line,
        end_line=end_line,
        target_version=target_version,
    )
    file_filters = config.FileFiltersOptions(
        include=include, extend_include=extend_include, exclude=exclude, extend_exclude=extend_exclude
    )
    overwrite_config = config.Config(
        formatter=formatter_config, linter=None, language=language, file_filters=file_filters
    )
    config_manager = config.ConfigManager(
        sources=sources,
        config=configuration_file,
        root=root,
        ignore_git_dir=ignore_git_dir,
        skip_gitignore=skip_gitignore,
        overwrite_config=overwrite_config,
    )
    runner = RobocopFormatter(config_manager)
    runner.run()


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
    console = Console(soft_wrap=True)
    config_manager = config.ConfigManager()
    runner = RobocopLinter(config_manager)
    runner.check_for_disabled_rules()
    if filter_pattern:
        filter_pattern = compile_rule_pattern(filter_pattern)
        rules = filter_rules_by_pattern(runner.rules, filter_pattern)
    else:
        rules = filter_rules_by_category(runner.rules, filter_category)
    severity_counter = {"E": 0, "W": 0, "I": 0}
    for rule in rules:
        console.print(str(rule))
        severity_counter[rule.severity.value] += 1
    configurable_rules_sum = sum(severity_counter.values())
    plural = get_plural_form(configurable_rules_sum)
    console.print(
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
    console = Console(soft_wrap=True)
    linter_config = config.LinterConfig(reports=reports)
    overwrite_config = config.Config(linter=linter_config)
    config_manager = config.ConfigManager(overwrite_config=overwrite_config)
    runner = RobocopLinter(config_manager)
    console.print(print_reports(runner.reports, enabled))  # TODO: color etc


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
def describe_rule(rule: Annotated[str, typer.Argument(help="Rule name")]) -> None:
    """Describe a rule."""
    # TODO load external from cli
    console = Console(soft_wrap=True)
    config_manager = config.ConfigManager()
    runner = RobocopLinter(config_manager)
    if rule not in runner.rules:
        console.print(f"Rule '{rule}' does not exist.")
        raise typer.Exit(code=2)
    console.print(runner.rules[rule].description_with_configurables)


def main() -> None:
    app()
