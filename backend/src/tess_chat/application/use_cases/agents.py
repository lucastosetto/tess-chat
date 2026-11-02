from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from tess_chat.application.ports.clock import Clock
from tess_chat.application.ports.llm import ModelOption
from tess_chat.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from tess_chat.domain import events
from tess_chat.domain.agent import Agent
from tess_chat.domain.errors import InvalidInput, NotFound

MAX_AGENTS = 20


async def load_agent(uow: UnitOfWork, user_id: UUID, agent_id: UUID) -> Agent:
    agent = await uow.agents.get(agent_id)
    if agent is None:
        raise NotFound("agent not found")
    agent.ensure_owned_by(user_id)
    return agent


def _check_model(model: str | None, models: Sequence[ModelOption]) -> None:
    if model and model not in {m.id for m in models}:
        raise InvalidInput(f"unknown model {model}")


@dataclass(frozen=True)
class ListAgents:
    uow: UnitOfWorkFactory

    async def execute(self, user_id: UUID) -> Sequence[Agent]:
        async with self.uow() as uow:
            return await uow.agents.list_for_owner(user_id)


@dataclass(frozen=True)
class SaveAgent:
    uow: UnitOfWorkFactory
    clock: Clock
    models: Sequence[ModelOption]

    async def execute(
        self,
        user_id: UUID,
        name: str,
        instructions: str,
        model: str | None,
        agent_id: UUID | None = None,
        tools: list[str] | None = None,
    ) -> Agent:
        _check_model(model, self.models)
        async with self.uow() as uow:
            now = self.clock.now()
            if agent_id is None:
                if len(await uow.agents.list_for_owner(user_id)) >= MAX_AGENTS:
                    raise InvalidInput(f"at most {MAX_AGENTS} agents")
                agent = Agent.create(user_id, name, instructions, model, now, tools)
                await uow.agents.add(agent)
                uow.record(events.agent_event("created", user_id, agent.id, name=agent.name))
            else:
                agent = await load_agent(uow, user_id, agent_id)
                agent.edit(name, instructions, model, now, tools)
                await uow.agents.update(agent)
                uow.record(events.agent_event("updated", user_id, agent.id, name=agent.name))
            await uow.commit()
            return agent


@dataclass(frozen=True)
class DeleteAgent:
    uow: UnitOfWorkFactory

    async def execute(self, user_id: UUID, agent_id: UUID) -> None:
        async with self.uow() as uow:
            agent = await load_agent(uow, user_id, agent_id)
            await uow.agents.delete(agent.id)
            uow.record(events.agent_event("deleted", user_id, agent.id, name=agent.name))
            await uow.commit()
