from __future__ import annotations

from collections.abc import Iterable, Iterator
from functools import lru_cache
from pathlib import Path
from re import Pattern
from typing import Any

import click
import pathspec

try:
    import tomli as toml
except ImportError:  # from Python 3.11
    import toml


def load_toml_file(config_path: Path) -> dict[str, Any]:
    try:
        with config_path.open("rb") as tf:
            return toml.load(tf)
    except (toml.TOMLDecodeError, OSError) as e:
        raise click.FileError(
            filename=str(config_path), hint=f"Error reading configuration file: {e}"
        ) from None  # TODO: check typer errors


def read_toml_config(config_path: Path) -> dict[str, Any] | None:
    """
    Load and return toml configuration file.

    For pyproject.toml files we need to retrieve configuration from [tool.robocop] section. This section is not
    required for the robocop.toml file.
    """
    config = load_toml_file(config_path)
    if config_path.name == "pyproject.toml" or "tool" in config:
        config = config.get("tool", {}).get("robocop", {})
        if not config:
            return None
    return {k.replace("--", "").replace("-", "_"): v for k, v in config.items()}


@lru_cache
def find_source_config_file(src: Path, ignore_git_dir: bool = False) -> Path | None:
    """
    Find and return configuration file for the source path.

    This method looks iteratively in source parents for directory that contains configuration file and
    returns its path. The lru_cache speeds up searching if there are multiple files in the same directory (they will
    have the same configuration file).

    If ``.git`` directory is found and ``ignore_git_dir`` is set to ``False``, or top directory is reached, this method
    returns ``None``.
    """
    if src.is_dir():
        for config_filename in CONFIG_NAMES:
            if (src / config_filename).is_file():
                return src / config_filename
        if not src.parents:
            return None
        if not ignore_git_dir and (src.parent / ".git").is_dir():
            return None
    return find_source_config_file(src.parent, ignore_git_dir)


def get_path_relative_to_path(path: Path, root_parent: Path) -> Path:
    try:
        return path.relative_to(root_parent)
    except ValueError:
        return path


@lru_cache
def get_gitignore(root: Path) -> pathspec.PathSpec:
    """Return a PathSpec matching gitignore content if present."""
    gitignore = root / ".gitignore"
    lines: list[str] = []
    if gitignore.is_file():
        with gitignore.open(encoding="utf-8") as gf:
            lines = gf.readlines()
    return pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, lines)
