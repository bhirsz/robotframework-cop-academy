"""Duplications checkers"""

from collections import defaultdict

from robot.api import Token

from robocop.linter.rules import Rule, RuleParam, RuleSeverity, VisitorChecker
from robocop.linter.utils import get_errors, normalize_robot_name, normalize_robot_var_name


def configure_sections_order(value):
    section_map = {
        "settings": Token.SETTING_HEADER,
        "variables": Token.VARIABLE_HEADER,
        "testcase": Token.TESTCASE_HEADER,
        "testcases": Token.TESTCASE_HEADER,
        "task": "TASK HEADER",
        "tasks": "TASK HEADER",
        "keyword": Token.KEYWORD_HEADER,
        "keywords": Token.KEYWORD_HEADER,
    }
    sections_order = {}
    for index, name in enumerate(value.split(",")):
        if name.lower() not in section_map or section_map[name.lower()] in sections_order:
            raise ValueError(f"Invalid section name: `{name}`")
        sections_order[section_map[name.lower()]] = index
    if Token.TESTCASE_HEADER in sections_order:
        sections_order["TASK HEADER"] = sections_order[Token.TESTCASE_HEADER]
    return sections_order


class DuplicatedTestCaseRule(Rule):
    """
    Multiple test cases with the same name in the suite.

    It is not allowed to reuse the same name of the test case within the same suite in Robot Framework.
    Name matching is case-insensitive and ignores spaces and underscore characters.
    Duplicated test cases example::

        *** Test Cases ***
        Test with name
            No Operation

        test_with Name  # it is a duplicate of 'Test with name'
            No Operation
    """

    name = "duplicated-test-case"
    rule_id = "DUP01"
    message = "Multiple test cases with name '{name}' (first occurrence in line {first_occurrence_line})"
    severity = RuleSeverity.ERROR
    added_in_version = "1.0.0"


class DuplicatedKeywordRule(Rule):
    """
    Multiple keywords with the same name in the file.

    Do not define keywords with the same name inside the same file. Name matching is case-insensitive and
    ignores spaces and underscore characters.
    Duplicated keyword names example::

        *** Keywords ***
        Keyword
            No Operation

        keyword
            No Operation

        K_eywor d
            No Operation

    """

    name = "duplicated-keyword"
    rule_id = "DUP02"
    message = "Multiple keywords with name '{name}' (first occurrence in line {first_occurrence_line})"
    severity = RuleSeverity.ERROR
    added_in_version = "1.0.0"


class DuplicatedVariableRule(Rule):
    """
    Multiple variables with the same name in the file.

    Variable names in Robot Framework are case-insensitive and ignore spaces and underscores. Following variables
    are duplicates::

        *** Variables ***
        ${variable}    1
        ${VARIAble}    a
        @{variable}    a  b
        ${v ariabl e}  c
        ${v_ariable}   d

    """

    name = "duplicated-variable"
    rule_id = "DUP03"
    message = (
        "Multiple variables with name '{name}' in Variables section (first occurrence in line "
        "{first_occurrence_line}). Note that Robot Framework is case-insensitive"
    )
    severity = RuleSeverity.ERROR
    added_in_version = "1.0.0"


class DuplicatedResourceRule(Rule):
    name = "duplicated-resource"
    rule_id = "DUP04"
    message = "Multiple resource imports with path '{name}' (first occurrence in line {first_occurrence_line})"
    severity = RuleSeverity.WARNING
    added_in_version = "1.0.0"


class DuplicatedLibraryRule(Rule):
    """
    If you need to reimport library use alias::

        *** Settings ***
        Library  RobotLibrary
        Library  RobotLibrary  AS  OtherRobotLibrary

    """

    name = "duplicated-library"
    rule_id = "DUP05"
    message = (
        "Multiple library imports with name '{name}' and identical arguments (first occurrence in line "
        "{first_occurrence_line})"
    )
    severity = RuleSeverity.WARNING
    added_in_version = "1.0.0"


class DuplicatedMetadataRule(Rule):
    name = "duplicated-metadata"
    rule_id = "DUP06"
    message = "Duplicated metadata '{name}' (first occurrence in line {first_occurrence_line})"
    severity = RuleSeverity.WARNING
    added_in_version = "1.0.0"


