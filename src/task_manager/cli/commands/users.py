from sys import stderr
from argparse import Namespace, ArgumentParser, ArgumentTypeError

import exceptions as app_exc
from dto.agent_usage import SetAgentAccessData
from dto.users import VerifyUserEmailData
from domain.value_objects.agent_usage import AgentAccessLevel
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

    set_agent_access_parser = commands.add_parser(
        "set-agent-access",
        help="Set quota-limited or unmetered agent access for a user.",
    )
    set_agent_access_parser.add_argument("email", type=_parse_email)
    set_agent_access_parser.add_argument(
        "access_level",
        type=AgentAccessLevel,
        choices=list(AgentAccessLevel),
    )
    set_agent_access_parser.set_defaults(command_handler=set_agent_access)


async def verify_email(args: Namespace, runtime: CliRuntime) -> int:
    data = VerifyUserEmailData(args.email)
    try:
        user = await runtime.user_service.verify_user_email(data)
    except app_exc.UserNotFound:
        print("User not found.", file=stderr)
        return 1

    print(f"Email verified for {user.email} ({user.user_id}).")
    return 0


async def set_agent_access(args: Namespace, runtime: CliRuntime) -> int:
    data = SetAgentAccessData(email=args.email, access_level=args.access_level)
    try:
        access = await runtime.agent_usage_service.set_access_level(data)
    except app_exc.UserNotFound:
        print("User not found.", file=stderr)
        return 1

    print(f"Agent access set to {access.access_level.value} for {data.email}.")
    return 0


def _parse_email(value: str) -> str:
    try:
        return VerifyUserEmailData(value).email
    except ValueError as exc:
        raise ArgumentTypeError(str(exc)) from exc
