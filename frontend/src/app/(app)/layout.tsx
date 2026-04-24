"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Nav } from "@/components/Nav";
import { useAuth } from "@/hooks/useAuth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center text-sm text-slate-400">
        <div className="flex items-center gap-2">
          <span className="size-2 rounded-full bg-brand-500 animate-pulse" />
          Loading…
        </div>
      </div>
    );
  }
  if (!user) return null;

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-6xl p-4 sm:p-6 lg:p-8">{children}</main>
    </>
  );
}