class DuplicatedVariablesImportRule(Rule):
    name = "duplicated-variables-import"
    rule_id = "DUP07"
    message = "Duplicated variables import with path '{name}' (first occurrence in line {first_occurrence_line})"
    severity = RuleSeverity.WARNING
    added_in_version = "1.0.0"


class SectionAlreadyDefinedRule(Rule):
    """
    Duplicated section in the file. Robot Framework will handle repeated sections but it is recommended to not
    duplicate them.

    Example::

        *** Test Cases ***
        My Test
            Keyword

        *** Keywords ***
        Keyword
            No Operation

        *** Test Cases ***  # duplicate
        Other Test
            Keyword
    """

    name = "section-already-defined"
    rule_id = "DUP08"
    message = (
        "'{section_name}' section header already defined in file (first occurrence in line " "{first_occurrence_line})"
    )
    severity = RuleSeverity.WARNING
    added_in_version = "1.0.0"


class SectionOutOfOrderRule(Rule):  # FIXME it is not dup, more like ORD
    """
    # TODO explain why
    Sections should be defined in order set by ``sections_order``
    parameter (default: ``settings,variables,testcases,keywords``).

    To change the default order use following option::

        robocop check configure section-out-of-order:sections_order:comma,separated,list,of,sections

    where section should be case-insensitive name from the list: comments, settings, variables, testcases, keywords.
    Order of not configured sections is ignored.

    Example::

        *** Settings ***

        *** Keywords ***

        *** Test Cases ***  # it will report issue because Test Cases should be defined before Keywords

    """

    name = "section-out-of-order"
    rule_id = "DUP09"
    message = "'{section_name}' section header is defined in wrong order: {recommended_order}"
    severity = RuleSeverity.WARNING
    added_in_version = "1.0.0"
    parameters = [
        RuleParam(
            name="sections_order",
            default="settings,variables,testcases,keywords",
            converter=configure_sections_order,
            show_type="str",
            desc="order of sections in comma-separated list",
        )
    ]


class BothTestsAndTasksRule(Rule):
    """
    The file contains both ``*** Test Cases ***`` and ``*** Tasks ***`` sections. Use only one of them. ::

    *** Test Cases ***

    *** Tasks ***
    """

    name = "both-tests-and-tasks"
    rule_id = "DUP10"
    message = "Both Task(s) and Test Case(s) section headers defined in file"
    severity = RuleSeverity.ERROR
    added_in_version = "1.0.0"


class DuplicatedArgumentRule(Rule):
    """
    Variable names in Robot Framework are case-insensitive and ignores spaces and underscores. Following arguments
    are duplicates::

        *** Keywords ***
        Keyword
            [Arguments]    ${var}  ${VAR}  ${v_ar}  ${v ar}
            Other Keyword
    """

    name = "duplicated-argument-name"
    rule_id = "DUP11"
    message = "Argument name '{argument_name}' is already used"
    severity = RuleSeverity.ERROR
    added_in_version = "1.11.0"


class DuplicatedAssignedVarNameRule(Rule):
    """
    Variable names in Robot Framework are case-insensitive and ignores spaces and underscores. Following variables
    are duplicates::

        *** Test Cases ***
        Test
            ${var}  ${VAR}  ${v_ar}  ${v ar}  Keyword

    It is possible to use `${_}` to note that variable name is not important and will not be used::

        *** Keywords ***
        Get Middle Element
            [Arguments]    ${list}
            ${_}    ${middle}    ${_}    Split List    ${list}
            RETURN    ${middle}
    """

    name = "duplicated-assigned-var-name"
    rule_id = "DUP12"
    message = "Assigned variable name '{variable_name}' is already used"
    severity = RuleSeverity.INFO
    added_in_version = "1.12.0"


class DuplicatedSettingRule(Rule):
    """
    Some settings can be used only once in a file. Only the first value is used.
    Example::

        *** Settings ***
        Force Tags        F1
        Force Tags        F2  # this setting will be ignored
    """

    name = "duplicated-setting"
    rule_id = "DUP13"
    message = "{error_msg}"
    severity = RuleSeverity.WARNING
    added_in_version = "2.0"


