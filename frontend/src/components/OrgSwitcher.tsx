"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { useMe, type AccessibleOrg } from "@/hooks/useMe";
import { getSelectedOrgId, setSelectedOrgId } from "@/lib/api";

/**
 * Renders the *active* garage in the Nav. Three modes:
 *   - 0 accessible orgs: nothing (the user can't do anything anyway).
 *   - 1 accessible org: static label so the user always knows which
 *     garage they're looking at.
 *   - 2+ accessible orgs: dropdown switcher. On change, updates
 *     localStorage and invalidates all queries so every page refetches
 *     against the newly selected org.
 *
 * On first mount we initialize localStorage to the user's primary_org_id
 * (or first accessible) if nothing's set yet, so the very first page
 * load after login already has X-Org-ID populated.
 */
export function OrgSwitcher() {
  const queryClient = useQueryClient();
  const me = useMe();
  const [open, setOpen] = useState(false);
  const [, forceRender] = useState(0);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Initialize the localStorage selection on first load + when /me arrives.
  // If the stored org isn't in accessible_orgs (e.g. admin lost access),
  // reset to primary_org_id.
  useEffect(() => {
    if (!me.data) return;
    const accessible = me.data.accessible_orgs;
    const current = getSelectedOrgId();
    const stillAccessible = accessible.some((o) => o.id === current);
    if (!current || !stillAccessible) {
      const fallback = me.data.primary_org_id ?? accessible[0]?.id ?? null;
      setSelectedOrgId(fallback);
      forceRender((n) => n + 1);
    }
  }, [me.data]);

  // Close dropdown on outside click.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  if (!me.data) return null;
  const accessible = me.data.accessible_orgs;
  if (accessible.length === 0) return null;

  const selectedId = getSelectedOrgId();
  const active =
    accessible.find((o) => o.id === selectedId) ?? accessible[0];
  const label = active?.name || active?.id || "—";

  // Single-org case: static label, no dropdown.
  if (accessible.length === 1) {
    return (
      <div
        className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-100/80 text-xs font-medium text-slate-700 max-w-[200px]"
        title={label}
      >
        <BuildingIcon />
        <span className="truncate">{label}</span>
      </div>
    );
  }

  // Multi-org admin: dropdown.
  return (
    <div ref={wrapperRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-100/80 hover:bg-slate-200 text-xs font-medium text-slate-700 max-w-[220px] transition-colors"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <BuildingIcon />
        <span className="truncate">{label}</span>
        <ChevronIcon />
      </button>
      {open && (
        <ul
          role="listbox"
          className="absolute top-full mt-1 right-0 min-w-[220px] max-h-[60vh] overflow-y-auto rounded-xl bg-white shadow-lg ring-1 ring-slate-900/5 py-1 z-20"
        >
          {accessible.map((org) => (
            <OrgOption
              key={org.id}
              org={org}
              isActive={org.id === active?.id}
              onPick={() => {
                setSelectedOrgId(org.id);
                setOpen(false);
                // Refetch every server-state query so all pages flip
                // to the new org's data without a full reload.
                queryClient.invalidateQueries();
                forceRender((n) => n + 1);
              }}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function OrgOption({
  org,
  isActive,
  onPick,
}: {
  org: AccessibleOrg;
  isActive: boolean;
  onPick: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        role="option"
        aria-selected={isActive}
        onClick={onPick}
        className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 ${
          isActive
            ? "bg-brand-50 text-brand-700 font-medium"
            : "text-slate-700 hover:bg-slate-50"
        }`}
      >
        <span className="size-1.5 rounded-full bg-brand-500" style={{ opacity: isActive ? 1 : 0 }} />
        <span className="truncate">{org.name || org.id}</span>
      </button>
    </li>
  );
}

function BuildingIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="size-3.5 shrink-0"
      aria-hidden="true"
    >
      <path d="M3 21h18M5 21V7l7-4 7 4v14M9 9h.01M9 13h.01M9 17h.01M14 9h.01M14 13h.01M14 17h.01" />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      className="size-3 shrink-0"
      aria-hidden="true"
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}
