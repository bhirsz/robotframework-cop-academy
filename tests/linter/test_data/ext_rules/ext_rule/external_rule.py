from robocop.checkers import VisitorChecker
from robocop.rules import Rule, RuleSeverity

rules = {
    "1101": Rule(rule_id="1101", name="smth", msg="Keyword call after [Return] statement", severity=RuleSeverity.ERROR)
}


class SmthChecker(VisitorChecker):
    """Checker for keyword calls after [Return] statement."""

    reports = ("smth",)

    def visit_Keyword(self, node):  # noqa: N802
        self.report("smth", node=node)