class DuplicationsChecker(VisitorChecker):
    """Checker for duplicated names."""

    duplicated_test_case: DuplicatedTestCaseRule
    duplicated_keyword: DuplicatedKeywordRule
    duplicated_variable: DuplicatedVariableRule
    duplicated_resource: DuplicatedResourceRule
    duplicated_library: DuplicatedLibraryRule
    duplicated_metadata: DuplicatedMetadataRule
    duplicated_variables_import: DuplicatedVariablesImportRule
    duplicated_argument_name: DuplicatedArgumentRule
    duplicated_assigned_var_name: DuplicatedAssignedVarNameRule
    duplicated_setting: DuplicatedSettingRule

    def __init__(self):
        self.test_cases = defaultdict(list)
        self.keywords = defaultdict(list)
        self.variables = defaultdict(list)
        self.resources = defaultdict(list)
        self.libraries = defaultdict(list)
        self.metadata = defaultdict(list)
        self.variable_imports = defaultdict(list)
        super().__init__()

    def visit_File(self, node) -> None:  # noqa: N802
        self.test_cases = defaultdict(list)
        self.keywords = defaultdict(list)
        self.variables = defaultdict(list)
        self.resources = defaultdict(list)
        self.libraries = defaultdict(list)
        self.metadata = defaultdict(list)
        self.variable_imports = defaultdict(list)
        super().visit_File(node)
        self.check_duplicates(self.test_cases, self.duplicated_test_case)
        self.check_duplicates(self.keywords, self.duplicated_keyword)
        self.check_duplicates(self.variables, self.duplicated_variable)
        self.check_duplicates(self.resources, self.duplicated_resource, underline_whole_line=True)
        self.check_duplicates(self.metadata, self.duplicated_metadata, underline_whole_line=True)
        self.check_duplicates(self.variable_imports, self.duplicated_variables_import, underline_whole_line=True)
        self.check_library_duplicates(self.libraries, self.duplicated_library)

    def check_duplicates(self, container, rule, underline_whole_line=False) -> None:
        for nodes in container.values():
            for duplicate in nodes[1:]:
                if underline_whole_line:
                    end_col = duplicate.end_col_offset + 1
                else:
                    end_col = duplicate.col_offset + len(duplicate.name) + 1
                self.report(
                    rule, name=duplicate.name, first_occurrence_line=nodes[0].lineno, node=duplicate, end_col=end_col
                )

    def check_library_duplicates(self, container, rule) -> None:
        for nodes in container.values():
            for duplicate in nodes[1:]:
                lib_token = duplicate.get_token(Token.NAME)
                self.report(
                    rule,
                    name=duplicate.name,
                    first_occurrence_line=nodes[0].lineno,
                    node=duplicate,
                    col=lib_token.col_offset + 1,
                    end_col=lib_token.end_col_offset + 1,
                )

    def visit_TestCase(self, node) -> None:  # noqa: N802
        testcase_name = normalize_robot_name(node.name)
        self.test_cases[testcase_name].append(node)
        self.generic_visit(node)

    def visit_Keyword(self, node) -> None:  # noqa: N802
        keyword_name = normalize_robot_name(node.name)
        self.keywords[keyword_name].append(node)
        self.generic_visit(node)

    def visit_KeywordCall(self, node) -> None:  # noqa: N802
        assign = node.get_tokens(Token.ASSIGN)
        seen = set()
        for var in assign:
            var_name, *_ = var.value.split("=", maxsplit=1)
            name = normalize_robot_var_name(var_name)
            if not name:  # ie. "${_}" -> ""
                return
            if name in seen:
                self.report(
                    self.duplicated_assigned_var_name,
                    variable_name=var_name,
                    node=node,
                    lineno=var.lineno,
                    col=var.col_offset + 1,
                    end_col=var.col_offset + len(var.value) + 1,
                )
            else:
                seen.add(name)

    def visit_VariableSection(self, node) -> None:  # noqa: N802
        self.generic_visit(node)

    def visit_Variable(self, node) -> None:  # noqa: N802
        if not node.name or get_errors(node):
            return
        var_name = normalize_robot_name(self.replace_chars(node.name, "${}@&"))
        self.variables[var_name].append(node)

    @staticmethod
    def replace_chars(name, chars):
        return "".join(c for c in name if c not in chars)

    def visit_ResourceImport(self, node) -> None:  # noqa: N802
        if node.name:
            self.resources[node.name].append(node)

    def visit_LibraryImport(self, node) -> None:  # noqa: N802
        if not node.name:
            return
        lib_name = node.alias if node.alias else node.name
        name_with_args = lib_name + "".join(token.value for token in node.get_tokens(Token.ARGUMENT))
        self.libraries[name_with_args].append(node)

    def visit_Metadata(self, node) -> None:  # noqa: N802
        if node.name is not None:
            self.metadata[node.name + node.value].append(node)

    def visit_VariablesImport(self, node) -> None:  # noqa: N802
        if not node.name:
            return
        # only YAML files can't have arguments - covered in E0404 variables-import-with-args
        if node.name.endswith((".yaml", ".yml")) and node.get_token(Token.ARGUMENT):
            return
        name_with_args = node.name + "".join(token.value for token in node.data_tokens[2:])
        self.variable_imports[name_with_args].append(node)

    def visit_Arguments(self, node) -> None:  # noqa: N802
        args = set()
        for arg in node.get_tokens(Token.ARGUMENT):
            orig, *_ = arg.value.split("=", maxsplit=1)
            name = normalize_robot_var_name(orig)
            if name in args:  # TODO could be handled with other variables rules
                self.report(
                    self.duplicated_argument_name,
                    argument_name=orig,
                    node=node,
                    lineno=arg.lineno,
                    col=arg.col_offset + 1,
                    end_col=arg.col_offset + len(orig) + 1,
                )
            else:
                args.add(name)

    def visit_Error(self, node) -> None:  # noqa: N802
        for error in get_errors(node):
            if "is allowed only once" in error:
                self.report(
                    self.duplicated_setting, error_msg=error, node=node, end_col=node.data_tokens[0].end_col_offset
                )


