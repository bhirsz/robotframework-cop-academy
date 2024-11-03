import click
from pathlib import Path
from typing import Any, Optional

try:
    import tomli as toml
except ImportError:  # from Python 3.11
    import toml


CONFIG_NAMES = frozenset(("robotidy.toml", "pyproject.toml"))


def find_project_root(srcs: Optional[tuple[str, ...]], ignore_git_dir: bool) -> Path:
    """
    Find and return the root of the project root.

    Project root is determined by existence of the `.git` directory (if `ignore_git_dir` is `False`) or by
    existence of configuration file. If nothing is found, the root of the file system is returned.

    Args:
        srcs: list of source paths.
        ignore_git_dir: whether to ignore existence of `.git` directory.

    Returns:
        path of the project root.

    """
    if not srcs:
        return Path("/").resolve()
    path_srcs = [Path(Path.cwd(), src).resolve() for src in srcs]
    # A list of lists of parents for each 'src'. 'src' is included as a
    # "parent" of itself if it is a directory
    src_parents = [list(path.parents) + ([path] if path.is_dir() else []) for path in path_srcs]

    common_base = max(
        set.intersection(*(set(parents) for parents in src_parents)),
        key=lambda path: path.parts,
    )

    for directory in (common_base, *common_base.parents):
        if not ignore_git_dir and (directory / ".git").exists():
            return directory
        if any((directory / config_name).is_file() for config_name in CONFIG_NAMES):
            return directory
    return directory


def get_config_path(directory: Path) -> Optional[Path]:
    """Returns path to configuration file if the configuration file exists."""
    for name in CONFIG_NAMES:
        if (config_path := (directory / name)).is_file():
            return config_path
    return None


def load_toml_file(config_path: Path) -> dict[str, Any]:
    try:
        with config_path.open("rb") as tf:
            config = toml.load(tf)
        return config
    except (toml.TOMLDecodeError, OSError) as e:
        raise click.FileError(
            filename=str(config_path), hint=f"Error reading configuration file: {e}"
        )  # TODO: check typer errors


def read_toml_config(config_path: Path) -> dict[str, Any]:
    """
    Load and return toml configuration file.

    For pyproject.toml files we need to retrieve configuration from [tool.robocop] section. This section is not
    required for the robocop.toml file.
    """
    config = load_toml_file(config_path)
    if config_path.name == "pyproject.toml" or "tool" in config:
        config = config.get("tool", {}).get("robotidy", {})
    return {k.replace("--", "").replace("-", "_"): v for k, v in config.items()}
