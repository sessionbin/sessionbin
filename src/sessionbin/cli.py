import click

CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
}


@click.command(context_settings=CONTEXT_SETTINGS)
def cli():
    """sessionbin CLI."""
    click.echo("sessionbin")
