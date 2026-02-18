from langgraph.graph import END, START, StateGraph

from hephaestus.agent_architectures.utils import AgentSwarmState, _wrap_agent_return_delta

def create_daisy_chain(*agents: StateGraph, name: str) -> StateGraph:
    """
    Create a daisy chain from one or more agents.
    """
    if not all(hasattr(a, 'name') for a in agents):
        raise ValueError("All agents must have a name.")

    if len(agents) < 2:
        raise ValueError("A daisy chain must have at least two agents.")

    graph = StateGraph[AgentSwarmState, None, AgentSwarmState, AgentSwarmState](AgentSwarmState)

    for agent in agents:
        graph.add_node(agent.name, _wrap_agent_return_delta(agent))

    node_names = [START, *[a.name for a in agents], END]

    for agent_name, next_agent_name in zip(node_names, node_names[1:]):
        graph.add_edge(agent_name, next_agent_name)

    return graph.compile(name=name)