from __future__ import annotations

import dataclasses
import re
from collections.abc import Generator
from dataclasses import dataclass, field
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING

import pathspec

from robocop import errors, files
from robocop.linter.rules import Rule, RuleSeverity, replace_severity_values
from robocop.linter.utils.misc import compile_rule_pattern

CONFIG_NAMES = frozenset(("robotidy.toml", "pyproject.toml"))
DEFAULT_INCLUDE = frozenset(("*.robot", "*.resource"))
DEFAULT_EXCLUDE = frozenset((".direnv", ".eggs", ".git", ".svn", ".hg", ".nox", ".tox", ".venv", "venv", "dist"))

DEFAULT_ISSUE_FORMAT = "{source}:{line}:{col} [{severity}] {rule_id} {desc} ({name})"

if TYPE_CHECKING:
    import pathspec


class RuleMatcher:
    def __init__(self, config: Config):
        self.config = config

    def is_rule_enabled(self, rule: Rule) -> bool:
        if self.is_rule_disabled(rule):
            return False
        if (
            self.config.linter.include_rules or self.config.linter.include_rules_patterns
        ):  # if any include pattern, it must match with something
            if rule.rule_id in self.config.linter.include_rules or rule.name in self.config.linter.include_rules:
                return True
            return any(
                pattern.match(rule.rule_id) or pattern.match(rule.name)
                for pattern in self.config.linter.include_rules_patterns
            )
        return rule.enabled

    def is_rule_disabled(self, rule: Rule) -> bool:
        if rule.deprecated or not rule.enabled_in_version:
            return True
        if rule.severity < self.config.linter.threshold and not rule.config.get("severity_threshold"):
            return True
        if rule.rule_id in self.config.linter.exclude_rules or rule.name in self.config.linter.exclude_rules:
            return True
        return any(
            pattern.match(rule.rule_id) or pattern.match(rule.name)
            for pattern in self.config.linter.exclude_rules_patterns
        )


@dataclass
class WhitespaceConfig:
    space_count: int | str | None = 4
    indent: int | str | None = None
    continuation_indent: int | str | None = None
    line_separator: str | None = "native"  # TODO was lineseparator in cli
    separator: str | None = "space"
    line_length: int | None = 120

    def process_config(self):
        """Prepare config with processed values. If value is missing, use related config as a default."""
        if self.indent is None:
            self.indent = self.space_count
        if self.continuation_indent is None:
            self.continuation_indent = self.space_count
        if self.separator == "space":
            self.separator = " " * self.space_count
            self.indent = " " * self.indent
            self.continuation_indent = " " * self.continuation_indent
        elif self.separator == "tab":
            self.separator = "\t"
            self.indent = "\t"
            self.continuation_indent = "\t"
        if self.line_separator == "native":
            self.line_separator = "\n"
        elif self.line_separator == "windows":
            self.line_separator = "\r\n"
        elif line_sep == "unix":
            self.line_separator = "\n"


