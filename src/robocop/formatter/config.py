from __future__ import annotations

import copy
import dataclasses
import os
import re
import sys
from collections import namedtuple
from dataclasses import dataclass, field
from pathlib import Path
from re import Pattern

try:
    from robot.api import Languages  # RF 6.0
except ImportError:
    Languages = None

import click
from click.core import ParameterSource

from robocop.formatter import exceptions, files, skip
from robocop.formatter.formatters import FormatConfig, FormatConfigMap, convert_format_config, load_formatters
from robocop.formatter.utils import misc


class FormattingConfig:
    def __init__(
        self,
        space_count: int,
        indent: int | None,
        continuation_indent: int | None,
        line_sep: str,
        start_line: int | None,
        end_line: int | None,
        separator: str,
        line_length: int,
    ):
        self.start_line = start_line
        self.end_line = end_line
        self.space_count = space_count
        self.line_length = line_length

        if indent is None:
            indent = space_count
        if continuation_indent is None:
            continuation_indent = space_count

        if separator == "space":
            self.separator = " " * space_count
            self.indent = " " * indent
            self.continuation_indent = " " * continuation_indent
        elif separator == "tab":
            self.separator = "\t"
            self.indent = "\t"
            self.continuation_indent = "\t"

        self.line_sep = self.get_line_sep(line_sep)

    @staticmethod
    def get_line_sep(line_sep):
        if line_sep == "windows":
            return "\r\n"
        if line_sep == "unix":
            return "\n"
        if line_sep == "auto":
            return "auto"
        return os.linesep


def validate_target_version(value: str | None) -> int | None:
    if value is None:
        return misc.ROBOT_VERSION.major
    try:
        target_version = misc.TargetVersion[value.upper()].value
    except KeyError:
        versions = ", ".join(ver.value for ver in misc.TargetVersion)
        raise click.BadParameter(f"Invalid target Robot Framework version: '{value}' is not one of {versions}")
    if target_version > misc.ROBOT_VERSION.major:
        raise click.BadParameter(
            f"Target Robot Framework version ({target_version}) should not be higher than "
            f"installed version ({misc.ROBOT_VERSION})."
        )
    return target_version


def csv_list_type(value: str | None) -> list[str]:
    if not value:
        return []
    return value.split(",")


def convert_formatters_config(
    param_name: str,
    config: dict,
    force_included: bool = False,
    custom_formatter: bool = False,
    is_config: bool = False,
) -> list[FormatConfig]:
    return [
        FormatConfig(tr, force_include=force_included, custom_formatter=custom_formatter, is_config=is_config)
        for tr in config.get(param_name, ())
    ]


def str_to_bool(v):
    if isinstance(v, bool):
        return v
    return v.lower() in ("yes", "true", "1")


def map_class_fields_with_their_types(cls):
    """Returns map of dataclass attributes with their types."""
    fields = dataclasses.fields(cls)
    return {field.name: field.type for field in fields}


SourceAndConfig = namedtuple("SourceAndConfig", "source config")


