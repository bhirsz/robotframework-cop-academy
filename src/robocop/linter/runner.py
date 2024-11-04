import os
from typing import Optional, TYPE_CHECKING

from robot.api import get_model

from robocop.config import Config, ConfigManager
from robocop.linter import rules
from robocop.linter.utils.misc import is_suite_templated

if TYPE_CHECKING:
    from robocop.linter.rules import Message, Rule  # TODO: Check if circular import will not happen


class RuleMatcher:
    def __init__(self, config: Config):
        self.config = config

    def is_rule_enabled(self, rule: "Rule") -> bool:
        if self.is_rule_disabled(rule):
            return False
        if self.config.include or self.config.include_patterns:  # if any include pattern, it must match with something
            if rule.rule_id in self.config.include or rule.name in self.config.include:
                return True
            return any(
                pattern.match(rule.rule_id) or pattern.match(rule.name) for pattern in self.config.include_patterns
            )
        return rule.enabled

    def is_rule_disabled(self, rule: "Rule") -> bool:
        if rule.deprecated or not rule.enabled_in_version:
            return True
        # if rule.severity < self.config.threshold and not rule.config.get("severity_threshold"):
        #     return True  # TODO
        if rule.rule_id in self.config.exclude or rule.name in self.config.exclude:
            return True
        return any(pattern.match(rule.rule_id) or pattern.match(rule.name) for pattern in self.config.exclude_patterns)


class RobocopLinter:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.config: Optional[Config] = None
        self.checkers: list = []  # [type[BaseChecker]]
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

    def run(self):
        issues_no = 0
        for source, config in self.config_manager.get_sources_with_configs():
            # TODO: If there is only one config, we do not need to reload it every time - some sort of caching?
            self.config = config  # need to save it for rules to access rules config (also TODO: load rules config)
            self.check_for_disabled_rules()
            #             if self.config.verbose:
            #                 print(f"Scanning file: {file}")
            # TODO: language
            # TODO: recognize file types? or at least if __init__ or resource
            model = get_model(source=source)
            found_issues = self.run_check(model, str(source))
            found_issues.sort()
            issues_no += len(found_issues)
            for issue in found_issues:
                self.report(issue)
        # print(f"\n\n{issues_no} issues found.")
        # if "file_stats" in self.reports:  # TODO:
        #     self.reports["file_stats"].files_count = len(self.files)

    def run_check(self, ast_model, filename: str, source=None) -> list["Message"]:
        # disablers = DisablersFinder(ast_model)  # TODO:
        # if disablers.file_disabled:
        #     return []
        found_issues = []
        templated = is_suite_templated(ast_model)
        for checker in self.checkers:
            if checker.disabled:
                continue
            found_issues += [
                issue
                for issue in checker.scan_file(ast_model, filename, source, templated)
                # if not disablers.is_rule_disabled(issue) and not issue.severity < self.config.threshold  # TODO:
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
        print(self.config.format.format(**kwargs))
        # self.write_line(self.config.format.format(**kwargs))


# should we rediscover checkers/rules for each source config?
# nope, any custom rules etc should be loaded from cli or default config
# then we can only enable/disable them in following configs
