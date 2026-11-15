"""LangGraph orchestration for analysis, strategy, execution planning, and review."""

import os
from typing import Any, Dict, List, Optional, TypedDict

from agent_analyst import AnalysisAgent, retrieve_context
from agent_common import AgentConfig, set_shared_llm
from agent_execute import ExecuteAgent
from agent_evaluate import EvaluateAgent
from agent_strategy import StrategyAgent
TOP_K = 4

class WorkflowState(TypedDict, total=False):
    user_input: str
    mode: str
    chat_history: List[Dict[str, str]]
    portfolio_context: str
    market_context: str
    analysis: str
    strategy: str
    execution_plan: str
    answer: str


def build_workflow(config: Optional[AgentConfig] = None, session: Any = None):
    """Build a fresh graph; dependencies are injectable for local integrations."""
    from langgraph.graph import END, START, StateGraph

    agent_config = config or AgentConfig.from_environment()
    configured_base_url = agent_config.base_url.rstrip("/")
    if configured_base_url.endswith("/v1"):
        configured_base_url = configured_base_url[:-3]
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", configured_base_url)
    try:
        from langchain_ollama import ChatOllama
    except ImportError:
        # Keep Advanced mode usable before the optional LangChain Ollama
        # integration is installed; invokeCommonLLM then uses Ollama's
        # OpenAI-compatible HTTP endpoint from AgentConfig.
        set_shared_llm(None)
    else:
        set_shared_llm(ChatOllama(
            model=agent_config.model,
            base_url=ollama_base_url,
            temperature=0.2,
            num_predict=agent_config.max_tokens,
            client_kwargs={"timeout": agent_config.timeout_seconds},
        ))

    analyst = AnalysisAgent(agent_config, session)
    strategist = StrategyAgent(agent_config, session)
    executor = ExecuteAgent(agent_config, session)
    evaluator = EvaluateAgent(agent_config, session)

    def analyze_node(state: WorkflowState):
        context = retrieve_context(
            state["user_input"],
            limit=TOP_K if state.get("mode") == "advanced" else 3,
        )
        brief = analyst.run(
            state["user_input"], state.get("chat_history"),
            context.get("portfolio_context", ""), context.get("market_context", ""),
            mode=state.get("mode", "basic"),
        )
        return {**context, "analysis": brief}

    graph = StateGraph(WorkflowState)
    graph.add_node("analysis", analyze_node)
    graph.add_node("strategy", strategist.run)
    graph.add_node("execute", executor.run)
    graph.add_node("evaluate", evaluator.run)
    graph.add_edge(START, "analysis")
    graph.add_edge("analysis", "strategy")
    graph.add_edge("strategy", "execute")
    graph.add_edge("execute", "evaluate")
    graph.add_edge("evaluate", END)
    return graph.compile()


def run_workflow(user_input: str, chat_history: Optional[List[Dict[str, str]]] = None,
                 config: Optional[AgentConfig] = None, session: Any = None,
                 mode: str = "basic") -> str:
    if not isinstance(user_input, str) or not user_input.strip():
        raise ValueError("Enter a research question.")
    normalized_mode = mode.lower() if isinstance(mode, str) else ""
    if normalized_mode not in {"basic", "advanced"}:
        raise ValueError("Mode must be Basic or Advanced.")
    history = list(chat_history or [])[-8:]
    if normalized_mode == "basic":
        from agent_basic import run_basic_workflow
        return run_basic_workflow(user_input.strip(), chat_history=history)

    state = build_workflow(config, session).invoke({
        "user_input": user_input.strip(),
        "mode": normalized_mode,
        "chat_history": history,
    })
    return state["answer"]
