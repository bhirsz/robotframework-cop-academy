from __future__ import annotations
import inspect
import json
from collections import OrderedDict
from inspect import isclass
from pathlib import Path

import robocop.linter.exceptions
from robocop.linter.rules import RobocopImporter
from robocop.linter.utils.misc import get_robocop_cache_directory
from typing import NoReturn

ROBOCOP_CACHE_FILE = ".robocop_cache"


class Report:
    """
    Base class for report class.
    Override `configure` method if you want to allow report configuration.
    Override `add_message`` if your report processes the Robocop issues.

    Set class attribute `DEFAULT` to `False` if you don't want your report to be included in `all` reports.
    """

    DEFAULT = True
    INTERNAL = False

    def configure(self, name: str, value: str) -> None:
        raise robocop.linter.exceptions.ConfigGeneralError(
            f"Provided param '{name}' for report '{getattr(self, 'name')}' does not exist"
        )

    def add_message(self, *args) -> None:
        pass

    def get_report(self, *args) -> None:
        return None


class ComparableReport(Report):
    def __init__(self, compare_runs):
        self.compare_runs = compare_runs

    def get_report(self, prev_results) -> NoReturn:
        raise NotImplementedError

    def persist_result(self) -> NoReturn:
        raise NotImplementedError


def load_reports(compare_runs) -> dict[str, type[Report]]:
    """
    Load all valid reports.
    Report is considered valid if it inherits from `Report` class
    and contains both `name` and `description` attributes.
    """
    reports = {}
    robocop_importer = RobocopImporter()
    for module in robocop_importer.modules_from_paths([Path(__file__).parent]):
        classes = inspect.getmembers(module, inspect.isclass)
        for report_class in classes:
            if not issubclass(report_class[1], Report):
                continue
            if issubclass(report_class[1], ComparableReport):
                report = report_class[1](compare_runs)
            else:
                report = report_class[1]()
            if not hasattr(report, "name") or not hasattr(report, "description"):
                continue
            reports[report.name] = report
    return reports


def disable_external_reports_if_none(configured_reports: list[str]) -> list[str]:
    """If any reports is 'None', disable other reports other than internal reports."""
    if "None" in configured_reports:
        if "internal_json_report" in configured_reports:
            # TODO: Improve how internal reports are handled
            return ["return_status", "internal_json_report"]
        return ["return_status"]
    return configured_reports


def get_reports(configured_reports: list[str]):
    """
    Return dictionary with list of valid, enabled reports (listed in `configured_reports` set of str).
    If `configured_reports` contains `all` then all default reports are enabled.
    """
    configured_reports = disable_external_reports_if_none(configured_reports)
    compare_runs = "compare_runs" in configured_reports
    reports = load_reports(compare_runs)
    enabled_reports = OrderedDict()
    for report in configured_reports:
        if report == "all":
            for name, report_class in reports.items():
                if report_class.DEFAULT and name not in enabled_reports:
                    enabled_reports[name] = report_class
        elif report not in reports:
            raise robocop.linter.exceptions.InvalidReportName(report, reports)
        elif report not in enabled_reports:
            enabled_reports[report] = reports[report]
    return enabled_reports


def print_reports(reports: dict[str, Report], only_enabled: bool | None) -> str:
    """
    Return description of reports.

    The reports list is filtered and only public reports are provided. If the report is enabled in current
    configuration it will have (enabled) suffix (and (disabled) if it is disabled).

    Args:
        reports: Dictionary with loaded reports.
        only_enabled: if set to True/False, it will filter reports by enabled/disabled status
    """
    all_public_reports = [report for report in load_reports(compare_runs=False).values() if not report.INTERNAL]
    all_public_reports = sorted(all_public_reports, key=lambda x: x.name)
    configured_reports = {x.name for x in reports.values()}
    available_reports = ""
    for report in all_public_reports:
        is_enabled = report.name in configured_reports
        if only_enabled is not None and only_enabled != is_enabled:
            continue
        status = "[green]enabled[/green]" if is_enabled else "[red]disabled[/red]"
        if not report.DEFAULT:
            status += " - non-default"
        available_reports += f"\n{report.name:20} - {report.description} ({status})"
    if available_reports:
        available_reports = "Available reports:" + available_reports
    else:
        available_reports = "No available reports that meet your search criteria."
    available_reports += (
        "\n\nEnable report by passing report name using --reports option. "
        "Use `all` to enable all default reports. "
        "Non-default reports can be only enabled using report name."
    )
    return available_reports


def load_reports_result_from_cache():
    cache_dir = get_robocop_cache_directory(ensure_exists=False)
    cache_file = cache_dir / ROBOCOP_CACHE_FILE
    if not cache_file.is_file():
        return None
    with open(cache_file) as fp:
        try:
            return json.load(fp)
        except json.JSONDecodeError:
            return None


def save_reports_result_to_cache(working_dir: str, report_results: dict) -> None:
    """
    Save results from Robocop reports to json file.

    Result file contains results grouped using working directory.
    That's why we are loading previous results and overwriting only
    the results for current working directory.
    """
    cache_dir = get_robocop_cache_directory(ensure_exists=True)
    cache_file = cache_dir / ROBOCOP_CACHE_FILE
    prev_results = load_reports_result_from_cache()
    if prev_results is None:
        prev_results = {}
    prev_results[working_dir] = report_results
    with open(cache_file, "w") as fp:
        json_string = json.dumps(prev_results, indent=4)
        fp.write(json_string)