@dataclass
class LinterConfig:
    configure: list[str] | None = field(default_factory=list)
    select: list[str] | None = field(default_factory=list)
    ignore: list[str] | None = field(default_factory=list)
    issue_format: str | None = DEFAULT_ISSUE_FORMAT
    threshold: RuleSeverity | None = RuleSeverity.INFO
    ext_rules: list[str] | None = field(default_factory=list)
    include_rules: set[str] | None = field(default_factory=set)
    exclude_rules: set[str] | None = field(default_factory=set)
    include_rules_patterns: set[re.Pattern] | None = field(default_factory=set)
    exclude_rules_patterns: set[re.Pattern] | None = field(default_factory=set)
    reports: list[str] | None = field(default_factory=list)
    persistent: bool | None = False
    compare: bool | None = False

    def __post_init__(self):
        """
        --include and --exclude accept both rule names and rule patterns.

        We need to remove optional severity and split it into patterns and not patterns for easier filtering.

        """
        # TODO: with overwrite, it will not be called
        if self.select:
            for rule in self.select:
                rule_without_sev = replace_severity_values(rule)
                if "*" in rule_without_sev:
                    self.include_rules_patterns.add(compile_rule_pattern(rule_without_sev))
                else:
                    self.include_rules.add(rule_without_sev)
        if self.ignore:
            for rule in self.ignore:
                rule_without_sev = replace_severity_values(rule)
                if "*" in rule_without_sev:
                    self.exclude_rules_patterns.add(compile_rule_pattern(rule_without_sev))
                else:
                    self.exclude_rules.add(rule_without_sev)

    # exec_dir: str  # it will not be passed, but generated
    # extend_ignore: set[str]
    # reports: list[str]
    #         self.output = None
    #         self.recursive = True  TODO do we need it anymore?
    #         self.persistent = False  TODO maybe better name, ie cache-results

    #     def validate_rules_exists_and_not_deprecated(self, rules: dict[str, "Rule"]):
    #         for rule in chain(self.include, self.exclude):
    #             if rule not in rules:
    #                 raise exceptions.RuleDoesNotExist(rule, rules) from None
    #             rule_def = rules[rule]
    #             if rule_def.deprecated:
    #                 print(rule_def.deprecation_warning)

    @classmethod
    def from_toml(cls, config: dict) -> LinterConfig:
        configure = config.pop("configure", [])  # TODO repeat the same for all params (use fields?)
        return cls(
            configure=configure,
        )


@dataclass
class FormatterConfig:
    whitespace_config: WhitespaceConfig = field(default_factory=WhitespaceConfig)
    overwrite: bool | None = False
    show_diff: bool | None = False
    output = None  # TODO
    color: bool | None = False
    check: bool | None = False
    reruns: int | None = 0  # TODO
    start_line: int | None = None  # TODO it's startline/endline in cli
    end_line: int | None = None


@dataclass
class FileFiltersOptions:
    include: set[str] | None = field(default_factory=lambda: DEFAULT_INCLUDE)
    extend_include: set[str] | None = None
    exclude: set[str] | None = field(default_factory=lambda: DEFAULT_EXCLUDE)
    extend_exclude: set[str] | None = None

    def overwrite(self, other: FileFiltersOptions) -> None:
        """
        Overwrite default value with options from cli.

        Ignore None values.
        """
        if other.include is not None:
            self.include = other.include
        if other.extend_include is not None:
            self.extend_include = other.extend_include
        if other.exclude is not None:
            self.exclude = other.exclude
        if other.extend_exclude is not None:
            self.extend_exclude = other.extend_exclude

    def path_excluded(self, path: Path) -> bool:
        """Exclude all paths matching exclue patterns."""
        if self.exclude:
            for pattern in self.exclude:
                if path.match(pattern):
                    return True
        if self.extend_exclude:
            for pattern in self.extend_exclude:
                if path.match(pattern):
                    return True
        return False

    def path_included(self, path: Path) -> bool:
        """Only allow paths matching include patterns."""
        include_paths = self.include
        if self.extend_include:
            include_paths.extend(self.extend_include)
        for pattern in include_paths:
            if path.match(pattern):
                return True
        return False


