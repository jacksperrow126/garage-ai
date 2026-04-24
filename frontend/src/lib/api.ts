/**
 * Thin fetch wrapper for the admin panel.
 *
 * TEMPORARY (local dev): we send `X-API-Key` taken from NEXT_PUBLIC_API_KEY
 * so the browser can talk to the backend without Firebase Auth. In
 * production this will switch to Firebase ID tokens via
 * `Authorization: Bearer <token>`. See docs/RESUME.md for the re-enable
 * plan.
 *
 * On App Hosting, `/api/**` is same-origin via the Next.js rewrite in
 * `next.config.ts`, so no CORS setup is needed.
 */

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

function devHeaders(): HeadersInit {
  const key = process.env.NEXT_PUBLIC_API_KEY;
  return key ? { "X-API-Key": key } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...devHeaders(),
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

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
