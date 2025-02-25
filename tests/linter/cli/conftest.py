import pytest

from robocop.config import ConfigManager
from robocop.linter.runner import RobocopLinter


@pytest.fixture
def empty_linter() -> RobocopLinter:
    config_manager = ConfigManager()
    runner = RobocopLinter(config_manager)
    runner.config.linter._checkers = []
    runner.config.linter._rules = {}
    return runner


@pytest.fixture(scope="session")
def loaded_linter() -> RobocopLinter:
    config_manager = ConfigManager()
    return RobocopLinter(config_manager)