@dataclass
class Config:
    sources: list[str] | None = field(default_factory=lambda: ["."])
    file_filters: FileFiltersOptions = field(default_factory=FileFiltersOptions)
    linter: LinterConfig = field(default_factory=LinterConfig)
    formatter: FormatterConfig = field(default_factory=FormatterConfig)
    language: list[str] | None = field(default_factory=list)
    exit_zero: bool | None = False
    config_source: str = "default configuration"

    @classmethod
    def from_toml(cls, config: dict, config_path: Path) -> Config:
        """
        Load configuration from toml dict. If there is parent configuration, use it to overwrite loaded configuration.
        """
        # TODO: validate all key and types
        parsed_config = {"config_source": str(config_path)}
        parsed_config["linter"] = LinterConfig.from_toml(config.pop("lint", {}))
        filter_config = {}
        for key in ("include", "extend_include", "exclude", "extend_exclude"):
            if key in config:
                filter_config[key] = config.pop(key)
        parsed_config["file_filters"] = FileFiltersOptions(**filter_config)
        parsed_config = {key: value for key, value in parsed_config.items() if value is not None}
        return cls(**parsed_config)

    def overwrite_from_config(self, overwrite_config: Config | None) -> None:
        # TODO what about --config? toml files has config = [], and cli --config as well, what should happen?
        # 1) cli overwrites all 2) we append to config (last, so cli overwrites the same settings) - preferred
        if not overwrite_config:
            return
        for field in dataclasses.fields(overwrite_config):
            if field.name in ("linter", "formatter", "file_filters", "config_source"):  # TODO Use field metadata maybe
                continue
            value = getattr(overwrite_config, field.name)
            if value:
                setattr(self, field.name, value)
        if overwrite_config.linter:
            for field in dataclasses.fields(overwrite_config.linter):
                value = getattr(overwrite_config.linter, field.name)
                if value:
                    setattr(self.linter, field.name, value)
        self.file_filters.overwrite(overwrite_config.file_filters)
        # TODO: same for formatter

    def __str__(self):
        return str(self.config_source)


class GitIgnoreResolver:
    def __init__(self):
        self.cached_ignores: dict[Path, pathspec.PathSpec] = {}

    def path_excluded(self, path: Path, gitignores: list[tuple[Path, pathspec.PathSpec]]) -> bool:
        """Find path gitignores and check if file is excluded."""
        if not gitignores:
            return False
        for gitignore_path, gitignore in gitignores:
            relative_path = files.get_path_relative_to_path(path, gitignore_path)
            if gitignore.match_file(relative_path):  # TODO test on dir
                return True
        return False

    def read_gitignore(self, path: Path) -> pathspec.PathSpec:
        """Return a PathSpec loaded from the file."""
        with path.open(encoding="utf-8") as gf:
            lines = gf.readlines()
        return pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, lines)

    def resolve_path_ignores(self, path: Path) -> list[tuple[Path, pathspec.PathSpec]]:
        """
        Visit all parent directories and find all gitignores.

        Gitignores are cached for multiple sources.

        Args:
            path: path to file/directory

        Returns:
            PathSpec from merged gitignores.
        """
        # TODO: respect nogitignore flag
        if path.is_file():
            path = path.parent
        gitignores = []
        for path in [path, *path.parents]:
            if path in self.cached_ignores:
                gitignores.append(self.cached_ignores[path])
            elif (gitignore_path := path / ".gitignore").is_file():
                gitignore = self.read_gitignore(gitignore_path)
                self.cached_ignores[path] = (path, gitignore)
                gitignores.append((path, gitignore))
            if (path / ".git").is_dir():
                break
        return gitignores


