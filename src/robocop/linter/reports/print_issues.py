from enum import Enum
from pathlib import Path

import robocop.linter.reports
from robocop.config import Config
from robocop.linter.diagnostics import Diagnostic


class OutputFormat(Enum):
    SIMPLE = "simple"
    EXTENDED = "extended"
    GROUPED = "grouped"

    @classmethod
    def _missing_(cls, value):
        choices = [choice.value for choice in cls.__members__.values()]
        raise ValueError(f"{value} is not a valid {cls.__name__}, please choose from {choices}") from None


class PrintIssuesReport(robocop.linter.reports.Report):
    """
    **Report name**: ``print_issues``

    This report is always enabled.
    Report that collect diagnostic messages and print them at the end of the execution.
    """

    DEFAULT = False
    ENABLED = True

    def __init__(self, config: Config):
        self.name = "print_issues"
        self.description = "Collect and print rules messages"
        self.diagn_by_source: dict[str, list[Diagnostic]] = {}
        self.output_format = OutputFormat.SIMPLE
        super().__init__(config)

    def configure(self, name: str, value: str) -> None:
        if name == "output_format":
            self.output_format = OutputFormat(value)
        else:
            super().configure(name, value)

    def add_message(self, message: Diagnostic) -> None:
        if message.source not in self.diagn_by_source:
            self.diagn_by_source[message.source] = []
        self.diagn_by_source[message.source].append(message)

    def print_diagnostics_simple(self) -> None:
        cwd = Path.cwd()
        for source, diagnostics in self.diagn_by_source.items():
            diagnostics.sort()
            source_rel = Path(source).relative_to(cwd)
            for diagnostic in diagnostics:
                print(
                    self.config.linter.issue_format.format(
                        source=source_rel,
                        source_abs=diagnostic.source,
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

    def get_report(self) -> None:
        if self.output_format == OutputFormat.SIMPLE:
            self.print_diagnostics_simple()
        else:
            raise NotImplementedError(f"Output format {self.output_format} is not implemented")
