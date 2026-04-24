"use client";

import { GoogleAuthProvider, signInWithPopup } from "firebase/auth";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { firebaseAuth } from "@/lib/firebase";

export default function LoginPage() {
  const t = useTranslations();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signIn() {
    setBusy(true);
    setError(null);
    try {
      await signInWithPopup(firebaseAuth(), new GoogleAuthProvider());
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-sm rounded-2xl bg-white shadow-sm p-8 space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">{t("app.title")}</h1>
          <p className="text-slate-500 text-sm">{t("app.tagline")}</p>
        </div>
        <button
          onClick={signIn}
          disabled={busy}
          className="w-full rounded-lg bg-slate-900 text-white py-3 font-medium hover:bg-slate-800 disabled:opacity-50"
        >
          {busy ? t("common.loading") : t("auth.signInWithGoogle")}
        </button>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>
    </main>
  );
}
