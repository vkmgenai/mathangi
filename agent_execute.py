"""Execution agent: translate a strategy into a paper plan, without trading."""

from typing import Any, Dict, Optional

from agent_common import AgentConfig, invokeCommonLLM


class ExecuteAgent:
    def __init__(self, config: Optional[AgentConfig] = None, session: Any = None):
        self.config, self.session = config, session

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["execution_plan"] = invokeCommonLLM(
            "You are the execution planning agent. Produce only a hypothetical, non-binding execution checklist based on the user's request and strategy. Match the requested response mode: Basic is concise; Advanced includes relevant review steps and assumptions. Never place orders, call trading APIs, invent prices, or imply an order was executed. If the user did not request execution planning, explicitly say no execution plan is needed. Require human review for any real transaction.",
            "Response mode: {}\n\nUser request:\n{}\n\nStrategy view:\n{}\n\nPortfolio snapshot:\n{}".format(
                state.get("mode", "basic"), state.get("user_input", ""), state.get("strategy", ""), state.get("portfolio_context", "")
            ), self.config, self.session,
        )
        return state
