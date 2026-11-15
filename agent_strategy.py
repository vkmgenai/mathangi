"""Investment strategy agent and compatibility entry point for the Flask app."""

from typing import Any, Dict, Optional

from agent_common import AgentConfig, AgentError, invokeCommonLLM

class StrategyAgent:
    def __init__(self, config: Optional[AgentConfig] = None, session: Any = None):
        self.config, self.session = config, session

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["strategy"] = invokeCommonLLM(
            "You are the strategy agent. Develop a cautious, evidence-based research view from the analysis brief. Match the requested response mode: Basic is concise; Advanced compares evidence and explains assumptions and risks in more depth. Do not claim certainty, invent current prices, or give personalized financial advice. If evidence is insufficient, say what is missing.",
            "Response mode: {}\n\nAnalysis brief:\n{}\n\nPortfolio documents:\n{}\n\nMarket documents:\n{}".format(
                state.get("mode", "basic"), state.get("analysis", ""), state.get("portfolio_context", ""), state.get("market_context", "")
            ), self.config, self.session,
        )
        return state
