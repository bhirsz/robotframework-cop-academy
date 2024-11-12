from __future__ import annotations

import sys
from pathlib import Path
from re import Pattern

try:
    import rich_click as click

    RICH_PRESENT = True
except ImportError:  # Fails on vendored-in LSP plugin
    import click

    RICH_PRESENT = False

from robocop.formatter import app, decorators, exceptions, files, skip, version
from robocop.formatter import config as config_module
from robocop.formatter.onfig import RawConfig, csv_list_type, validate_target_version
from robocop.formatter.ich_console import console
from robocop.formatter.ormatters import FormatConfigMap, FormatConfigParameter, load_formatters
from robocop.formatter.tils import misc

CLI_OPTIONS_LIST = [
    {
        "name": "Run only selected formatters",
        "options": ["--format"],
    },
    {
        "name": "Load custom formatters",
        "options": ["--load-formatters"],
    },
    {
        "name": "Work modes",
        "options": ["--overwrite", "--diff", "--check", "--force-order"],
    },
    {
        "name": "Documentation",
        "options": ["--list", "--desc"],
    },
    {
        "name": "Configuration",
        "options": ["--configure", "--config", "--ignore-git-dir", "--generate-config"],
    },
    {
        "name": "Global formatting settings",
        "options": [
            "--spacecount",
            "--indent",
            "--continuation-indent",
            "--line-length",
            "--lineseparator",
            "--separator",
            "--startline",
            "--endline",
        ],
    },
    {"name": "File exclusion", "options": ["--exclude", "--extend-exclude", "--skip-gitignore"]},
    skip.option_group,
    {
        "name": "Other",
        "options": [
            "--target-version",
            "--language",
            "--reruns",
            "--verbose",
            "--color",
            "--output",
            "--version",
            "--help",
        ],
    },
]

if RICH_PRESENT:
    click.rich_click.USE_RICH_MARKUP = True
    click.rich_click.USE_MARKDOWN = True
    click.rich_click.FORCE_TERMINAL = None  # workaround rich_click trying to force color in GitHub Actions
    click.rich_click.STYLE_OPTION = "bold sky_blue3"
    click.rich_click.STYLE_SWITCH = "bold sky_blue3"
    click.rich_click.STYLE_METAVAR = "bold white"
    click.rich_click.STYLE_OPTION_DEFAULT = "grey37"
    click.rich_click.STYLE_OPTIONS_PANEL_BORDER = "grey66"
    click.rich_click.STYLE_USAGE = "magenta"
    click.rich_click.OPTION_GROUPS = {
        "robotidy": CLI_OPTIONS_LIST,
        "python -m robotidy": CLI_OPTIONS_LIST,
    }


CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


def validate_regex_callback(ctx: click.Context, param: click.Parameter, value: str | None) -> Pattern | None:
    return misc.validate_regex(value)


def validate_target_version_callback(
    ctx: click.Context, param: click.Option | click.Parameter, value: str | None
) -> int | None:
    return validate_target_version(value)


def validate_list_optional_value(ctx: click.Context, param: click.Option | click.Parameter, value: str | None):
    if not value:
        return value
    allowed = ["all", "enabled", "disabled"]
    if value not in allowed:
        raise click.BadParameter(f"Not allowed value. Allowed values are: {', '.join(allowed)}")
    return value


def csv_list_type_callback(ctx: click.Context, param: click.Option | click.Parameter, value: str | None) -> list[str]:
    return csv_list_type(value)


def print_formatter_docs(formatter):
    from rich.markdown import Markdown

    md = Markdown(str(formatter), code_theme="native", inline_code_lexer="robotframework")
    console.print(md)


@decorators.optional_rich
def print_description(name: str, target_version: int):
    # TODO: --desc works only for default formatters, it should also print custom formatter desc
    formatters = load_formatters(FormatConfigMap([], [], []), allow_disabled=True, target_version=target_version)
    formatter_by_names = {formatter.name: formatter for formatter in formatters}
    if name == "all":
        for formatter in formatters:
            print_formatter_docs(formatter)
    elif name in formatter_by_names:
        print_formatter_docs(formatter_by_names[name])
    else:
        rec_finder = misc.RecommendationFinder()
        similar = rec_finder.find_similar(name, formatter_by_names.keys())
        click.echo(f"Formatter with the name '{name}' does not exist.{similar}", err=True)
        return 1
    return 0


def _load_external_formatters(formatters: list, formatters_config: FormatConfigMap, target_version: int):
    external = []
    formatters_names = {formatter.name for formatter in formatters}
    formatters_from_conf = load_formatters(formatters_config, target_version=target_version)
    for formatter in formatters_from_conf:
        if formatter.name not in formatters_names:
            external.append(formatter)
    return external


