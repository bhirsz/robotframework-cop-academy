from tests.linter.utils import RuleAcceptance


class TestRuleAcceptance(RuleAcceptance):
    def test_rule(self):
        self.check_rule(
            src_files=["test.robot", "test.resource", "documentation.resource", "with_settings.resource"],
            expected_file="expected_output.txt",
        )