class SectionHeadersChecker(VisitorChecker):
    """Checker for duplicated or out of order section headers."""

    section_already_defined: SectionAlreadyDefinedRule
    section_out_of_order: SectionOutOfOrderRule
    both_tests_and_tasks: BothTestsAndTasksRule

    def __init__(self):
        self.sections_by_order = []
        self.sections_by_existence = {}
        super().__init__()

    @staticmethod
    def section_order_to_str(order):
        by_index = sorted(order.items(), key=lambda x: x[1])
        name_map = {
            Token.SETTING_HEADER: "Settings",
            Token.VARIABLE_HEADER: "Variables",
            Token.TESTCASE_HEADER: "Test Cases / Tasks",
            "TASK HEADER": "Test Cases / Tasks",
            Token.KEYWORD_HEADER: "Keywords",
        }
        order_str = []
        for name, _ in by_index:
            mapped_name = name_map[name]
            if mapped_name not in order_str:
                order_str.append(mapped_name)
        return " > ".join(order_str)

    def visit_File(self, node) -> None:  # noqa: N802
        self.sections_by_order = []
        self.sections_by_existence = {}
        super().visit_File(node)

    def visit_SectionHeader(self, node) -> None:  # noqa: N802
        section_name = node.type
        if section_name not in self.section_out_of_order.sections_order:
            return
        if section_name in (Token.TESTCASE_HEADER, "TASK HEADER"):
            # a bit awkward implementation because before RF 6.0 task header used TESTCASE_HEADER type
            if "task" in node.name.lower():
                section_name = "TASK HEADER"
                if Token.TESTCASE_HEADER in self.sections_by_existence:
                    self.report(
                        self.both_tests_and_tasks, node=node, col=node.col_offset + 1, end_col=node.end_col_offset
                    )
            elif "TASK HEADER" in self.sections_by_existence:
                self.report(self.both_tests_and_tasks, node=node, col=node.col_offset + 1, end_col=node.end_col_offset)
        order_id = self.section_out_of_order.sections_order[section_name]
        if section_name in self.sections_by_existence:
            self.report(
                self.section_already_defined,
                section_name=node.data_tokens[0].value,
                first_occurrence_line=self.sections_by_existence[section_name],
                node=node,
                end_col=node.end_col_offset,
            )
        else:
            self.sections_by_existence[section_name] = node.lineno
        if any(previous_id > order_id for previous_id in self.sections_by_order):
            token = node.data_tokens[0]
            self.report(
                self.section_out_of_order,
                section_name=token.value,
                recommended_order=self.section_order_to_str(self.section_out_of_order.sections_order),
                node=node,
                end_col=token.end_col_offset + 1,
            )
        self.sections_by_order.append(order_id)
