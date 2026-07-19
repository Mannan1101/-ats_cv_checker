"""Wires the OpenAI Agents SDK to OpenRouter's OpenAI-compatible API.

OpenRouter only implements the Chat Completions API (not OpenAI's newer
Responses API), so every `Agent` in this project is built with an explicit
`OpenAIChatCompletionsModel` pointed at an `AsyncOpenAI` client whose
`base_url` is OpenRouter. Tracing is disabled by default because the Agents
SDK tracing exporter talks to OpenAI's own backend, which requires a real
OpenAI API key we don't have.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import TypeVar

from agents import (
    Agent,
    InputGuardrailTripwireTriggered,
    ModelSettings,
    OpenAIChatCompletionsModel,
    Runner,
    set_tracing_disabled,
)
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

load_dotenv()

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client: AsyncOpenAI | None = None
_configured = False


def configure_agents_sdk() -> None:
    """Idempotently disable tracing (see module docstring)."""
    global _configured
    if _configured:
        return
    if os.getenv("DISABLE_TRACING", "true").lower() in ("1", "true", "yes"):
        set_tracing_disabled(True)
    _configured = True


def get_openrouter_client() -> AsyncOpenAI:
    """Return a process-wide `AsyncOpenAI` client pointed at OpenRouter."""
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    _client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers={
            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost"),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "ATS-CV-Agent"),
        },
    )
    return _client


def get_model(model_name: str | None = None) -> OpenAIChatCompletionsModel:
    """Build the shared chat-completions model every agent is created with."""
    configure_agents_sdk()
    name = model_name or os.getenv(
        "OPENROUTER_MODEL_NAME", "nousresearch/hermes-3-llama-3.1-405b:free"
    )
    return OpenAIChatCompletionsModel(model=name, openai_client=get_openrouter_client())


def default_model_settings() -> ModelSettings:
    """Conservative defaults tuned for a free, less-deterministic model.

    `max_tokens` is set generously: the improvement/report agents return
    fairly large nested JSON objects, and free-tier models silently
    truncate mid-JSON at their provider's default output limit otherwise,
    which then surfaces as a confusing JSON-parse error rather than a
    length error.
    """
    return ModelSettings(temperature=0.3, max_tokens=4096)


_FENCE_START_RE = re.compile(r"^\s*```[a-zA-Z0-9]*\s*\n?")
_FENCE_END_RE = re.compile(r"\n?\s*```\s*$")
_JSON_OBJECT_RE = re.compile(r"(\{.*\}|\[.*\])", re.DOTALL)


def json_schema_instructions(model: type[BaseModel]) -> str:
    """Human-readable schema block appended to an agent's instructions.

    Free OpenRouter models don't reliably honor the OpenAI `response_format`
    structured-output contract, so instead of depending on it we spell the
    exact JSON shape out in plain instructions and parse the reply ourselves
    (see `run_structured`).
    """
    schema = json.dumps(model.model_json_schema(), indent=2)
    return (
        "\n\nYou MUST respond with ONLY a single valid JSON object matching "
        "this JSON Schema -- no markdown code fences, no commentary before "
        f"or after it:\n\n{schema}"
    )


def _extract_json_text(raw: str) -> str:
    text = raw.strip()
    text = _FENCE_START_RE.sub("", text)
    text = _FENCE_END_RE.sub("", text)
    text = text.strip()
    if not (text.startswith("{") or text.startswith("[")):
        match = _JSON_OBJECT_RE.search(text)
        if match:
            text = match.group(1)
    return text


async def run_structured(
    agent: Agent,
    input_text: str,
    output_type: type[T],
    *,
    max_attempts: int = 3,
    network_retry_delay: float = 2.0,
) -> T:
    """Run a (plain-text) agent and parse+validate its JSON reply ourselves.

    More resilient than the Agents SDK's built-in `output_type` validation,
    which raises immediately on markdown-fenced or slightly malformed JSON.
    On a parse/validation failure, feeds the error back to the model and
    asks it to correct itself. Transient network/API hiccups (common on
    OpenRouter's free tier: dropped connections, truncated response bodies)
    are retried from scratch with a short backoff instead of being treated
    as a schema problem. Up to `max_attempts` total tries either way.
    """
    conversation: str | list = input_text
    last_error = "unknown error"

    for attempt in range(1, max_attempts + 1):
        try:
            result = await Runner.run(agent, input=conversation)
        except InputGuardrailTripwireTriggered:
            raise
        except Exception as exc:  # noqa: BLE001 - network/provider flakiness, not our bug
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Model call failed (attempt %d/%d) for %s: %s",
                attempt, max_attempts, agent.name, last_error,
            )
            if attempt == max_attempts:
                break
            await asyncio.sleep(network_retry_delay * attempt)
            continue

        raw = result.final_output if isinstance(result.final_output, str) else str(result.final_output)
        candidate = _extract_json_text(raw)
        try:
            data = json.loads(candidate)
            return output_type.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)
            logger.warning(
                "Structured output parse failed (attempt %d/%d) for %s: %s",
                attempt, max_attempts, agent.name, last_error,
            )
            if attempt == max_attempts:
                break
            history = result.to_input_list()
            history.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous response was not valid JSON matching the required "
                        f"schema. Error: {last_error}\n"
                        "Reply with ONLY the corrected JSON object. No markdown code "
                        "fences, no commentary."
                    ),
                }
            )
            conversation = history

    raise RuntimeError(
        f"{agent.name} failed to produce valid structured output after "
        f"{max_attempts} attempts: {last_error}"
    )
