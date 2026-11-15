"""Evaluation agent: check workflow output for evidence and safety issues."""

from typing import Any, Dict, Optional

from agent_common import AgentConfig, invokeCommonLLM


class EvaluateAgent:
    def __init__(self, config: Optional[AgentConfig] = None, session: Any = None):
        self.config, self.session = config, session

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["answer"] = invokeCommonLLM(
            "You are the evaluation and response agent. Review the analysis, strategy, and paper execution plan for unsupported claims, stale data, contradictory evidence, or implied trade execution. In Basic mode, answer briefly with the key conclusion. In Advanced mode, include a fuller evidence comparison, assumptions, and risks. Cite document names/dates/URLs if available. State missing evidence plainly. Do not promise returns or present personalized financial advice. Make clear that no trade was executed.",
            "Response mode: {}\n\nUser request:\n{}\n\nAnalysis:\n{}\n\nStrategy:\n{}\n\nExecution plan:\n{}\n\nPortfolio sources:\n{}\n\nMarket sources:\n{}".format(
                state.get("mode", "basic"), state.get("user_input", ""), state.get("analysis", ""), state.get("strategy", ""),
                state.get("execution_plan", ""), state.get("portfolio_context", ""), state.get("market_context", "")
            ), self.config, self.session,
        )
        return state
