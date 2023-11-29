from __future__ import annotations
from abc import ABCMeta

import uuid
from logging import Logger
from typing import TYPE_CHECKING, ClassVar

from pydantic import Field

from .meta import TaskStatusList

from .base import BaseTask
from .task import Task
# from autogpts.autogpt.autogpt.core.memory import
from ...sdk.forge_log import ForgeLogger

LOG = ForgeLogger(name=__name__)


from autogpts.autogpt.autogpt.core.agents import AbstractAgent


class Plan(BaseTask):

    _instance: ClassVar[dict[Plan]] = {}
    _modified_tasks_ids: list[str] = []
    _new_tasks_ids: list[str] = []
    _all_task_ids: list[str] = []
    _ready_task_ids: list[str] = []
    _loaded_tasks_dict: dict[Task] = {}


    # def dict(self, *args, **kwargs):
    #     exclude = set(kwargs.get("exclude", []))
    #     exclude.add("agent")
    #     kwargs["exclude"] = exclude
    #     data = super().dict(*args, **kwargs)
    #     data["myagent_id"] = self.agent_id
    #     return data

    # def json(self, *args, **kwargs):
    #     exclude = set(kwargs.get("exclude", []))
    #     exclude.add("agent")
    #     kwargs["exclude"] = exclude
    #     data = super().json(*args, **kwargs)
    #     data = data[:-1] + f', "myagent_id": "{self.agent_id}"' + data[-1:]
    #     return data

    def __init__(self,
                 *args,
                 **kwargs):

        if kwargs["agent"].agent_id in Plan._instance:
            self = Plan._instance[kwargs["agent"].agent_id]
            return None

        # Initialize the instance if needed
        super().__init__(**kwargs)
        Plan._instance[kwargs["agent"].agent_id ] = self
        self.agent.plan : Plan = self

        # Load the tasks from the database
        agent : AbstractAgent = kwargs["agent"]
        memory = agent._memory
        task_table = memory.get_table("tasks")
        all_task = task_table.list(filter={"plan_id": self.plan_id})

        # Update the static variables
        for task in all_task:
            #Plan._loaded_tasks_dict[task.task_id] = task
            self._all_task_ids.append(task.task_id)
            if task.state == TaskStatusList.READY.value:
                self._ready_task_ids.append(task.task_id)

        

    """
    Represents a plan consisting of a list of tasks.
    """
    # class Config(BaseTask):
    #     allow_population_by_field_name = True

    task_id: str = Field(
        default_factory=lambda: Plan.generate_uuid(),
        alias="plan_id"
    )

    @staticmethod
    def generate_uuid():
        return "PL" + str(uuid.uuid4())

    @property
    def plan_id(self):
        return self.task_id

    def generate_pitch(self, task=None):
        if task is None:
            task = self.get_first_ready_task()

        # Extract the task's siblings and path
        siblings = [
            sib
            for sib in self.subtasks
            if sib.task_parent_id == task.task_parent_id and sib != task
        ]
        path_to_task = task.find_task_path()

        # Build the pitch
        pitch = """
        # INSTRUCTION
        Your goal is to find the best-suited command in order to achieve the following task: {task_description}

        # CONTEXT
        The high-level plan designed to achieve our goal is: 
        {high_level_plan}
        
        We are working on the task "{task_name}" that consists in: {task_command}. This task is located in:
        {path_structure}
        """.format(
            task_description=task.description,
            high_level_plan="\n".join(
                [
                    "{}: {}".format(t.task_goal, t.description)
                    for t in self.subtasks
                    if not t.task_parent_id
                ]
            ),
            task_name=task.task_goal,
            task_command=task.command,  # assuming each task has a 'command' attribute
            path_structure="\n".join(["->".join(p.task_goal for p in path_to_task)]),
        )

        return pitch
    

    def get_task(self, task_id: str) -> Task:
        """
        Get a task from the plan
        """
        task : Task = None
        if task_id in self._all_task_ids:
            
            task =  self._loaded_tasks_dict.get(task_id)
            if task is None:
                task =  Task(**task.get_from_db(task_id))
                self._loaded_tasks_dict[task_id] = task

            return task
        else : 
            raise Exception(f"Task {task_id} not found in plan {self.plan_id}")
        


    def get_ready_tasks(self, task_ids_set : list[str] = None) -> list[Task]:
        """
        Get the first ready tasks. 
        """

        # Fetch the Task objects based on the common task IDs
        return [self.get_task(task_id) for task_id in self._ready_task_ids]
    
    def get_first_ready_tasks(self, task_ids_set : list[str] = None) -> Task:
        """
        Get all ready tasks. If task_ids_set is not None, return only the tasks that are both ready and in the additional_task_ids list.
        """
        
        # Fetch the Task objects based on the common task IDs
        return self.get_task(self._ready_task_ids[0]) 
        


    def register_tasks(self, task: Task):
        self.register_tasks([task])
        


    def register_tasks(self, tasks: list[Task]):
        """
        Register a list of tasks in the plan
        """
        for task in tasks:
            self._all_task_ids.append(task.task_id)
            self._loaded_tasks_dict[task.task_id] = task
            if(task.state == TaskStatusList.READY.value):
                self._ready_task_ids.append(task.task_id)
            
            self.register_task_as_new(task_id=task.task_id)

    def register_task_as_modified(self, task_id: str):
        """
        Register a task as modified
        """
        if task_id not in self._modified_tasks_ids:
            self._modified_tasks_ids.append(task_id)

    def register_task_as_new(self, task_id: str):
        """
        Register a task as modified
        """
        if task_id not in self._new_tasks_ids:
            self._new_tasks_ids.append(task_id)
        
    #############################################################################################
    #############################################################################################
    #############################################################################################
    ### Database access
    #############################################################################################
    #############################################################################################
    #############################################################################################



    @classmethod
    def create_in_db(cls, agent: AbstractAgent):
            """
            Create a plan in the database for the given agent.

            Args:
                agent (AbstractAgent): The agent for which the plan is created.

            Returns:
                Plan: The created plan.

            """
            memory = agent._memory
            plan_table = memory.get_table("plans")

            plan = cls(agent_id=agent.agent_id,
                       task_goal=agent.agent_goal_sentence, 
                       tasks=[],
                       agent=agent
                       )
            
            plan._create_initial_tasks(status=TaskStatusList.READY)

            plan_table.add(plan, id=plan.plan_id)
            return plan

    def _create_initial_tasks(self, status: TaskStatusList):
        initial_task = Task(
            agent=self.agent,
            #plan=self,
            task_parent=self,
            _task_parent_id=self.plan_id,
            state=status.value,

            _task_predecessors_id=None,
            responsible_agent_id=None,

            task_goal=self.task_goal,
            command=Task.default_command(),
            arguments={'note_to_agent_length': 400},
            acceptance_criteria=[
                "A plan has been made to achieve the specific task"
            ],

        )
        # self._current_task = initial_task  # .task_id
        initial_task_list = [initial_task]

        ###
        # Step 2 : Prepend usercontext
        ###
        # FIXME: DEACTIVATED FOR TEST PURPOSE
        if False:
            try:
                import autogpts.autogpt.autogpt.core.agents.usercontext
                refine_user_context_task = Task(
                    # task_parent = self.plan() ,

                    agent = self.agent,
                    plan=self,
                    _task_parent_id=None,
                    _task_predecessors_id=None,
                    responsible_agent_id=None,
                    task_goal="Refine a user requirements for better exploitation by Agents",
                    command="afaas_refine_user_context",
                    acceptance_criteria=[
                        "The user has clearly and undoubtly stated his willingness to quit the process"
                    ],
                    arguments={},
                    state=TaskStatusList.READY,
                )
                initial_task_list = [refine_user_context_task] + initial_task_list
                # self._current_task = refine_user_context_task  # .task_id
            except:
                pass

        self.add_tasks(tasks=initial_task_list)

    
    async def save(self):

        ###
        # Step 1 : Lazy saving : Update Existing Tasks 
        ###
        for task_id in self._modified_tasks_ids:
            # Safeguard to avoid saving new tasks
            if task_id not in self._new_tasks_ids:
                task : Task = self._loaded_tasks_dict.get(task_id)
                if task:
                    task.save_in_db() # Save the task

        ###
        # Step 2 : Lazy saving : Create New Tasks 
        ###
        for task_id in self._new_tasks_ids:
            task : Task = self._loaded_tasks_dict.get(task_id)
            if task:
                task.create_in_db(task=task,agent=self.agent) # Save the task
        
        # Reinitalize the lists
        self._modified_tasks_ids = []
        self._new_tasks_ids = []

        ###
        # Step 3 : Save the Plan 
        ###
        agent = self._agent
        if agent:
            memory = agent._memory
            plan_table = memory.get_table("plans")
            plan_table.update(self.plan_id, self)

    @classmethod
    def get_plan_from_db(plan_id : str, agent : AbstractAgent):
        """
        Get a plan from the database
        """
        memory = agent._memory
        plan_table = memory.get_table("plans")
        plan_dict = plan_table.get(plan_id)
        return Plan(**plan_dict, agent=agent)
    

Plan.update_forward_refs()


# # 1. Find the first ready task
# first_ready_task = plan.get_first_ready_task()

# # 2. Retrieve the task and its siblings
# task_parent_id = first_ready_task.task_parent_id
# siblings = []
# if task_parent_id:
#     task_parent = plan.find_task(task_parent_id)
#     siblings = task_parent.subtasks

# # 3. Retrieve the list of tasks on the path
# path_to_task = plan.find_task_path(first_ready_task.task_id)