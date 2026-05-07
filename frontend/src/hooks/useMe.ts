"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type AccessibleOrg = { id: string; name: string };

export type Me = {
  uid: string;
  email: string | null;
  role: string;
  actor: string;
  system_role: string | null;
  primary_org_id: string | null;
  accessible_orgs: AccessibleOrg[];
};

export function useMe() {
  return useQuery<Me>({
    queryKey: ["me"],
    queryFn: () => api.get("/me"),
    staleTime: 5 * 60_000,
  });
}