@dataclass
class RawConfig:
    """Configuration read directly from cli or configuration file."""

    format: list[FormatConfig] = field(default_factory=list)
    custom_formatters: list[FormatConfig] = field(default_factory=list)
    configure: list[FormatConfig] = field(default_factory=list)
    src: tuple[str, ...] = None
    exclude: Pattern = re.compile(files.DEFAULT_EXCLUDES)
    extend_exclude: Pattern = None
    skip_gitignore: bool = False
    overwrite: bool = False
    diff: bool = False
    color: bool = True
    check: bool = False
    spacecount: int = 4
    indent: int = None
    continuation_indent: int = None
    lineseparator: str = "native"
    verbose: bool = False
    config: str = None
    config_path: Path = None
    separator: str = "space"
    startline: int = None
    endline: int = None
    line_length: int = 120
    list_formatters: str = ""
    generate_config: str = ""
    desc: str = None
    output: Path = None
    force_order: bool = False
    target_version: int = misc.ROBOT_VERSION.major
    language: list[str] = field(default_factory=list)
    reruns: int = 0
    ignore_git_dir: bool = False
    skip_comments: bool = False
    skip_documentation: bool = False
    skip_return_values: bool = False
    skip_keyword_call: list[str] = None
    skip_keyword_call_pattern: list[str] = None
    skip_settings: bool = False
    skip_arguments: bool = False
    skip_setup: bool = False
    skip_teardown: bool = False
    skip_timeout: bool = False
    skip_template: bool = False
    skip_return: bool = False
    skip_tags: bool = False
    skip_block_comments: bool = False
    skip_sections: str = ""
    defined_in_cli: set = field(default_factory=set)
    defined_in_config: set = field(default_factory=set)

    @classmethod
    def from_cli(cls, ctx: click.Context, **kwargs):
        """Creates RawConfig instance while saving which options were supplied from CLI."""
        defined_in_cli = set()
        for option in kwargs:
            if ctx.get_parameter_source(option) == ParameterSource.COMMANDLINE:
                defined_in_cli.add(option)
        return cls(**kwargs, defined_in_cli=defined_in_cli)

    def from_config_file(self, config: dict, config_path: Path) -> RawConfig:
        """
        Creates new RawConfig instance from dictionary.

        Dictionary key:values needs to be normalized and parsed to correct types.
        """
        options_map = map_class_fields_with_their_types(self)
        parsed_config = {"defined_in_config": {"defined_in_config", "config_path"}, "config_path": config_path}
        for key, value in config.items():
            # workaround to be able to use two option names for same action - backward compatibility change
            if key == "load_formatters":
                key = "custom_formatters"
            if key not in options_map:
                raise exceptions.NoSuchOptionError(key, list(options_map.keys())) from None
            value_type = options_map[key]
            if value_type == "bool":  # will not be required for basic types after Python 3.9
                parsed_config[key] = str_to_bool(value)
            elif key == "target_version":
                parsed_config[key] = validate_target_version(value)
            elif key == "language":
                parsed_config[key] = csv_list_type(value)
            elif value_type == "int":
                parsed_config[key] = int(value)
            elif value_type == "list[FormatConfig]":
                parsed_config[key] = [convert_format_config(val, key) for val in value]
            elif key == "src":
                parsed_config[key] = tuple(value)
            elif value_type in ("Pattern", Pattern):  # future typing for 3.8 provides type as str
                parsed_config[key] = misc.validate_regex(value)
            else:
                parsed_config[key] = value
            parsed_config["defined_in_config"].add(key)
        from_config = RawConfig(**parsed_config)
        return self.merge_with_config_file(from_config)

    def merge_with_config_file(self, config: RawConfig) -> RawConfig:
        """
        Merge cli config with the configuration file config.

        Use configuration file parameter value only if it was not defined in the cli already.
        """
        merged = copy.deepcopy(self)
        if not config:
            return merged
        overwrite_params = config.defined_in_config - self.defined_in_cli
        for param in overwrite_params:
            merged.__dict__[param] = config.__dict__[param]
        return merged


class MainConfig:
    """Main configuration file which contains default configuration and map of sources and their configurations."""

    def __init__(self, cli_config: RawConfig):
        self.loaded_configs = {}
        self.default = self.load_config_from_option(cli_config)
        self.default_loaded = Config.from_raw_config(self.default)
        self.sources = self.get_sources(self.default.src)

    def validate_src_is_required(self):
        if self.sources or self.default.list_formatters or self.default.desc or self.default.generate_config:
            return
        print("No source path provided. Run robotidy --help to see how to use robotidy")
        sys.exit(1)

    @staticmethod
    def load_config_from_option(cli_config: RawConfig) -> RawConfig:
        """If there is config path passed from cli, load it and overwrite default config."""
        if cli_config.config:
            config_path = Path(cli_config.config)
            config_file = files.read_pyproject_config(config_path)
            cli_config = cli_config.from_config_file(config_file, config_path)
        return cli_config

    def get_sources(self, sources: tuple[str, ...]) -> tuple[str, ...] | None:
        """
        Get list of sources to be formated by Robotidy.

        If the sources tuple is empty, look for most common configuration file and load sources from there.
        """
        if sources:
            return sources
        src = Path().resolve()
        config_path = files.find_source_config_file(src, self.default.ignore_git_dir)
        if not config_path:
            return None
        config = files.read_pyproject_config(config_path)
        if not config or "src" not in config:
            return None
        raw_config = self.default.from_config_file(config, config_path)
        loaded_config = Config.from_raw_config(raw_config)
        self.loaded_configs[str(loaded_config.config_directory)] = loaded_config
        return tuple(config["src"])

    def get_config_for_source(self, source: Path):
        config_path = files.find_source_config_file(source, self.default.ignore_git_dir)
        if config_path is None:
            return self.default_loaded
        if str(config_path.parent) in self.loaded_configs:
            return self.loaded_configs[str(config_path.parent)]
        config_file = files.read_pyproject_config(config_path)
        raw_config = self.default.from_config_file(config_file, config_path)
        loaded_config = Config.from_raw_config(raw_config)
        self.loaded_configs[str(loaded_config.config_directory)] = loaded_config
        return loaded_config


