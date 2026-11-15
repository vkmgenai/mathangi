"""Shared model configuration and completion helper for the workflow agents."""

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

MODEL_NAME = "phi4-mini:latest"
MODEL_BASE_URL = "http://localhost:11434/v1"
_SHARED_LLM = None


class AgentError(RuntimeError):
    """Raised when an agent cannot get a usable completion."""


def set_shared_llm(llm: Any) -> None:
    """Set the workflow's shared LangChain chat model instance."""
    global _SHARED_LLM
    _SHARED_LLM = llm


@dataclass(frozen=True)
class AgentConfig:
    base_url: str = MODEL_BASE_URL
    model: str = MODEL_NAME
    api_key: Optional[str] = None
    timeout_seconds: int = 600
    max_tokens: int = 900

    @classmethod
    def from_environment(cls) -> "AgentConfig":
        return cls(
            base_url=os.getenv("STRATEGY_LLM_BASE_URL", MODEL_BASE_URL),
            model=os.getenv("STRATEGY_LLM_MODEL", MODEL_NAME),
            api_key=os.getenv("STRATEGY_LLM_API_KEY"),
            timeout_seconds=int(os.getenv("STRATEGY_LLM_TIMEOUT", "600")),
            max_tokens=int(os.getenv("STRATEGY_LLM_MAX_TOKENS", "900")),
        )


def invokeCommonLLM(system_prompt: str, user_prompt: str, config: Optional[AgentConfig] = None,
                    session: Any = None) -> str:
    config = config or AgentConfig.from_environment()
    if _SHARED_LLM is not None and session is None:
        from langchain_core.messages import HumanMessage, SystemMessage
        try:
            result = _SHARED_LLM.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            answer = result.content
        except Exception as error:
            raise AgentError("The configured Ollama model could not complete the request: {}".format(error)) from error
        if isinstance(answer, list):
            answer = "\n".join(
                part.get("text", "") for part in answer if isinstance(part, dict)
            )
        if not isinstance(answer, str) or not answer.strip():
            raise AgentError("The Ollama model returned an empty answer.")
        return answer.strip()

    client = session or requests
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = "Bearer " + config.api_key
    if "openrouter.ai" in config.base_url:
        headers["HTTP-Referer"] = os.getenv("OPENROUTER_SITE_URL", "http://localhost")
        headers["X-Title"] = os.getenv("OPENROUTER_APP_NAME", "AEGIS Investment Research")
    try:
        response = client.post(
            config.base_url.rstrip("/") + "/chat/completions",
            headers=headers,
            json={
                "model": config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": config.max_tokens,
            },
            timeout=config.timeout_seconds,
        )
    except requests.Timeout as error:
        raise AgentError(
            "The model did not respond within {} seconds. Increase STRATEGY_LLM_TIMEOUT or lower STRATEGY_LLM_MAX_TOKENS.".format(config.timeout_seconds)
        ) from error
    except requests.ConnectionError as error:
        raise AgentError("Could not connect to the model endpoint at {}.".format(config.base_url)) from error
    except requests.RequestException as error:
        raise AgentError("The model HTTP request failed: {}.".format(error)) from error
    if response.status_code >= 400:
        raise AgentError("The model endpoint returned HTTP {}.".format(response.status_code))
    try:
        payload = response.json()
        answer = payload["choices"][0]["message"].get("content")
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise AgentError("The model endpoint returned no usable answer.") from error
    if not isinstance(answer, str) or not answer.strip():
        raise AgentError("The model returned an empty answer.")
    return answer.strip()
