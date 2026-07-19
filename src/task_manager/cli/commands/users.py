from sys import stderr
from argparse import Namespace, ArgumentParser, ArgumentTypeError

import exceptions as app_exc
from dto.users import VerifyUserEmailData
from cli.runtime import CliRuntime


def configure_users_parser(parser: ArgumentParser) -> None:
    """Register administrative user commands on the provided parser."""
    commands = parser.add_subparsers(dest="user_command", required=True)
    verify_email_parser = commands.add_parser(
        "verify-email",
        help="Mark an existing user's email as verified.",
    )
    verify_email_parser.add_argument("email", type=_parse_email)
    verify_email_parser.set_defaults(command_handler=verify_email)


async def verify_email(args: Namespace, runtime: CliRuntime) -> int:
    data: VerifyUserEmailData = args.email
    try:
        user = await runtime.user_service.verify_user_email(data)
    except app_exc.UserNotFound:
        print("User not found.", file=stderr)
        return 1

    print(f"Email verified for {user.email} ({user.user_id}).")
    return 0


def _parse_email(value: str) -> VerifyUserEmailData:
    try:
        return VerifyUserEmailData(value)
    except ValueError as exc:
        raise ArgumentTypeError(str(exc)) from exc
