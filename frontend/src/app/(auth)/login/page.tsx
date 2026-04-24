"use client";

import { signInAnonymously } from "firebase/auth";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { firebaseAuth } from "@/lib/firebase";

/**
 * Google sign-in is disabled for now — we sign in anonymously against the
 * Auth emulator / real Identity Platform. The backend still verifies a
 * Firebase ID token, so the auth pipeline is fully exercised; re-enable
 * Google by swapping signInAnonymously() for signInWithPopup(..., new
 * GoogleAuthProvider()) and restoring the GoogleAuthProvider import.
 */
export default function LoginPage() {
  const t = useTranslations();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function enter() {
    setBusy(true);
    setError(null);
    try {
      await signInAnonymously(firebaseAuth());
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="relative rounded-3xl bg-white/80 backdrop-blur-xl border border-white shadow-[0_20px_60px_-15px_rgba(15,23,42,0.15)] p-10 space-y-8">
          <div className="absolute -top-px left-12 right-12 h-px bg-gradient-to-r from-transparent via-brand-400/60 to-transparent" />
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 rounded-full bg-brand-50 text-brand-700 px-3 py-1 text-xs font-medium">
              <span className="size-1.5 rounded-full bg-brand-500" />
              {t("app.tagline")}
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900">
              {t("app.title")}
            </h1>
            <p className="text-sm text-slate-500">{t("auth.enterHint")}</p>
          </div>

          <button
            onClick={enter}
            disabled={busy}
            className="w-full rounded-xl bg-brand-600 text-white py-3.5 font-medium shadow-lg shadow-brand-600/20 hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {busy ? t("common.loading") : t("auth.enter")}
          </button>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </div>
        <p className="mt-6 text-center text-xs text-slate-400">
          {t("auth.devNotice")}
        </p>
      </div>
    </main>
  );
}
