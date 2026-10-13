from typing import Callable
from logging import getLogger

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from uuid import uuid4
from pydantic import BaseModel, create_model
from langchain_core.messages import RemoveMessage, SystemMessage


logger = getLogger(__name__)

class FailedToSelfCorrect(Exception): pass

def nudged_agent(agent: CompiledStateGraph | StateGraph, validator: Callable, nudge_text: str, max_retries: int = 2) -> CompiledStateGraph:
    """Wrap a compiled agent graph so its last message must pass `validator(message) -> bool`.

    On failure, the bad message is removed and `nudge_text` is appended as a SystemMessage,
    then the agent reruns. On success, all nudges are purged from state and the graph ends.
    Raises `FailedToSelfCorrect` after `max_retries` total attempts. The returned graph keeps
    the agent's name and state schema (plus an internal `nudge_ids` field), so it's a drop-in replacement.
    """

    agent_name = agent.name
    
    max_retries -= 1 # cuz the check happens before appending the nudge

    def validator_node(state: BaseModel) -> dict:
        latest = state.messages[-1]

        if validator(latest):
            # 🧹 purge the nudges, keep the validated message
            return {"messages": [RemoveMessage(id=i) for i in state.nudge_ids], "nudge_ids": []}

        count = len(state.nudge_ids)
        if count >= max_retries:
            raise FailedToSelfCorrect(f"{agent_name} failed validation after {max_retries} retries")
        logger.warning(f"🔁{agent_name} failed to validate the latest message, {max_retries - count} tries remaining. Nudging...")
        nudge = SystemMessage(content=nudge_text, id=str(uuid4()))
        return {"messages": [RemoveMessage(id=latest.id), nudge], "nudge_ids": [*state.nudge_ids, nudge.id]}

    def route_after_validation(state: BaseModel) -> str:
        return agent_name if state.nudge_ids else END  # ✅ END once validated (nudges purged)


    if isinstance(agent, CompiledStateGraph):
        state_schema = agent.builder.state_schema
    else:
        state_schema = agent.state_schema

    # 🔌 reuse whatever pydantic state the agent uses, plus the nudge-id tracker (O(1) count, O(k) purge)
    graph = StateGraph(create_model("NudgedState", __base__=state_schema, nudge_ids=(list[str], [])))
    graph.add_node(agent_name, agent)
    graph.add_node("validator_node", validator_node)
    graph.add_edge(START, agent_name)
    graph.add_edge(agent_name, "validator_node")
    graph.add_conditional_edges("validator_node", route_after_validation, [agent_name, END])

    return graph.compile(name=agent_name)