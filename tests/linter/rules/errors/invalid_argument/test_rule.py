from tests.linter.utils import RuleAcceptance


class TestRuleAcceptance(RuleAcceptance):
    def test_rule(self):
        self.check_rule(
            src_files=["test.robot"], expected_file="expected_output.txt", test_on_version=">=4", issue_format="end_col"
        )
