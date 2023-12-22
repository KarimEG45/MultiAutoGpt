from __future__ import annotations

import enum
import os
import uuid
from typing import TYPE_CHECKING, Any, Callable, Optional

from langchain.tools import DuckDuckGoSearchRun

if TYPE_CHECKING:
    from AFAAS.interfaces.task import AbstractTask

from AFAAS.interfaces.adapters import (
    AbstractLanguageModelProvider,
    AbstractPromptConfiguration,
    AssistantChatMessageDict,
    ChatMessage,
    ChatPrompt,
    CompletionModelFunction,
)
from AFAAS.interfaces.prompts.strategy import (
    AbstractPromptStrategy,
    DefaultParsedResponse,
    PromptStrategiesConfiguration,
)
from AFAAS.lib.sdk.logger import AFAASLogger
from AFAAS.lib.utils.json_schema import JSONSchema

LOG = AFAASLogger(name=__name__)


class BaseTaskSummaryStrategyFunctionNames(str, enum.Enum):
    DEFAULT_TASK_SUMMARY: str = "afaas_default_task_summary"


class BaseTaskSummaryStrategyConfiguration(PromptStrategiesConfiguration):
    """
    A Pydantic model that represents the default configurations for the refine user context strategy.
    """

    default_tool_choice: BaseTaskSummaryStrategyFunctionNames = (
        BaseTaskSummaryStrategyFunctionNames.DEFAULT_TASK_SUMMARY
    )
    task_output_lenght: int = 150
    temperature: float = 0.4


class BaseTaskSummary_Strategy(AbstractPromptStrategy):
    default_configuration = BaseTaskSummaryStrategyConfiguration()
    STRATEGY_NAME = "afaas_default_task_summary"

    def __init__(
        self,
        default_tool_choice: BaseTaskSummaryStrategyFunctionNames,
        temperature: float,
        count=0,
        exit_token: str = str(uuid.uuid4()),
        task_output_lenght: int = 300,
    ):
        # self._model_classification = model_classification
        self._count = count
        self._config = self.default_configuration
        self.default_tool_choice = default_tool_choice
        self.task_output_lenght = task_output_lenght

    def set_tools(
        self,
        task: AbstractTask,
        **kwargs,
    ):
        self.afaas_default_task_summary: CompletionModelFunction = CompletionModelFunction(
            name=BaseTaskSummaryStrategyFunctionNames.DEFAULT_TASK_SUMMARY.value,
            description="Provide detailed information about the task and the context of the task to the Agent responsible or completing the task.",
            parameters={
                "text_output": JSONSchema(
                    type=JSONSchema.Type.STRING,
                    description=f"All the information with regards to what have been donne in the task. This note should be {str(self.task_output_lenght * 0.8)} to {str(self.task_output_lenght *  1.25)} words long.",
                    required=True,
                ),
                "text_output_as_uml": JSONSchema(
                    type=JSONSchema.Type.ARRAY,
                    items=JSONSchema(
                        type=JSONSchema.Type.STRING,
                        description=f"UML diagrams in PlantUML notation that may help any one to understand the task. Accepts Class Diagram, Object Diagram, Package Diagram, Component Diagram, Composite Structure Diagram, Deployment Diagram, Activity Diagram, State Machine Diagram, Use Case Diagram, Sequence Diagram, Communication Diagram, Interaction Overview Diagram, Timing Diagram",
                        required=True,
                    ),
                ),
                "archimate_diagrams": JSONSchema(
                    type=JSONSchema.Type.ARRAY,
                    items=JSONSchema(
                        type=JSONSchema.Type.STRING,
                        description=f"Architectural diagrams in PlantUML notation that may help any one to understand the task",
                        required=False,
                    ),
                ),
                "gant_diagrams": JSONSchema(
                    type=JSONSchema.Type.ARRAY,
                    items=JSONSchema(
                        type=JSONSchema.Type.STRING,
                        description=f"Gantt diagrams in PlantUML notation that may help any one to understand the task",
                        required=False,
                    ),
                ),
            },
        )

        self._tools = [
            self.afaas_default_task_summary,
        ]

    from AFAAS.core.tools import Tool

    def build_message(
        self, task: AbstractTask, tool: Tool, documents: list, **kwargs
    ) -> ChatPrompt:
        LOG.debug("Building prompt for task : " + task.debug_dump_str())
        self._task: AbstractTask = task
        self._model_name = kwargs.get("model_name")

        # FIXME: This his a hack for test, please remove it :
        task.task_context = "No additional context"
        task.tech_summary_task_context = task.task_context

        task_summary_param = {
            "tool_output": kwargs.get("tool_output", None),
            "tool": tool,
            "documents": documents,
        }

        messages = []
        messages.append(
            ChatMessage.system(
                self._build_jinja_message(
                    task=task,
                    template_name=f"{self.STRATEGY_NAME}.jinja",
                    template_params=task_summary_param,
                )
            )
        )
        messages.append(ChatMessage.system(self.response_format_instruction()))

        return self.build_chat_prompt(messages=messages)

    def parse_response_content(
        self,
        response_content: AssistantChatMessageDict,
    ) -> DefaultParsedResponse:
        return self.default_parse_response_content(response_content=response_content)

    def response_format_instruction(self) -> str:
        return super().response_format_instruction()

    def get_llm_provider(self) -> AbstractLanguageModelProvider:
        return super().get_llm_provider()

    def get_prompt_config(self) -> AbstractPromptConfiguration:
        return super().get_prompt_config()