class Config:
    """Configuration after loading dynamic attributes like formatter list."""

    def __init__(
        self,
        formatting: FormattingConfig,
        skip,
        formatters_config: FormatConfigMap,
        overwrite: bool,
        show_diff: bool,
        verbose: bool,
        check: bool,
        output: Path | None,
        force_order: bool,
        target_version: int,
        color: bool,
        language: list[str] | None,
        reruns: int,
        config_path: Path | None,
    ):
        self.formatting = formatting
        self.overwrite = self.set_overwrite_mode(overwrite, check)
        self.show_diff = show_diff
        self.verbose = verbose
        self.check = check
        self.output = output
        self.color = self.set_color_mode(color)
        self.reruns = reruns
        self.config_directory = config_path.parent if config_path else None
        self.language = self.get_languages(language)
        self.formatters = []
        self.formatters_lookup = dict()
        self.formatters_config = formatters_config
        self.load_formatters(formatters_config, force_order, target_version, skip)

    @staticmethod
    def get_languages(lang):
        if Languages is None:
            return None
        return Languages(lang)

    @staticmethod
    def set_overwrite_mode(overwrite: bool, check: bool) -> bool:
        if overwrite is None:
            return not check
        return overwrite

    @staticmethod
    def set_color_mode(color: bool) -> bool:
        if not color:
            return color
        return "NO_COLOR" not in os.environ

    @classmethod
    def from_raw_config(cls, raw_config: RawConfig):
        skip_config = skip.SkipConfig(
            documentation=raw_config.skip_documentation,
            return_values=raw_config.skip_return_values,
            keyword_call=raw_config.skip_keyword_call,
            keyword_call_pattern=raw_config.skip_keyword_call_pattern,
            settings=raw_config.skip_settings,
            arguments=raw_config.skip_arguments,
            setup=raw_config.skip_setup,
            teardown=raw_config.skip_teardown,
            template=raw_config.skip_template,
            timeout=raw_config.skip_timeout,
            return_statement=raw_config.skip_return,
            tags=raw_config.skip_tags,
            comments=raw_config.skip_comments,
            block_comments=raw_config.skip_block_comments,
            sections=raw_config.skip_sections,
        )

        formatting = FormattingConfig(
            space_count=raw_config.spacecount,
            indent=raw_config.indent,
            continuation_indent=raw_config.continuation_indent,
            line_sep=raw_config.lineseparator,
            start_line=raw_config.startline,
            separator=raw_config.separator,
            end_line=raw_config.endline,
            line_length=raw_config.line_length,
        )

        formatters_config = FormatConfigMap(raw_config.format, raw_config.custom_formatters, raw_config.configure)

        if raw_config.verbose and raw_config.config_path:
            click.echo(f"Loaded configuration from {raw_config.config_path}")

        return cls(
            formatting=formatting,
            skip=skip_config,
            formatters_config=formatters_config,
            overwrite=raw_config.overwrite,
            show_diff=raw_config.diff,
            verbose=raw_config.verbose,
            check=raw_config.check,
            output=raw_config.output,
            force_order=raw_config.force_order,
            target_version=raw_config.target_version,
            color=raw_config.color,
            language=raw_config.language,
            reruns=raw_config.reruns,
            config_path=raw_config.config_path,
        )

    def load_formatters(self, formaters_config: FormatConfigMap, force_order, target_version, skip):
        # Workaround to pass configuration to formater before the instance is created
        if "GenerateDocumentation" in formaters_config.formatters:
            formatters_config.formatters["GenerateDocumentation"].args["template_directory"] = self.config_directory
        formatters = load_formatters(
            formatters_config,
            force_order=force_order,
            target_version=target_version,
            skip=skip,
        )
        for formatter in formatters:
            # inject global settings TODO: handle it better
            formatter.instance.formatting_config = self.formatting
            formatter.instance.formatters = self.formatters_lookup
            formatter.instance.languages = self.language
            self.formatters.append(formatter.instance)
            self.formatters_lookup[formatter.name] = formatter.instance
