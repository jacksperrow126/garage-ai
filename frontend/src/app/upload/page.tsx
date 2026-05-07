"use client";

import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

const MAX_BYTES = 10 * 1024 * 1024;

/**
 * Public upload form reachable via /upload?token=<hmac>. The bot mints
 * the token + URL via the get_upload_url MCP tool when Zalo CDN blocks
 * server-side image fetches (the common case from Cloud Run egress).
 *
 * No auth on this page — possession of the URL is the proof. The
 * backend verifies the HMAC and binds the upload to the embedded
 * zalo_id.
 */
export default function UploadPage() {
  return (
    <Suspense fallback={null}>
      <UploadInner />
    </Suspense>
  );
}

function UploadInner() {
  const t = useTranslations("upload");
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [file, setFile] = useState<File | null>(null);
  const [caption, setCaption] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reply, setReply] = useState<string | null>(null);
  const [sentToZalo, setSentToZalo] = useState(false);

  if (!token) {
    return (
      <Shell>
        <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg p-3">
          {t("noToken")}
        </p>
      </Shell>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setError(t("fileTooLarge"));
      return;
    }
    setBusy(true);
    setError(null);
    setReply(null);

    const fd = new FormData();
    fd.append("file", file);
    fd.append("caption", caption);

    try {
      const res = await fetch(`/public/uploads/analyze?t=${encodeURIComponent(token!)}`, {
        method: "POST",
        body: fd,
      });
      if (!res.ok) {
        if (res.status === 403) throw new Error(t("linkExpired"));
        if (res.status === 413) throw new Error(t("fileTooLarge"));
        if (res.status === 415) throw new Error(t("unsupportedType"));
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `${res.status}`);
      }
      const json = (await res.json()) as { reply_text: string; sent_to_zalo: boolean };
      setReply(json.reply_text);
      setSentToZalo(json.sent_to_zalo);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell>
      <form onSubmit={submit} className="space-y-5">
        <div className="space-y-2">
          <label className="block text-sm font-medium text-slate-700">
            {t("fileLabel")}
          </label>
          <input
            type="file"
            accept="image/*,application/pdf,text/plain,text/csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-slate-700 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-brand-50 file:text-brand-700 hover:file:bg-brand-100"
          />
          <p className="text-xs text-slate-500">{t("fileHint")}</p>
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium text-slate-700">
            {t("captionLabel")}
          </label>
          <textarea
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
            placeholder={t("captionPlaceholder")}
            rows={3}
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>

        <button
          type="submit"
          disabled={busy || !file}
          className="w-full rounded-xl bg-brand-600 text-white py-3 font-medium shadow-md shadow-brand-600/20 hover:bg-brand-700 disabled:opacity-50 transition-colors"
        >
          {busy ? t("analyzing") : t("submit")}
        </button>

        {error && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg p-3">
            {error}
          </p>
        )}

        {reply && (
          <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 space-y-2">
            <div className="text-xs uppercase tracking-wide text-slate-500 font-medium">
              {t("resultTitle")}
            </div>
            <p className="text-sm text-slate-900 whitespace-pre-wrap">{reply}</p>
            {sentToZalo && (
              <p className="text-xs text-emerald-700">
                ✓ {t("alsoSentToZalo")}
              </p>
            )}
          </div>
        )}
      </form>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const t = useTranslations("upload");
  return (
    <main className="min-h-screen flex items-start justify-center p-4 sm:p-6">
      <div className="w-full max-w-md mt-8 sm:mt-16">
        <div className="rounded-3xl bg-white/80 backdrop-blur-xl border border-white shadow-[0_20px_60px_-15px_rgba(15,23,42,0.15)] p-6 sm:p-8 space-y-5">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 rounded-full bg-brand-50 text-brand-700 px-3 py-1 text-xs font-medium">
              <span className="size-1.5 rounded-full bg-brand-500" />
              {t("badge")}
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
              {t("title")}
            </h1>
            <p className="text-sm text-slate-500">{t("subtitle")}</p>
          </div>
          {children}
        </div>
      </div>
    </main>
  );
}
