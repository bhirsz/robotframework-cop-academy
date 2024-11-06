from pathlib import Path

from tests.linter.utils import RuleAcceptance

import pytest

CUR_DIR = Path(__file__).parent


class TestRuleAcceptance(RuleAcceptance):
    @pytest.mark.xfail(reason="Custom test needs to be reimplemented")  # FIXME
    def test_rule(self):
        self.check_rule(
            src_files=["."],
            expected_file="expected_output.txt",
            include=["project-checker", "test-total-count"],
            ext_rules=[f"{CUR_DIR}/external_project_checker"]
        )