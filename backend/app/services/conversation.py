"""Per-user conversation persistence for the Zalo bot.

Stored at:
  conversations/{zalo_user_id}/messages/{auto_id}
    role: "user" | "assistant"
    content: str (for user) | list[dict] (for assistant — content blocks)
    created_at: server_timestamp

Why blocks instead of plain text on assistant turns: Claude's MCP connector
emits `mcp_tool_use` and `mcp_tool_result` blocks alongside the visible text.
For two-phase confirms (preview → user "ok" → confirm) to work across Zalo
messages, the next turn must show Claude its prior tool_use blocks (which
carry the `preview_id`) — so we round-trip the full block list, not just text.

`HISTORY_LIMIT` caps cost: every turn re-sends prior turns to Anthropic, so
unbounded history = unbounded token spend. 20 messages ≈ 10 user/assistant
exchanges, plenty for a chat-style ops session.
"""

from __future__ import annotations

import logging
from typing import Any

from google.cloud import firestore

from app.firestore import get_db, server_timestamp

log = logging.getLogger(__name__)

HISTORY_LIMIT = 20


def load(user_id: str, limit: int = HISTORY_LIMIT) -> list[dict[str, Any]]:
    """Return last `limit` messages, oldest-first, in Anthropic message format.

    Anthropic requires the first message to have role=user; if our slice
    happens to start with an assistant turn (we cut mid-exchange), drop
    leading assistant messages until we find a user one."""
    col = (
        get_db()
        .collection("conversations")
        .document(user_id)
        .collection("messages")
    )
    snaps = list(
        col.order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    snaps.reverse()  # chronological

    msgs: list[dict[str, Any]] = []
    for snap in snaps:
        data = snap.to_dict() or {}
        role = data.get("role")
        content = data.get("content")
        if role not in ("user", "assistant") or content is None:
            continue
        msgs.append({"role": role, "content": content})

    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def append_turn(
    user_id: str,
    user_text: str,
    assistant_content: list[dict[str, Any]],
) -> None:
    """Append one (user → assistant) exchange to the conversation log."""
    col = (
        get_db()
        .collection("conversations")
        .document(user_id)
        .collection("messages")
    )
    col.add(
        {"role": "user", "content": user_text, "created_at": server_timestamp()}
    )
    col.add(
        {
            "role": "assistant",
            "content": assistant_content,
            "created_at": server_timestamp(),
        }
    )
