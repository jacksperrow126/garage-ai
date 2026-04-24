import { Nav } from "@/components/Nav";

/**
 * TEMPORARY: auth is dropped for local dev. All routes are open; the
 * frontend authenticates to the backend via `X-API-Key` in src/lib/api.ts.
 * Re-enable Firebase Auth per docs/RESUME.md before any deploy.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Nav />
      <main className="mx-auto max-w-6xl p-4 sm:p-6">{children}</main>
    </>
  );
}
