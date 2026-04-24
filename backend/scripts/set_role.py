"""Admin script: set Firebase Auth custom claims (role) on a user.

Usage:
    python scripts/set_role.py --email you@example.com --role owner
    python scripts/set_role.py --email mech@example.com --role manager

Requires GOOGLE_APPLICATION_CREDENTIALS to point at a service account JSON
with Firebase Auth admin permissions on the target project.
"""

from __future__ import annotations

import argparse
import sys

import firebase_admin
from firebase_admin import auth, credentials


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", required=True, choices=["owner", "manager"])
    parser.add_argument("--project")
    args = parser.parse_args()

    opts = {"projectId": args.project} if args.project else None
    firebase_admin.initialize_app(credentials.ApplicationDefault(), opts)

    try:
        user = auth.get_user_by_email(args.email)
    except auth.UserNotFoundError:
        print(f"no user with email {args.email}", file=sys.stderr)
        return 1

    existing = user.custom_claims or {}
    auth.set_custom_user_claims(user.uid, {**existing, "role": args.role})
    print(f"ok: {args.email} → role={args.role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
