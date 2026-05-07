"use client";

import { signInAnonymously, signInWithCustomToken } from "firebase/auth";
import { useTranslations } from "next-intl";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { firebaseAuth } from "@/lib/firebase";

/**
 * Two sign-in paths:
 *   1. Anonymous (dev / demo) — the existing button.
 *   2. ?token=<jwt> — the Zalo bot mints a one-time login link via
 *      `get_login_url`, brother taps it in chat. We POST the token to
 *      /public/auth/exchange, get back a Firebase custom token, sign
 *      in with it. URL param is dropped via router.replace once
 *      we've consumed it so it can't be re-used by browser history.
 */
export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginPageInner />
    </Suspense>
  );
}

function LoginPageInner() {
  const t = useTranslations();
  const router = useRouter();
  const searchParams = useSearchParams();
  const tokenParam = searchParams.get("token");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tokenConsumedRef = useRef(false);

  useEffect(() => {
    if (!tokenParam || tokenConsumedRef.current) return;
    tokenConsumedRef.current = true;
    void exchangeToken(tokenParam);
    // exchangeToken is stable — it captures router/setBusy/setError.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tokenParam]);

  async function exchangeToken(token: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/public/auth/exchange", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Exchange failed (${res.status})`);
      }
      const { custom_token } = (await res.json()) as { custom_token: string };
      await signInWithCustomToken(firebaseAuth(), custom_token);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

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

  const exchanging = busy && tokenParam;

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
            <p className="text-sm text-slate-500">
              {exchanging ? t("auth.signingIn") : t("auth.enterHint")}
            </p>
          </div>

          {!tokenParam && (
            <button
              onClick={enter}
              disabled={busy}
              className="w-full rounded-xl bg-brand-600 text-white py-3.5 font-medium shadow-lg shadow-brand-600/20 hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {busy ? t("common.loading") : t("auth.enter")}
            </button>
          )}

          {exchanging && (
            <div className="flex items-center justify-center gap-2 text-sm text-slate-500">
              <span className="size-2 rounded-full bg-brand-500 animate-pulse" />
              {t("common.loading")}
            </div>
          )}

          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </div>
        <p className="mt-6 text-center text-xs text-slate-400">
          {tokenParam ? "" : t("auth.devNotice")}
        </p>
      </div>
    </main>
  );
}
