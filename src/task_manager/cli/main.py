import asyncio
from typing import cast
from argparse import Namespace, ArgumentParser
from collections.abc import Awaitable, Callable, Sequence

from cli.runtime import CliRuntime
from cli.commands.users import configure_users_parser


CommandHandler = Callable[[Namespace, CliRuntime], Awaitable[int]]


def create_parser() -> ArgumentParser:
    """Create the root parser for Task Manager administrative commands."""
    parser = ArgumentParser(prog="task-manager", description="Task Manager administration CLI.")
    commands = parser.add_subparsers(dest="command", required=True)
    users_parser = commands.add_parser("users", help="Manage user accounts.")
    configure_users_parser(users_parser)
    return parser


async def run(argv: Sequence[str] | None = None) -> int:
    """Parse and execute one command with application-owned dependencies."""
    args = create_parser().parse_args(None if argv is None else list(argv))
    handler = cast(CommandHandler, args.command_handler)
    runtime = CliRuntime()
    try:
        return await handler(args, runtime)
    finally:
        await runtime.close()


def main() -> None:
    raise SystemExit(asyncio.run(run()))
