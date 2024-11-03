from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Optional

from robocop import files

DEFAULT_EXCLUDES = r"(\.direnv|\.eggs|\.git|\.hg|\.nox|\.tox|\.venv|venv|\.svn)"


@dataclass
class CheckConfig:
    exec_dir: str  # it will not be passed, but generated
    include: set[str]
    exclude: set[str]
    extend_ignore: set[str]
    reports: list[str]
    # threshold = RuleSeverity("I")
    configure: list[str]
    ignore: re.Pattern = re.compile(DEFAULT_EXCLUDES)
    issue_format: str = "{source}:{line}:{col} [{severity}] {rule_id} {desc} ({name})"
    # ext_rules = set()
    #         self.include_patterns = []
    #         self.exclude_patterns = []
    #         self.filetypes = {".robot", ".resource", ".tsv"}
    #         self.language = []
    #         self.output = None
    #         self.recursive = True  TODO do we need it anymore?
    #         self.persistent = False  TODO maybe better name, ie cache-results


@dataclass
class FormatConfig:
    pass


@dataclass
class Config:
    sources: list[str] = field(default_factory=lambda: ["."])

    @classmethod
    def from_toml(cls, config_path: Path) -> "Config":
        configuration = files.read_toml_config(config_path)
        # TODO validate all key and types
        return cls(**configuration)


class ConfigManager:
    """
    Finds and loads configuration files for each file.

    Config provided from cli takes priority. ``--config`` option overrides any found configuration file.
    """

    def __init__(
        self,
        sources: tuple[str, ...] | None = None,
        config: str | None = None,
        root: str | None = None,
        ignore_git_dir: bool = False,
    ):
        """
        Args:
            sources: List of sources with Robot Framework files.
            config: Path to configuration file.
            root: Root of the project. Can be supplied if it's known beforehand (for example by IDE plugin)
            Otherwise it will be automatically found.
            ignore_git_dir: Flag for project root discovery to decide if directories with `.git` should be ignored.
        """
        self.root = Path(root) if root else files.find_project_root(sources, ignore_git_dir)
        self.overridden_config = config is not None
        self.default_config: Config = self.get_default_config(config)
        self.sources = sources

    def get_default_config(self, config: str | None) -> Config:
        """Default config is config from --config option or found in the project root."""
        if config:
            config_path = Path(config)  # TODO fail if doesn't exist, and pass Path instead of str here
        else:
            config_path = files.get_config_path(self.root)
        if not config_path:
            return Config()
        return Config.from_toml(config_path)

    def get_sources_with_configs(self, sources: tuple[str, ...] | None):
        # 1) find sources
        # iterate them, base on the cli or default config (or both if default config is already merged) for any excludes, filetypes etc
        # find for each source file its configuration file (base on directory as multiple files in one directory will have one config file)
        ...


#         for option in kwargs:
#             if ctx.get_parameter_source(option) == ParameterSource.COMMANDLINE:
#                 defined_in_cli.add(option)
# we may not need above if we assume that all cli options are None (and just filter for non-Nones)
