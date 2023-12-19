from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from pydantic import Field
from langchain_core.vectorstores import VectorStore
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores.chroma import Chroma
from langchain_community.embeddings.openai import OpenAIEmbeddings

from AFAAS.lib.task.plan import Plan
from AFAAS.interfaces.db import AbstractMemory
from AFAAS.core.workspace.local import AGPTLocalFileWorkspace
from AFAAS.interfaces.adapters import AbstractLanguageModelProvider
from AFAAS.core.adapters.openai import AFAASChatOpenAI, OpenAISettings
from AFAAS.core.tools import TOOL_CATEGORIES, SimpleToolRegistry

from AFAAS.interfaces.agent import BaseAgent, BaseLoopHook, BasePromptManager, ToolExecutor
from .loop import PlannerLoop
from .models import PlannerAgentConfiguration  # PlannerAgentSystemSettings,
from .models import PlannerAgentSystems
from AFAAS.lib.sdk.logger import AFAASLogger

LOG = AFAASLogger(name=__name__)

if TYPE_CHECKING:
    from AFAAS.interfaces.workspace import AbstractFileWorkspace


class PlannerAgent(BaseAgent):
    ################################################################################
    ##################### REFERENCE SETTINGS FOR FACTORY ###########################
    ################################################################################

    CLASS_CONFIGURATION = PlannerAgentConfiguration
    CLASS_SYSTEMS = PlannerAgentSystems  # PlannerAgentSystems() = cls.SystemSettings().configuration.systems

    class SystemSettings(BaseAgent.SystemSettings):
        name: str = "simple_agent"
        description: str = "A simple agent."
        configuration: PlannerAgentConfiguration = PlannerAgentConfiguration()

        tool_registry: SimpleToolRegistry.SystemSettings = (
            SimpleToolRegistry.SystemSettings()
        )

        agent_name: str = Field(default="New Agent")
        agent_goals: Optional[list]
        agent_goal_sentence: Optional[str]

        class Config(BaseAgent.SystemSettings.Config):
            pass

        def json(self, *args, **kwargs):
            self.prepare_values_before_serialization()  # Call the custom treatment before .json()
            kwargs["exclude"] = self.Config.default_exclude
            return super().json(*args, **kwargs)

    def __init__(
        self,
        settings: PlannerAgent.SystemSettings,
        user_id: uuid.UUID,
        agent_id: uuid.UUID = SystemSettings.generate_uuid(),
        memory :  AbstractMemory = AbstractMemory.get_adapter(),
        default_llm_provider: AbstractLanguageModelProvider = AFAASChatOpenAI(),
        workspace: AbstractFileWorkspace = AGPTLocalFileWorkspace(),
        prompt_manager: BasePromptManager = BasePromptManager(),
        loop : PlannerLoop = PlannerLoop(),
        tool_registry = SimpleToolRegistry,
        tool_handler : ToolExecutor = ToolExecutor(),
        vectorstores: VectorStore = Chroma(),
        embeddings : Embeddings =   OpenAIEmbeddings(),
        **kwargs,
    ):
        super().__init__(
            settings=settings,
            memory=memory,
            workspace=workspace,
            default_llm_provider=default_llm_provider,
            prompt_manager=prompt_manager,
            user_id=user_id,
            agent_id=agent_id,
            vectorstores=vectorstores,
            embeddings = embeddings,
        )

        self.agent_goals = settings.agent_goals #TODO: Remove & make it part of the plan ?
        self.agent_goal_sentence = settings.agent_goal_sentence

        #
        # Step 4 : Set the ToolRegistry
        #
        self._tool_registry = tool_registry.with_tool_modules(
            modules=TOOL_CATEGORIES,
            agent=self,
            memory=memory,
            workspace=workspace,
            model_providers=default_llm_provider,
        )
        # self._tool_registry.set_agent(agent=self)

        ###
        ### Step 5 : Create the Loop
        ###
        self._loop : PlannerLoop = loop
        self._loop.set_agent(agent=self)

        # Set tool Executor
        self._tool_executor : ToolExecutor = tool_handler
        self._tool_executor.set_agent(agent=self)

        ###
        ### Step 5a : Create the plan
        ###
        # FIXME: Long term : PlannerLoop / Pipeline get all ready tasks & launch them => Parralelle processing of tasks
        if hasattr(settings, "plan_id") and settings.plan_id is not None:
            self.plan: Plan = Plan.get_plan_from_db(
                plan_id=settings.plan_id, agent=self
            )  # Plan(user_id=user_id)
            # task = self.plan.find_first_ready_task()
            # self._loop.set_current_task(task = task)
            self._loop.set_current_task(task=self.plan.get_next_task())
        else:
            self.plan: Plan = Plan.create_in_db(agent=self)
            # self._loop.add_initial_tasks()
            self._loop.set_current_task(task=self.plan.get_ready_tasks()[0])
            self.plan_id = self.plan.plan_id

        ###
        ### Step 6 : add hooks/pluggins to the loop
        ###
        # TODO : Get hook added from configuration files
        # Exemple :
        # self.add_hook( hook: BaseLoopHook, uuid: uuid.UUID)
        self.add_hook(
            hook=BaseLoopHook(
                name="begin_run",
                function=test_hook,
                kwargs=["foo_bar"],
                expected_return=True,
                callback_function=None,
            ),
            uuid=uuid.uuid4(),
        )

    def loophooks(self) -> PlannerLoop.LoophooksDict:
        if not self._loop._loophooks:
            self._loop._loophooks = {}
        return self._loop._loophooks

    def loop(self) -> PlannerLoop:
        return self._loop

    def add_hook(self, hook: BaseLoopHook, uuid: uuid.UUID):
        super().add_hook(hook, uuid)

    ################################################################################
    ################################ LOOP MANAGEMENT################################
    ################################################################################

    async def start(
        self,
        user_input_handler: Callable[[str], Awaitable[str]],
        user_message_handler: Callable[[str], Awaitable[str]],
    ):
        return_var = await super().start(
            user_input_handler=user_input_handler,
            user_message_handler=user_message_handler,
        )
        return return_var

    async def stop(
        self,
        user_input_handler: Callable[[str], Awaitable[str]],
        user_message_handler: Callable[[str], Awaitable[str]],
    ):
        return_var = await super().stop(
            agent=self,
            user_input_handler=user_input_handler,
            user_message_handler=user_message_handler,
        )
        return return_var

    ################################################################################
    ################################FACTORY SPECIFIC################################
    ################################################################################

    @classmethod
    def _create_agent_custom_treatment(
        cls,
        agent_settings: PlannerAgent.SystemSettings,
    ) -> None:
        return cls._create_workspace(agent_settings=agent_settings)

    @classmethod
    def _create_workspace(
        cls,
        agent_settings: PlannerAgent.SystemSettings,
    ):
        from AFAAS.interfaces.workspace import AbstractFileWorkspace

        return agent_settings.workspace.__class__.create_workspace(
            user_id=agent_settings.user_id,
            agent_id=agent_settings.agent_id,
            settings=agent_settings,
        )

    def __repr__(self):
        return "PlannerAgent()"


def test_hook(**kwargs):
    LOG.notice("Entering test_hook Function")
    LOG.notice(
        "Hooks are an experimental plug-in system that may fade away as we are transiting from a Loop logic to a Pipeline logic."
    )
    test = "foo_bar"
    for key, value in kwargs.items():
        LOG.debug(f"{key}: {value}")
