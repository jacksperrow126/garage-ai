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
    return <div className="p-8 text-slate-500">Loading...</div>;
  }
  if (!user) return null;

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-6xl p-4 sm:p-6">{children}</main>
    </>
  );
}
