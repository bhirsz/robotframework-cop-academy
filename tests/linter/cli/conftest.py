import pytest

from robocop.config import ConfigManager
from robocop.linter.runner import RobocopLinter


@pytest.fixture
def empty_linter() -> RobocopLinter:
    config_manager = ConfigManager()
    runner = RobocopLinter(config_manager)
    runner.checkers = []
    runner.rules = {}
    return runner


@pytest.fixture(scope="session")
def loaded_linter() -> RobocopLinter:
    config_manager = ConfigManager()
    runner = RobocopLinter(config_manager)
    return runner
