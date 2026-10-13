from logging import getLogger
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from hephaestus.agent_architectures.utils import AgentSwarmState, _wrap_agent_return_delta

logger = getLogger(__name__)
_STOP_TOKENS = {"", "end", "none", "finish", "done"}


class DynamicDaisyChainState(AgentSwarmState):
    next_agent: str = END
    step_count: int = 0
    agent_counts: dict[str, int] = {}


def create_dynamic_daisy_chain(
    *agents: CompiledStateGraph | StateGraph,
    router_agent: CompiledStateGraph | StateGraph,
    name: str,
    max_agent_turns: int = 1,
    max_steps: int | None = None,
) -> CompiledStateGraph:
    """🔀 Daisy chain where `router_agent` picks the next agent (or END) at each step."""
    if not all(hasattr(a, "name") for a in (*agents, router_agent)):
        raise ValueError("All agents and router_agent must have a name.")

    agent_names = {a.name for a in agents}
    max_steps = max_steps if max_steps is not None else len(agents) * max_agent_turns

    async def router_node(state: DynamicDaisyChainState, config: RunnableConfig | None = None) -> dict:
        if state.step_count >= max_steps or all(state.agent_counts.get(n, 0) >= max_agent_turns for n in agent_names):
            logger.info(f"🛑 {name}: step/turn limit reached ({state.step_count}/{max_steps}), ending.")
            return {"next_agent": END, "step_count": 0, "agent_counts": {}}

        res = await router_agent.ainvoke({"messages": state.messages}, {**(config or {}), "run_name": router_agent.name})
        choice = str(res["messages"][-1].content).strip()

        if choice.lower() in _STOP_TOKENS:
            logger.info(f"✅ {router_agent.name} chose to finish ({choice!r}).")
            return {"next_agent": END, "step_count": 0, "agent_counts": {}}

        if choice not in agent_names or state.agent_counts.get(choice, 0) >= max_agent_turns:
            logger.warning(f"⚠️ {router_agent.name} picked invalid/exhausted agent {choice!r}, ending.")
            return {"next_agent": END, "step_count": 0, "agent_counts": {}}

        logger.info(f"🧭 {router_agent.name} -> {choice} (step {state.step_count + 1}/{max_steps})")
        return {
            "next_agent": choice,
            "step_count": state.step_count + 1,
            "agent_counts": {**state.agent_counts, choice: state.agent_counts.get(choice, 0) + 1},
        }

    graph = StateGraph(DynamicDaisyChainState)
    graph.add_node(router_agent.name, router_node)
    graph.add_edge(START, router_agent.name)
    for agent in agents:
        graph.add_node(agent.name, _wrap_agent_return_delta(agent))
        graph.add_edge(agent.name, router_agent.name)
    graph.add_conditional_edges(router_agent.name, lambda s: s.next_agent, [*agent_names, END])
    return graph.compile(name=name)
