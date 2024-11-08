import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from robot.api import get_model, get_init_model, get_resource_model

from robocop.config import Config, ConfigManager, RuleMatcher
from robocop.linter import rules, exceptions
from robocop.linter.utils.misc import is_suite_templated
from robocop.linter.utils.disablers import DisablersFinder

if TYPE_CHECKING:
    from robocop.linter.rules import Message, Rule  # TODO: Check if circular import will not happen


class RobocopLinter:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.config: Config = self.config_manager.default_config
        self.checkers: list = []  # [type[BaseChecker]]
        self.reports: dict = {}  # TODO: load reports
        self.rules: dict[str, Rule] = {}
        self.load_checkers()
        # load_reports()
        # configure reports / rules

    def load_checkers(self):
        self.checkers = []
        self.rules = {}
        rules.init(self)

    def register_checker(self, checker):  # [type[BaseChecker]]
        for rule_name, rule in checker.rules.items():
            self.rules[rule_name] = rule
            self.rules[rule.rule_id] = rule
        self.checkers.append(checker)

    def check_for_disabled_rules(self):
        """Check checker configuration to disable rules."""
        rule_matcher = RuleMatcher(self.config)
        for checker in self.checkers:
            if not self.any_rule_enabled(checker, rule_matcher):
                checker.disabled = True

    def any_rule_enabled(self, checker, rule_matcher: RuleMatcher) -> bool:
        for name, rule in checker.rules.items():
            rule.enabled = rule_matcher.is_rule_enabled(rule)
            checker.rules[name] = rule
        return any(msg.enabled for msg in checker.rules.values())

    def get_model_for_file_type(self, source: Path):
        """Recognize model type of the file and load the model."""
        # TODO: decide to migrate file type recognition based on imports from robocop
        # TODO: language
        if "__init__" in source.name:
            return get_init_model(source)
        if source.suffix == ".resource":
            return get_resource_model(source)
        return get_model(source)

    def run(self):
        issues_no = 0
        for source, config in self.config_manager.get_sources_with_configs():
            # TODO: If there is only one config, we do not need to reload it every time - some sort of caching?
            self.config = config  # need to save it for rules to access rules config (also TODO: load rules config)
            self.configure_checkers_or_reports()
            self.check_for_disabled_rules()
            #             if self.config.verbose:
            #                 print(f"Scanning file: {file}")
            model = self.get_model_for_file_type(source)
            found_issues = self.run_check(model, str(source))
            found_issues.sort()
            issues_no += len(found_issues)
            for issue in found_issues:
                self.report(issue)
        # print(f"\n\n{issues_no} issues found.")
        # if "file_stats" in self.reports:  # TODO:
        #     self.reports["file_stats"].files_count = len(self.files)

    def run_check(self, ast_model, filename: str, source=None) -> list["Message"]:
        disablers = DisablersFinder(ast_model)
        if disablers.file_disabled:
            return []
        found_issues = []
        templated = is_suite_templated(ast_model)
        for checker in self.checkers:
            if checker.disabled:
                continue
            found_issues += [
                issue
                for issue in checker.scan_file(ast_model, filename, source, templated)
                if not disablers.is_rule_disabled(issue) and not issue.severity < self.config.linter.threshold
            ]
        return found_issues

    def report(self, rule_msg: "Message"):
        # for report in self.reports.values():  # TODO:
        #     report.add_message(rule_msg)
        try:
            # TODO: reimplement with Path
            # TODO: lazy evaluation in case source_rel is not used
            source_rel = os.path.relpath(os.path.expanduser(rule_msg.source), self.config_manager.root)
        except ValueError:
            source_rel = rule_msg.source
        self.log_message(
            source=rule_msg.source,
            source_rel=source_rel,
            line=rule_msg.line,
            col=rule_msg.col,
            end_line=rule_msg.end_line,
            end_col=rule_msg.end_col,
            severity=rule_msg.severity.value,
            rule_id=rule_msg.rule_id,
            desc=rule_msg.desc,
            name=rule_msg.name,
        )

    def log_message(self, **kwargs):
        print(self.config.linter.issue_format.format(**kwargs))
        # self.write_line(self.config.format.format(**kwargs))

    def configure_checkers_or_reports(self):
        """
        Iterate over configuration for rules and reports and apply it.

        Accepted format is rule_name.param=value or report_name.param=value . ``rule_id`` can be used instead of
        ``rule_name``.
        """
        for config in self.config.linter.configure:
            # TODO: applying configuration change original rule/report. We should have way of restoring it for multiple configurations (or store separately)
            # TODO: should be validated in Config class, here only applying values
            # TODO: there could be rules and reports containers that accept config and apply, instead of doing it in the runner
            try:  # TODO: replace severity values
                name, param_and_value = config.split(".", maxsplit=1)
                param, value = param_and_value.split("=", maxsplit=1)
            except ValueError:
                raise exceptions.ConfigGeneralError(
                    f"Provided invalid config: '{config}' (general pattern: <rule/report>.<param>=<value>)"
                ) from None
            if name in self.rules:
                rule = self.rules[name]
                if rule.deprecated:
                    print(rule.deprecation_warning)
                else:
                    rule.configure(param, value)
            elif name in self.reports:
                self.reports[name].configure(param, value)
            else:
                raise exceptions.RuleOrReportDoesNotExist(name, self.rules)


# should we rediscover checkers/rules for each source config?
# nope, any custom rules etc should be loaded from cli or default config
# then we can only enable/disable them in following configs