class ConfigManager:
    """
    Finds and loads configuration files for each file.

    Config provided from cli takes priority. ``--config`` option overrides any found configuration file.
    """

    def __init__(
        self,
        sources: list[str] | None = None,
        config: Path | None = None,
        root: str | None = None,
        ignore_git_dir: bool = False,
        skip_gitignore: bool = False,
        overwrite_config: Config | None = None,
    ):
        """
        Initialize ConfigManager.

        Args:
            sources: List of sources with Robot Framework files.
            config: Path to configuration file.
            root: Root of the project. Can be supplied if it's known beforehand (for example by IDE plugin)
            Otherwise it will be automatically found.
            ignore_git_dir: Flag for project root discovery to decide if directories with `.git` should be ignored.
            skip_gitignore: Do not load .gitignore files when looking for the files to parse
            overwrite_config: Overwrite existing configuration file with the Config class

        """
        self.cached_configs: dict[Path, Config] = {}
        self.overwrite_config = overwrite_config
        self.ignore_git_dir = ignore_git_dir
        self.gitignore_resolver = GitIgnoreResolver()
        self.overridden_config = (
            config is not None
        )  # TODO: what if both cli and --config? should take --config then apply cli
        self.root = Path.cwd()  # FIXME or just check if its fine
        self.default_config: Config = self.get_default_config(config)
        self.sources = sources
        self._paths: dict[Path, Config] | None = None

    @property
    def paths(self) -> Generator[tuple[Path, Config], None, None]:
        # TODO: what if we provide the same path twice - tests
        if self._paths is None:
            self._paths = {}
            sources = self.sources if self.sources else self.default_config.sources
            ignore_file_filters = bool(sources)
            self.resolve_paths(sources, gitignores=None, ignore_file_filters=ignore_file_filters)
        for path, config in self._paths.items():
            yield path, config

    def get_default_config(self, config_path: Path | None) -> Config:
        """Get default config either from --config option or find it in the project root."""
        if config_path:
            configuration = files.read_toml_config(config_path)
            config = Config.from_toml(configuration, config_path)
            config.overwrite_from_config(self.overwrite_config)
            return config
        config = Config()
        config.overwrite_from_config(self.overwrite_config)
        return config

    def find_closest_config(self, source: Path) -> Config:
        """
        Look in the directory and its parents for the closest valid configuration file.
        """
        # we always look for configuration in parent directory, unless we hit the top already
        if (self.ignore_git_dir or not (source / ".git").is_dir()) and source.parents:
            source = source.parent
        check_dirs = [source, *source.parents]
        seen = []  # if we find config, mark all visited directories with resolved config
        config = self.default_config
        found_config = False
        for check_dir in check_dirs:
            if check_dir in self.cached_configs:
                return self.cached_configs[check_dir]
            seen.append(check_dir)
            for config_filename in CONFIG_NAMES:
                if (config_path := (check_dir / config_filename)).is_file():
                    configuration = files.read_toml_config(config_path)
                    if configuration is not None:
                        config = Config.from_toml(configuration, config_path)
                        config.overwrite_from_config(self.overwrite_config)  # TODO those two lines together
                        found_config = True
                        break
            if found_config or (not self.ignore_git_dir and (check_dir / ".git").is_dir()):
                break
        for check_dir in seen:
            self.cached_configs[check_dir] = config
        return config

    def get_config_for_source_file(self, source_file: Path) -> Config:
        """
        Find the closest config to the source file or directory.

        If it was loaded before it will be returned from the cache. Otherwise, we will load it and save it to cache
        first.

        Args:
            source_file: Path to Robot Framework source file or directory.

        """
        if self.overridden_config:
            return self.default_config
        return self.find_closest_config(source_file)

    def resolve_paths(
        self,
        sources: list[str | Path],
        gitignores: list[tuple[Path, pathspec.PathSpec]] | None,
        ignore_file_filters: bool = False,
    ) -> None:
        """
        Find all files to parse and their corresponding configs.

        Initially sources can be ["."] (if not path provided, assume current working directory).
        It can be also any list of paths, for example ["tests/", "file.robot"].

        Args:
            sources: list of sources from CLI or configuration file.
            gitignores: list of gitignore pathspec and their locations for path resolution.
            ignore_file_filters: force robocop to parse file even if it's excluded in the configuration

        """
        # FIXME ignore file filters is True for default source
        for source in sources:
            source = Path(source).resolve()
            if source in self._paths:
                continue
            if not source.exists():  # TODO only for passed sources
                raise errors.FileError(source)
            # if gitignores is None:  # TODO it works, but should be added with tests later
            #     source_gitignore = self.gitignore_resolver.resolve_path_ignores(source)
            # else:
            #     source_gitignore = gitignores
            config = self.get_config_for_source_file(source)
            # if self.gitignore_resolver.path_excluded(source, source_gitignore):
            #     continue
            if not ignore_file_filters:
                if config.file_filters.path_excluded(source):
                    continue
                if source.is_file() and not config.file_filters.path_included(source):
                    continue
            if source.is_dir():
                self.resolve_paths(source.iterdir(), gitignores)
                # TODO cache resolved dirs too
            elif source.is_file():
                self._paths[source] = config
