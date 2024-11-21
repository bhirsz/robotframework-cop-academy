from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from robot.api import get_init_model, get_model, get_resource_model
from robot.errors import DataError

from robocop.config import Config, ConfigManager, RuleMatcher
from robocop.linter import exceptions, reports
from robocop.linter.diagnostics import Diagnostic
from robocop.linter.rules import Rule, comments, documentation, duplications, errors, lengths
from robocop.linter.utils.disablers import DisablersFinder
from robocop.linter.utils.misc import is_suite_templated

if TYPE_CHECKING:
    from robot.parsing import File

    from robocop.linter.rules import BaseChecker, Rule  # TODO: Check if circular import will not happen


class RobocopLinter:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.config: Config = self.config_manager.default_config
        self.checkers: list[BaseChecker] = []
        self.rules: dict[str, Rule] = {}
        for checker in [  # TODO measure perf. if the same, compare code readability
            comments.CommentChecker(),
            comments.IgnoredDataChecker(),
            documentation.MissingDocumentationChecker(),
            duplications.DuplicationsChecker(),
            duplications.SectionHeadersChecker(),
            errors.ParsingErrorChecker(),
            errors.TwoSpacesAfterSettingsChecker(),
            errors.VariablesImportErrorChecker(),
            errors.MissingKeywordName(),
            lengths.LengthChecker(),
            lengths.LineLengthChecker(),
            lengths.TestCaseNumberChecker(),
            lengths.EmptySectionChecker(),
            lengths.EmptySettingsChecker(),
            lengths.NumberOfReturnedArgsChecker(),
            lengths.TooManyArgumentsInLineChecker(),
        ]:  # TODO:
            self.register_checker(checker)
        # self.load_checkers()
        self.reports: dict[str, reports.Report] = reports.get_reports(
            self.config.linter.reports, self.config.linter.compare
        )

    def register_checker(self, checker: type[BaseChecker]) -> None:  # [type[BaseChecker]]
        checker_module = importlib.import_module(
            checker.__module__
        )  # TODO perf, wouldn't be needed if not for pytest caching
        checker_annotations = checker.__annotations__
        for name, rule_class in checker_annotations.items():
            if isinstance(rule_class, str):  # if from future import annotations was used
                rule_instance = getattr(checker_module, rule_class)()
            else:
                rule_instance = rule_class()
            self.rules[rule_instance.rule_id] = rule_instance
            self.rules[rule_instance.name] = rule_instance
            checker.rules[rule_instance.name] = rule_instance
            setattr(checker, name, rule_instance)
        self.checkers.append(checker)

    def check_for_disabled_rules(self) -> None:
        """Check checker configuration to disable rules."""
        rule_matcher = RuleMatcher(self.config)
        for checker in self.checkers:  # TODO: each config with own copy of checkers & rules
            if not self.any_rule_enabled(checker, rule_matcher):
                checker.disabled = True

    def any_rule_enabled(self, checker: type[BaseChecker], rule_matcher: RuleMatcher) -> bool:
        any_enabled = False
        for name, rule in checker.rules.items():
            rule.enabled = rule_matcher.is_rule_enabled(rule)
            if rule.enabled:
                any_enabled = True
        return any_enabled

    def get_model_for_file_type(self, source: Path) -> File:
        """Recognize model type of the file and load the model."""
        # TODO: decide to migrate file type recognition based on imports from robocop
        # TODO: language
        if "__init__" in source.name:
            return get_init_model(source)
        if source.suffix == ".resource":
            return get_resource_model(source)
        return get_model(source)

    def run(self) -> None:
        issues_no = 0
        for source, config in self.config_manager.get_sources_with_configs():
            # TODO: If there is only one config, we do not need to reload it every time - some sort of caching?
            self.config = config  # need to save it for rules to access rules config (also TODO: load rules config)
            self.configure_checkers_or_reports()
            self.check_for_disabled_rules()
            #             if self.config.verbose:
            #                 print(f"Scanning file: {file}")
            try:
                model = self.get_model_for_file_type(source)
            except DataError:
                print(
                    f"Failed to decode {source}. Default supported encoding by Robot Framework is UTF-8. Skipping file"
                )
                continue
            diagnostics = self.run_check(model, str(source))
            diagnostics.sort()
            issues_no += len(diagnostics)
            for diagnostic in diagnostics:
                self.report(diagnostic)
        self.make_reports()
        self.return_with_exit_code(issues_no)
        # print(f"\n\n{issues_no} issues found.")
        # if "file_stats" in self.reports:  # TODO:
        #     self.reports["file_stats"].files_count = len(self.files)

    def run_check(self, ast_model: File, filename: str, source: str | None = None) -> list[Diagnostic]:
        disablers = DisablersFinder(ast_model)
        if disablers.file_disabled:
            return []
        found_diagnostics = []
        templated = is_suite_templated(ast_model)
        for checker in self.checkers:
            if checker.disabled:
                continue
            found_diagnostics += [
                diagnostic
                for diagnostic in checker.scan_file(ast_model, filename, source, templated)
                if not disablers.is_rule_disabled(diagnostic) and not diagnostic.severity < self.config.linter.threshold
            ]
        return found_diagnostics

    def return_with_exit_code(self, issues_count: int) -> None:
        """
        Exit the Robocop with exit code.

        Exit code is always 0 if --exit-zero is set. Otherwise, it can be calculated by optional `return_status`
        report. If it is not enabled, exit code will be:

        - 0 if no issues found
        - 1 if any issue found
        - 2 if Robocop terminated abnormally

        """
        if self.config_manager.default_config.exit_zero:
            exit_code = 0
        elif "return_status" in self.reports:
            exit_code = self.reports["return_status"].exit_code
        else:
            exit_code = 1 if issues_count else 0
        raise typer.Exit(code=exit_code)

    def report(self, diagnostic: Diagnostic) -> None:
        for report in self.reports.values():
            report.add_message(diagnostic)
        # try:
        #     # TODO: reimplement with Path
        #     # TODO: lazy evaluation in case source_rel is not used
        #     source_rel = os.path.relpath(os.path.expanduser(rule_msg.source), self.config_manager.root)
        # except ValueError:
        #     source_rel = rule_msg.source
        print(
            self.config.linter.issue_format.format(
                source=diagnostic.source,
                line=diagnostic.range.start.line,
                col=diagnostic.range.start.character,
                end_line=diagnostic.range.end.line,
                end_col=diagnostic.range.end.character,
                severity=diagnostic.severity.value,
                rule_id=diagnostic.rule.rule_id,
                desc=diagnostic.message,
                name=diagnostic.rule.name,
            )
        )

    def configure_checkers_or_reports(self) -> None:
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

    def make_reports(self) -> None:
        report_results = {}
        prev_results = reports.load_reports_result_from_cache()
        prev_results = prev_results.get(str(self.config_manager.root)) if prev_results is not None else None
        is_persistent = self.config_manager.default_config.linter.persistent
        for report in self.reports.values():
            if report.name == "sarif":
                output = report.get_report(self.config_manager.root, self.rules)
            elif isinstance(report, reports.ComparableReport):  # TODO:
                prev_result = prev_results.get(report.name) if prev_results is not None else None
                output = report.get_report(prev_result)
            else:
                output = report.get_report()
            if output is not None:
                print(output)
            if is_persistent and isinstance(report, reports.ComparableReport):
                result = report.persist_result()
                if result is not None:
                    report_results[report.name] = result
        if is_persistent:
            save_reports_result_to_cache(str(self.config_manager.root), report_results)


# should we rediscover checkers/rules for each source config?
# nope, any custom rules etc should be loaded from cli or default config
# then we can only enable/disable them in following configs
