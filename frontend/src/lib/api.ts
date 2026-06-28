import { firebaseAuth } from "./firebase";

/**
 * Thin fetch wrapper that attaches the current user's Firebase ID token
 * AND the X-Org-ID header for the org the user is currently viewing.
 * All API routes in the FastAPI backend accept `Authorization: Bearer <token>`
 * and gate access via `require_org_id` (auth.py).
 *
 * On App Hosting, `/api/**` is same-origin via the Next.js rewrite in
 * `next.config.ts`, so no CORS setup is needed in the browser.
 */

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

const ORG_ID_KEY = "garage-ai:selected-org-id";

export function getSelectedOrgId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ORG_ID_KEY);
}

export function setSelectedOrgId(orgId: string | null): void {
  if (typeof window === "undefined") return;
  if (orgId) localStorage.setItem(ORG_ID_KEY, orgId);
  else localStorage.removeItem(ORG_ID_KEY);
}

async function authHeaders(): Promise<HeadersInit> {
  const headers: Record<string, string> = {};
  const user = firebaseAuth().currentUser;
  if (user) {
    const token = await user.getIdToken();
    headers["Authorization"] = `Bearer ${token}`;
  }
  const orgId = getSelectedOrgId();
  if (orgId) headers["X-Org-ID"] = orgId;
  return headers;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...(await authHeaders()),
    ...(init.headers ?? {}),
  };
  const res = await fetch(`/api/v1${path}`, { ...init, headers });
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    throw new ApiError(res.status, `API ${res.status}`, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function requestBlob(
  path: string,
  init: RequestInit = {},
): Promise<{ blob: Blob; filename: string | null }> {
  const headers = {
    ...(init.body ? { "Content-Type": "application/json" } : {}),
    ...(await authHeaders()),
    ...(init.headers ?? {}),
  };
  const res = await fetch(`/api/v1${path}`, { ...init, headers });
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    throw new ApiError(res.status, `API ${res.status}`, body);
  }
  // Pull suggested filename out of Content-Disposition if the server set one.
  const cd = res.headers.get("Content-Disposition") || "";
  const match = cd.match(/filename="?([^";]+)"?/i);
  return { blob: await res.blob(), filename: match ? match[1] : null };
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  getBlob: (path: string) => requestBlob(path),
  postBlob: (path: string, body: unknown) =>
    requestBlob(path, { method: "POST", body: JSON.stringify(body) }),
};
