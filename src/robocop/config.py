from __future__ import annotations

import dataclasses
import fnmatch
import re
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from robocop import files
from robocop.linter.rules import Rule, RuleSeverity, replace_severity_values

DEFAULT_EXCLUDES = r"(\.direnv|\.eggs|\.git|\.hg|\.nox|\.tox|\.venv|venv|\.svn)"

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
class LinterConfig:
    configure: list[str] = field(default_factory=list)
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    issue_format: str = "{source}:{line}:{col} [{severity}] {rule_id} {desc} ({name})"
    threshold: RuleSeverity | None = RuleSeverity.INFO
    ext_rules: list[str] = field(default_factory=list)
    include_rules: set[str] = field(default_factory=set)
    exclude_rules: set[str] = field(default_factory=set)
    include_rules_patterns: set[re.Pattern] = field(default_factory=set)
    exclude_rules_patterns: set[re.Pattern] = field(default_factory=set)

    def __post_init__(self):
        """
        --include and --exclude accept both rule names and rule patterns.

        We need to remove optional severity and split it into patterns and not patterns for easier filtering.

        """
        for rule in self.include:
            rule_without_sev = replace_severity_values(rule)
            if "*" in rule_without_sev:
                self.include_rules_patterns.add(self.compile_rule_pattern(rule_without_sev))
            else:
                self.include_rules.add(rule_without_sev)
        for rule in self.exclude:
            rule_without_sev = replace_severity_values(rule)
            if "*" in rule_without_sev:
                self.exclude_rules_patterns.add(self.compile_rule_pattern(rule_without_sev))
            else:
                self.exclude_rules.add(rule_without_sev)

    def compile_rule_pattern(self, rule_pattern: str) -> re.Pattern:
        return re.compile(fnmatch.translate(rule_pattern))

    # exec_dir: str  # it will not be passed, but generated
    # extend_ignore: set[str]
    # reports: list[str]
    # ignore: re.Pattern = re.compile(DEFAULT_EXCLUDES)
    #         self.filetypes = {".robot", ".resource", ".tsv"}
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


@dataclass
class FormatConfig:
    pass


@dataclass
class Config:
    sources: list[str] = field(default_factory=lambda: ["."])
    linter: LinterConfig = field(default_factory=LinterConfig)
    language: list[str] = field(default_factory=list)

    @classmethod
    def from_toml(cls, config_path: Path) -> Config:
        """
        Load configuration from toml file. If there is parent configuration, use it to overwrite loaded configuration.
        """
        configuration = files.read_toml_config(config_path)
        # TODO: validate all key and types
        return cls(**configuration)

    def overwrite_from_config(self, overwrite_config: Config | None) -> None:
        if not overwrite_config:
            return
        for field in dataclasses.fields(overwrite_config):
            if field.name == "linter":
                continue
            value = getattr(overwrite_config, field.name)
            if value:
                setattr(self, field.name, value)
        if overwrite_config.linter:
            for field in dataclasses.fields(overwrite_config.linter):
                value = getattr(overwrite_config.linter, field.name)
                if value:
                    setattr(self.linter, field.name, value)
        # TODO: same for formatter


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

        """
        self.cached_configs: dict[Path, Config] = {}
        self.overwrite_config = overwrite_config
        self.ignore_git_dir = ignore_git_dir
        self.root = Path(root) if root else files.find_project_root(sources, ignore_git_dir)
        self.root_parent = self.root.parent if self.root.parent else self.root
        self.root_gitignore = self.get_root_gitignore(skip_gitignore)
        self.overridden_config = (
            config is not None
        )  # TODO: what if both cli and --config? should take --config then apply cli
        self.default_config: Config = self.get_default_config(config)
        self.sources = sources if sources else self.default_config.sources
        self.overridden_sources = self.get_overridden_sources(sources)

    def get_and_cache_config_from_toml(self, config_path: Path) -> Config:
        # TODO: merge with cli options
        # TODO: some options may require resolving paths (relative paths in config)
        config = Config.from_toml(config_path)
        config.overwrite_from_config(self.overwrite_config)
        self.cached_configs[config_path.parent] = config
        return config

    def get_default_config(self, config: str | None) -> Config:
        """Get default config either from --config option or find it in the project root."""
        if config:
            config_path = Path(config)  # TODO: fail if doesn't exist, and pass Path instead of str here
        else:
            config_path = files.get_config_path(self.root)
        if not config_path:
            config = Config(self.overwrite_config)
            config.overwrite_from_config(self.overwrite_config)
            return config
        return self.get_and_cache_config_from_toml(config_path)

    def get_root_gitignore(self, skip_gitignore: bool) -> pathspec.PathSpec | None:
        """Load gitignore from project root if it exists and skip_gitignore is False."""
        if skip_gitignore:
            return None
        return files.get_gitignore(self.root)

    @staticmethod
    def get_overridden_sources(sources: list[str] | None) -> set[Path]:
        """
        We can force Robocop to lint/format file even if does match our file filters if we pass path to file in cli.

        This method filters out list of sources from cli for file-like paths.

        Args:
            sources: List of sources with Robot Framework files from the CLI.

        Returns:
            Set of Paths with only files from the sources.

        """
        if not sources:
            return set()
        filtered = set()
        for source in sources:
            path = Path(source)
            if path.is_file():
                filtered.add(path)
        return filtered

    def get_source_files(self, sources: list[str]) -> list[Path]:
        """
        Return list of source files paths that should be parsed by Robocop.

        Args:
            sources: List of sources from CLI or default configuration file.

        Returns:
            List of source paths.

        """
        source_files = []
        exclude, extend_exclude = (
            re.compile(r"/(\.direnv|\.eggs|\.git|\.hg|\.nox|\.tox|\.venv|venv|\.svn)/"),
            None,
        )  # TODO: Pass them from cli / default configuration file
        for source in sources:
            # TODO: Support for - . Instead of existing implementation, we can create temporary fake file
            # if s == "-":
            #     sources.add("-")
            #     continue
            path = Path(source).resolve()
            if not files.should_parse_path(
                path, self.overridden_sources, self.root_parent, exclude, extend_exclude, self.root_gitignore
            ):
                continue
            if path.is_file():
                source_files.append(path)
            elif path.is_dir():
                source_files.extend(
                    files.iterate_dir(
                        path.iterdir(),
                        self.overridden_sources,
                        exclude,
                        extend_exclude,
                        self.root_parent,
                        self.root_gitignore,
                    )
                )
        return source_files

    def get_config_for_source_file(self, source_file: Path) -> Config:
        """
        Find the closest config to the source file.

        If it was loaded before it will be returned from the cache. Otherwise, we will load it and save it to cache
        first.

        Args:
            source_file: Path to Robot Framework source file.

        """
        if self.overridden_config:
            return self.default_config
        if source_file.parent in self.cached_configs:
            return self.cached_configs[source_file.parent]
        config_path = files.find_source_config_file(source_file.parent, self.ignore_git_dir)
        if config_path is None:
            self.cached_configs[source_file.parent] = self.default_config
            return self.default_config
        if config_path.parent in self.cached_configs:
            return self.cached_configs[config_path.parent]
        return self.get_and_cache_config_from_toml(config_path)

    def get_sources_with_configs(self) -> Generator[tuple[Path, Config], None, None]:
        source_files = self.get_source_files(self.sources)
        for source in source_files:
            config = self.get_config_for_source_file(source)
            yield source, config
