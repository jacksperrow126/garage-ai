"""Onboarding state machine for newly approved Zalo users.

A user moves through these steps after `approve_access_request` succeeds:

  garage_profile → first_inventory → done

Each step is stored as `onboarding_step` on the `zalo_users/{zalo_id}`
doc. The agent's session-context prompt branches on this value to drive
the dialog. State transitions are explicit — the bot calls
`set_onboarding_step` MCP tool when it decides the current step is
complete.

Skip rules:
  - Only approval with role="owner" into a *fresh* org triggers onboarding.
    A "fresh" org has no profile data set (no address/phone/tax_id) AND
    is the user's first owner.
  - Subsequent owners/managers added to an already-set-up org skip
    straight to "done" — the org is in use, no setup needed.
"""

from __future__ import annotations

from typing import Final

from app.services import orgs as orgs_service

STEP_GARAGE_PROFILE: Final = "garage_profile"
STEP_FIRST_INVENTORY: Final = "first_inventory"
STEP_DONE: Final = "done"

# Order matters: each entry's successor is the next valid step.
_STEP_ORDER: Final = (STEP_GARAGE_PROFILE, STEP_FIRST_INVENTORY, STEP_DONE)


def is_valid_step(step: str | None) -> bool:
    return step is None or step in _STEP_ORDER


def is_org_already_setup(org_id: str) -> bool:
    """Heuristic: an org is "set up" if it has any printable header field.
    Used to decide whether an approval should trigger onboarding or skip
    straight to 'done' (the second user joining an already-active org)."""
    org = orgs_service.get_org(org_id)
    if not org:
        return False
    return bool(org.get("address") or org.get("phone") or org.get("tax_id"))
