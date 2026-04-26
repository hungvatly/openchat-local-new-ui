"""
utils/llm_bridge.py — Engine-agnostic LLM completion helper for template-fill.

The template-fill pipeline needs a simple synchronous-style call:
    text = await template_llm_complete(system_prompt, user_prompt, model)

This module wraps the app's existing local_llm.stream_chat() — which already
routes to Ollama, GGUF (llama.cpp), or HuggingFace Transformers depending on
what the user currently has loaded. No engine is hard-coded here.
"""
from __future__ import annotations

import json
import re
from typing import Dict, Optional


async def template_llm_complete(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_retries: int = 2,
) -> str:
    """
    Send a prompt to whatever LLM engine is currently loaded in the app.
    Returns the raw completion string.

    Uses local_llm.stream_chat() — the app's single unified inference path.
    This means the template-fill feature automatically works with:
      - Ollama models  (detected by model name containing ":" or matching Ollama list)
      - GGUF models    (llama.cpp via llama-cpp-python)
      - HuggingFace    (SafeTensors via transformers)

    If the caller needs to switch model, pass model= explicitly; otherwise the
    currently loaded model is used.
    """
    from utils.local_llm import local_llm  # singleton, already handles all backends

    tokens = []
    async for token in local_llm.stream_chat(
        message=user_prompt,
        model=model,
        context="",
        history=[],
        images=None,
        system_prompt=system_prompt,
    ):
        tokens.append(token)
    return "".join(tokens)


async def extract_json_from_llm(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
) -> Dict:
    """
    Call the LLM and attempt to parse JSON from the response.
    Retries up to 2 times if parsing fails, appending a corrective instruction.
    Returns a dict (possibly empty {}) — never raises.
    """
    MAX_RETRIES = 2
    current_user_prompt = user_prompt

    for attempt in range(MAX_RETRIES + 1):
        raw = await template_llm_complete(system_prompt, current_user_prompt, model)
        parsed = _try_parse_json(raw)
        if parsed is not None:
            return parsed

        # Retry with correction appended
        current_user_prompt = (
            user_prompt
            + "\n\nIMPORTANT: Your previous response could not be parsed as JSON. "
            "You MUST respond with ONLY a valid JSON object. "
            "No markdown fences, no explanation, no extra text before or after the JSON."
        )

    # All retries exhausted — return empty dict so pipeline degrades gracefully
    return {}


def _try_parse_json(text: str) -> Optional[Dict]:
    """
    Try to extract and parse a JSON object from LLM output.
    Handles markdown fences, leading/trailing prose, etc.
    """
    if not text or not text.strip():
        return None

    # Strip markdown code fences  ```json ... ``` or ``` ... ```
    stripped = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()

    # Try direct parse first
    try:
        result = json.loads(stripped)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # Try to extract the first { ... } block
    match = re.search(r"\{[\s\S]*\}", stripped)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    return None