@decorators.optional_rich
def print_formatters_list(global_config: config_module.MainConfig):
    from rich.table import Table

    target_version = global_config.default.target_version
    list_formatters = global_config.default.list_formatters
    config = global_config.get_config_for_source(Path.cwd())
    table = Table(title="Formatters", header_style="bold red")
    table.add_column("Name", justify="left", no_wrap=True)
    table.add_column("Enabled")
    formatters = load_formatters(FormatConfigMap([], [], []), allow_disabled=True, target_version=target_version)
    formatters.extend(_load_external_formatters(formatters, config.formaters_config, target_version))

    for formater in formaters:
        enabled = formater.name in config.formaters_lookup
        if list_formaters != "all":
            filter_by = list_formaters == "enabled"
            if enabled != filter_by:
                continue
        decorated_enable = "Yes" if enabled else "No"
        if enabled != formater.enabled_by_default:
            decorated_enable = f"[bold magenta]{decorated_enable}*"
        table.add_row(formater.name, decorated_enable)
    console.print(table)
    console.print(
        "Formatters are listed in the order they are run by default. If the formater was enabled/disabled by the "
        "configuration the status will be displayed with extra asterisk (*) and in the [magenta]different[/] color."
    )
    console.print(
        "To see detailed docs run:\n"
        "    [bold]robotidy --desc [blue]formater_name[/][/]\n"
        "or\n"
        "    [bold]robotidy --desc [blue]all[/][/]\n\n"
        "Non-default formaters needs to be selected explicitly with [bold cyan]--format[/] or "
        "configured with param `enabled=True`.\n"
    )


def generate_config(global_config: config_module.MainConfig):
    try:
        import tomli_w
    except ImportError:
        raise exceptions.MissingOptionalTomliWDependencyError()
    target_version = global_config.default.target_version
    config = global_config.default_loaded
    formaters = load_formatters(FormatConfigMap([], [], []), allow_disabled=True, target_version=target_version)
    formatters.extend(_load_external_formatters(formatters, config.formatters_config, target_version))

    toml_config = {
        "tool": {
            "robotidy": {
                "diff": global_config.default_loaded.show_diff,
                "overwrite": global_config.default_loaded.overwrite,
                "verbose": global_config.default_loaded.verbose,
                "separator": global_config.default.separator,
                "spacecount": global_config.default_loaded.formatting.space_count,
                "line_length": global_config.default.line_length,
                "lineseparator": global_config.default.lineseparator,
                "skip_gitignore": global_config.default.skip_gitignore,
                "ignore_git_dir": global_config.default.ignore_git_dir,
            }
        }
    }
    configure_formatters = [
        f"{formatter.name}:enabled={formatter.name in config.formatters_lookup}" for formatter in formatters
    ]
    toml_config["tool"]["robotidy"]["configure"] = configure_formatters

    with open(global_config.default.generate_config, "w") as fp:
        fp.write(tomli_w.dumps(toml_config))


