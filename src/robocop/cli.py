import typer


app = typer.Typer(
    help="Static code analysis tool (linter) and code formatter for Robot Framework. "
    "Full documentation available at https://robocop.readthedocs.io .",
    rich_markup_mode="rich",
)


@app.command(name="check")
def check_files():
    """Lint files."""
    pass


@app.command(name="format")
def format_files():
    """Format files."""
    pass


@app.command(name="list")
def list_rules_or_formatters():
    """List available rules or formatters."""
    pass


# list configurables, reports, rules, formatters


def main():
    app()
