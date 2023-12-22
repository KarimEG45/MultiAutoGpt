from __future__ import annotations

import logging
from typing import Callable, Iterable, TypeVar

from autogpt.models.command import Command
from colorama import Fore, Style
from openai.error import APIError, RateLimitError, ServiceUnavailableError, Timeout
from openai.openai_object import OpenAIObject

from AFAAS.interfaces.adapters import CompletionModelFunction

logger = logging.getLogger(__name__)


T = TypeVar("T", bound=Callable)


def get_openai_command_specs(
    commands: Iterable[Command],
) -> list[CompletionModelFunction]:
    """Get OpenAI-consumable function specs for the agent's available commands.
    see https://platform.openai.com/docs/guides/gpt/function-calling
    """
    return [
        CompletionModelFunction(
            name=command.name,
            description=command.description,
            parameters={param.name: param.spec for param in command.parameters},
        )
        for command in commands
    ]
