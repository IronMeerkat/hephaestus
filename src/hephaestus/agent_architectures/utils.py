import operator
from typing import Annotated, Any, Callable

from langchain_core.messages import AnyMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph.message import add_messages

from pydantic import BaseModel


class AgentSwarmState(BaseModel, extra='allow'):
    """🐝 Shared state flowing through every node in an agent swarm."""

    # messages: Annotated[list[AnyMessage], operator.add]
    messages: Annotated[list[AnyMessage], add_messages]



def message_delta(input_messages: list[AnyMessage], output_messages: list[AnyMessage]) -> list[AnyMessage]:
    len_input = len(input_messages)
    len_output = len(output_messages)
    return output_messages[len_input:] if len_input <= len_output else []


def _wrap_agent_return_delta(agent: object) -> object:
    """Wrap an agent so it returns only the messages it added (delta), not the full list.

    Child agents return their full accumulated messages. With operator.add, the swarm
    would concatenate that with its current state, duplicating all prior messages.
    This wrapper extracts only the new messages the agent produced.
    """

    async def wrapper(state: AgentSwarmState, config: RunnableConfig | None = None) -> dict:
        invoke_config = dict(config) if config else {}
        invoke_config["run_name"] = agent.name  # preserve character name in Langfuse when subgraph
        result = await agent.ainvoke({"messages": state.messages}, invoke_config)
        output_messages = result['messages']
        delta = message_delta(state.messages, output_messages)
        return {"messages": delta}

    return wrapper


def function_to_graph(
    func: Callable[..., Any],
    state_schema: type[BaseModel] = AgentSwarmState,
    name: str | None = None,
) -> CompiledStateGraph:
    """🔧 Wrap any sync/async callable (state -> state update) into a one-node graph.

    The result can be passed to `parent.add_node(...)` like any other node.
    """
    name = name or getattr(func, "__name__", "function")
    graph = StateGraph(state_schema)
    graph.add_node(name, func)
    graph.add_edge(START, name)
    graph.add_edge(name, END)
    return graph.compile(name=name)
