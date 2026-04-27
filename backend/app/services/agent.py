"""Anthropic agent — the brain behind the Zalo bot.

Calls Claude Haiku 4.5 via the Messages API with the *native MCP connector*:
Claude reaches our deployed `/mcp/` endpoint server-side, calls our tools,
loops until done, and returns the final Vietnamese reply text.

This means we do NOT manage the tool loop client-side. We send the user's
message + history; Anthropic does the multi-step LLM↔MCP dance; we get back
one final text reply to pipe into Zalo.

The MCP connector is currently behind the `mcp-client-2025-04-04` beta header.
If/when it goes GA, drop the `betas=` argument.
"""

from __future__ import annotations

import logging
from pathlib import Path

from anthropic import AsyncAnthropic

from app.config import get_settings

log = logging.getLogger(__name__)

MCP_BETA = "mcp-client-2025-04-04"
# Co-located with this module so it ships in the Docker image (the
# Dockerfile only copies `app/`, not the repo's docs/ tree).
PROMPT_PATH = Path(__file__).parent / "AGENT_PROMPT.md"


def _load_system_prompt() -> str:
    """Read the Vietnamese system prompt from docs/AGENT_PROMPT.md.

    Stripped to the prompt body (between the first and last fenced block,
    if present) so the surrounding markdown commentary doesn't leak in."""
    raw = PROMPT_PATH.read_text(encoding="utf-8")
    if "```" in raw:
        parts = raw.split("```")
        # Body is between the first and second fence: parts[1] (skip leading
        # language tag if any).
        body = parts[1]
        if body.lstrip().startswith(("text\n", "markdown\n")):
            body = body.split("\n", 1)[1]
        return body.strip()
    return raw.strip()


_SYSTEM_PROMPT: str | None = None


def system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = _load_system_prompt()
    return _SYSTEM_PROMPT


_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY unset")
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def reply(
    user_text: str,
    history: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    """Run one Zalo turn through Claude + MCP.

    Returns `(final_text, assistant_content_blocks)`. Caller is expected to
    persist `user_text` as a user turn and `assistant_content_blocks` as
    the matching assistant turn so two-phase confirms (preview → "ok" →
    confirm) work across Zalo messages."""
    settings = get_settings()
    client = _get_client()

    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": user_text})

    resp = await client.beta.messages.create(
        model=settings.agent_model,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": system_prompt(),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
        mcp_servers=[
            {
                "type": "url",
                "url": settings.mcp_self_url,
                "name": "garage-ai",
                "authorization_token": settings.openclaw_api_key,
            }
        ],
        betas=[MCP_BETA],
    )

    text_parts: list[str] = []
    mcp_calls = 0
    content_blocks: list[dict] = []
    for block in resp.content:
        # Serialize to JSON-safe dict for Firestore + replay on next turn.
        block_dict = (
            block.model_dump(mode="json") if hasattr(block, "model_dump") else dict(block)
        )
        content_blocks.append(block_dict)
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(block.text)
        elif btype in ("mcp_tool_use", "tool_use"):
            mcp_calls += 1

    final_text = "\n\n".join(p.strip() for p in text_parts if p.strip())
    log.info(
        "agent: model=%s stop=%s mcp_calls=%d reply_chars=%d history=%d",
        settings.agent_model,
        getattr(resp, "stop_reason", "?"),
        mcp_calls,
        len(final_text),
        len(history or []),
    )

    if not final_text:
        # Defensive fallback — shouldn't happen, but the user must get *something*.
        final_text = "Xin lỗi, em đang gặp lỗi. Anh thử lại sau nhé."
    return final_text, content_blocks
