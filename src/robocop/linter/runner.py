from typing import TYPE_CHECKING

from robocop.linter import rules

if TYPE_CHECKING:
    from robocop.linter.rules import Rule  # TODO: Check if circular import will not happen


class Linter:
    def __init__(self):
        self.checkers: list = []  # [type[BaseChecker]]
        self.rules: dict[str, Rule] = {}
        self.load_checkers()
        # load_reports()
        # configure reports / rules
        # check for disabled rules

    def load_checkers(self):
        self.checkers = []
        self.rules = {}
        rules.init(self)

    def register_checker(self, checker):  # [type[BaseChecker]]
        for rule_name, rule in checker.rules.items():
            self.rules[rule_name] = rule
            self.rules[rule.rule_id] = rule
        self.checkers.append(checker)