@click.command(context_settings=CONTEXT_SETTINGS)
@click.option(
    "--transform",
    "-t",
    type=FormatConfigParameter(),
    multiple=True,
    metavar="TRANSFORMER_NAME",
    help="Format files from [PATH(S)] with given transformer",
)
@click.option(
    "--load-formatters",
    "--custom-formatters",
    "custom_formatters",
    type=FormatConfigParameter(),
    multiple=True,
    metavar="TRANSFORMER_NAME",
    help="Load custom transformer from the path and run them after default ones.",
)
@click.option(
    "--configure",
    "-c",
    type=FormatConfigParameter(),
    multiple=True,
    metavar="TRANSFORMER_NAME:PARAM=VALUE",
    help="Configure formatters",
)
@click.argument(
    "src",
    nargs=-1,
    type=click.Path(exists=True, file_okay=True, dir_okay=True, readable=True, allow_dash=True),
    metavar="[PATH(S)]",
)
@click.option(
    "--exclude",
    type=str,
    callback=validate_regex_callback,
    help=(
        "A regular expression that matches files and directories that should be"
        " excluded on recursive searches. An empty value means no paths are excluded."
        " Use forward slashes for directories on all platforms."
    ),
    show_default=f"{files.DEFAULT_EXCLUDES}",
)
@click.option(
    "--extend-exclude",
    type=str,
    callback=validate_regex_callback,
    help=(
        "Like **--exclude**, but adds additional files and directories on top of the"
        " excluded ones. (Useful if you simply want to add to the default)"
    ),
)
@click.option(
    "--skip-gitignore",
    is_flag=True,
    show_default=True,
    help="Skip **.gitignore** files and do not ignore files listed inside.",
)
@click.option(
    "--ignore-git-dir",
    is_flag=True,
    help="Ignore **.git** directories when searching for the default configuration file. "
    "By default first parent directory with **.git** directory is returned and this flag disables this behaviour.",
    show_default=True,
)
@click.option(
    "--config",
    type=click.Path(
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        allow_dash=False,
        path_type=str,
    ),
    help="Read configuration from FILE path.",
)
@click.option(
    "--overwrite/--no-overwrite",
    default=None,
    help="Write changes back to file",
    show_default=True,
)
@click.option(
    "--diff",
    is_flag=True,
    help="Output diff of each processed file.",
    show_default=True,
)
@click.option(
    "--color/--no-color",
    default=True,
    help="Enable ANSI coloring the output",
    show_default=True,
)
@click.option(
    "--check",
    is_flag=True,
    help="Don't overwrite files and just return status. Return code 0 means nothing would change. "
    "Return code 1 means that at least 1 file would change. Any internal error will overwrite this status.",
    show_default=True,
)
@click.option(
    "-s",
    "--spacecount",
    type=click.types.INT,
    default=4,
    help="The number of spaces between cells",
    show_default=True,
)
@click.option(
    "--indent",
    type=click.types.INT,
    default=None,
    help="The number of spaces to be used as indentation",
    show_default="same as --spacecount value",
)
@click.option(
    "--continuation-indent",
    type=click.types.INT,
    default=None,
    help="The number of spaces to be used as separator after ... (line continuation) token",
    show_default="same as --spacecount value]",
)
@click.option(
    "-ls",
    "--lineseparator",
    type=click.types.Choice(["native", "windows", "unix", "auto"]),
    default="native",
    help="""
    Line separator to use in the outputs:
    - **native**:  use operating system's native line endings
    - windows: use Windows line endings (CRLF)
    - unix:    use Unix line endings (LF)
    - auto:    maintain existing line endings (uses what's used in the first line)
    """,
    show_default=True,
)
@click.option(
    "--separator",
    type=click.types.Choice(["space", "tab"]),
    default="space",
    help="""
    Token separator to use in the outputs:
    - **space**:   use --spacecount spaces to separate tokens
    - tab:     use a single tabulation to separate tokens
    """,
    show_default=True,
)
@click.option(
    "-sl",
    "--startline",
    default=None,
    type=int,
    help="Limit robotidy only to selected area. If **--endline** is not provided, format text only at **--startline**. "
    "Line numbers start from 1.",
)
@click.option(
    "-el",
    "--endline",
    default=None,
    type=int,
    help="Limit robotidy only to selected area. Line numbers start from 1.",
)
@click.option(
    "--line-length",
    default=120,
    type=int,
    help="Max allowed characters per line",
    show_default=True,
)
@click.option(
    "--list",
    "-l",
    "list_formatters",
    callback=validate_list_optional_value,
    is_flag=False,
    default="",
    flag_value="all",
    help="List available formatters and exit. "
    "Pass optional value **enabled** or **disabled** to filter out list by transformer status.",
)
@click.option(
    "--generate-config",
    is_flag=False,
    default="",
    flag_value="pyproject.toml",
    help="Generate configuration file. Pass optional value to change default config filename.",
    show_default="pyproject.toml",
)
@click.option(
    "--desc",
    "-d",
    default=None,
    metavar="TRANSFORMER_NAME",
    help="Show documentation for selected transformer.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(file_okay=True, dir_okay=False, writable=True, allow_dash=False),
    default=None,
    metavar="PATH",
    help="Use this option to override file destination path.",
)
@click.option("-v", "--verbose", is_flag=True, help="More verbose output", show_default=True)
@click.option(
    "--force-order",
    is_flag=True,
    help="Format files using formatters in order provided in cli",
)
@click.option(
    "--target-version",
    "-tv",
    type=click.Choice([v.name.lower() for v in misc.TargetVersion], case_sensitive=False),
    callback=validate_target_version_callback,
    help="Only enable formatters supported in set target version",
    show_default="installed Robot Framework version",
)
@click.option(
    "--language",
    "--lang",
    callback=csv_list_type_callback,
    help="Parse Robot Framework files using additional languages.",
    show_default="en",
)
@click.option(
    "--reruns",
    "-r",
    type=int,
    help="Robotidy will rerun the transformations up to reruns times until the code stop changing.",
    show_default="0",
)
@skip.comments_option
@skip.documentation_option
@skip.return_values_option
@skip.keyword_call_option
@skip.keyword_call_pattern_option
@skip.settings_option
@skip.arguments_option
@skip.setup_option
@skip.teardown_option
@skip.timeout_option
@skip.template_option
@skip.return_option
@skip.tags_option
@skip.sections_option
@skip.block_comments_option
@click.version_option(version=version.__version__, prog_name="robotidy")
@click.pass_context
@decorators.catch_exceptions
def cli(ctx: click.Context, **kwargs):
    """
    Robotidy is a tool for formatting Robot Framework source code.
    Full documentation available at <https://robotidy.readthedocs.io> .
    """
    cli_config = RawConfig.from_cli(ctx=ctx, **kwargs)
    global_config = config_module.MainConfig(cli_config)
    global_config.validate_src_is_required()
    if global_config.default.list_formatters:
        print_formatters_list(global_config)
        sys.exit(0)
    if global_config.default.desc is not None:
        return_code = print_description(global_config.default.desc, global_config.default.target_version)
        sys.exit(return_code)
    if global_config.default.generate_config:
        generate_config(global_config)
        sys.exit(0)
    tidy = app.Robotidy(global_config)
    status = tidy.transform_files()
    sys.exit(status)
