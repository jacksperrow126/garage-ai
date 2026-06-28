"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

type OrgInfo = {
  id: string;
  name: string;
  address: string;
  phone: string;
  tax_id: string;
  bank_name: string;
  bank_account: string;
  bank_holder: string;
  services: string[];
  logo: string;
};

// Resize a picked image to <= maxDim on its longest side and return a PNG
// data-URI. Keeps the logo well under Firestore's 1 MB doc limit and avoids
// shipping a multi-MB camera photo.
function fileToResizedDataUrl(file: File, maxDim = 400): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
      const w = Math.max(1, Math.round(img.width * scale));
      const h = Math.max(1, Math.round(img.height * scale));
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) return reject(new Error("no canvas context"));
      ctx.drawImage(img, 0, 0, w, h);
      resolve(canvas.toDataURL("image/png"));
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("invalid image"));
    };
    img.src = url;
  });
}

export default function SettingsPage() {
  const t = useTranslations("settings");
  const tc = useTranslations("common");
  const qc = useQueryClient();

  const org = useQuery<OrgInfo>({
    queryKey: ["org", "current"],
    queryFn: () => api.get("/orgs/current"),
  });

  const [form, setForm] = useState<OrgInfo | null>(null);
  const [servicesText, setServicesText] = useState("");
  const [logoError, setLogoError] = useState<string | null>(null);

  // Hydrate the editable form once the org loads.
  useEffect(() => {
    if (org.data && !form) {
      setForm(org.data);
      setServicesText((org.data.services || []).join("\n"));
    }
  }, [org.data, form]);

  const save = useMutation<OrgInfo>({
    mutationFn: () =>
      api.patch<OrgInfo>("/orgs/current", {
        address: form?.address ?? "",
        phone: form?.phone ?? "",
        tax_id: form?.tax_id ?? "",
        bank_name: form?.bank_name ?? "",
        bank_account: form?.bank_account ?? "",
        bank_holder: form?.bank_holder ?? "",
        services: servicesText
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean)
          .slice(0, 12),
        logo: form?.logo ?? "",
      }),
    onSuccess: (updated) => {
      qc.setQueryData(["org", "current"], updated);
      setForm(updated);
    },
  });

  if (org.isLoading || !form) return <div className="text-slate-500">{tc("loading")}…</div>;

  function set(patch: Partial<OrgInfo>) {
    setForm((f) => (f ? { ...f, ...patch } : f));
  }

  async function onLogoPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-picking the same file
    if (!file) return;
    setLogoError(null);
    try {
      const dataUrl = await fileToResizedDataUrl(file);
      set({ logo: dataUrl });
    } catch {
      setLogoError(t("logoError"));
    }
  }

  return (
    <div className="space-y-4 max-w-2xl">
      <h1 className="text-xl font-semibold">{t("title")}</h1>
      <p className="text-sm text-slate-500">{t("subtitle")}</p>

      <div className="rounded-xl bg-white p-4 shadow-sm space-y-4">
        <h2 className="text-sm font-medium text-slate-700">{t("headerSection")}</h2>

        {/* Logo */}
        <div className="flex items-center gap-4">
          <div className="grid size-20 shrink-0 place-items-center overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
            {form.logo ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={form.logo} alt="logo" className="max-h-full max-w-full object-contain" />
            ) : (
              <span className="text-xs text-slate-400">{t("noLogo")}</span>
            )}
          </div>
          <div className="space-y-1">
            <label className="inline-block cursor-pointer rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
              {t("uploadLogo")}
              <input type="file" accept="image/*" onChange={onLogoPick} className="hidden" />
            </label>
            {form.logo && (
              <button
                type="button"
                onClick={() => set({ logo: "" })}
                className="ml-2 cursor-pointer text-sm text-slate-400 hover:text-red-600"
              >
                {t("removeLogo")}
              </button>
            )}
            <div className="text-xs text-slate-400">{t("logoHint")}</div>
            {logoError && <div className="text-xs text-red-600">{logoError}</div>}
          </div>
        </div>

        <Field label={t("orgName")}>
          <input
            value={form.name}
            disabled
            className="w-full rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-slate-500"
          />
        </Field>
        <Field label={t("taxId")}>
          <input
            value={form.tax_id}
            onChange={(e) => set({ tax_id: e.target.value })}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </Field>
        <Field label={t("address")}>
          <input
            value={form.address}
            onChange={(e) => set({ address: e.target.value })}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </Field>
        <Field label={t("phone")}>
          <input
            value={form.phone}
            onChange={(e) => set({ phone: e.target.value })}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </Field>
      </div>

      <div className="rounded-xl bg-white p-4 shadow-sm space-y-4">
        <h2 className="text-sm font-medium text-slate-700">{t("bankSection")}</h2>
        <Field label={t("bankName")}>
          <input
            value={form.bank_name}
            onChange={(e) => set({ bank_name: e.target.value })}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </Field>
        <Field label={t("bankAccount")}>
          <input
            value={form.bank_account}
            onChange={(e) => set({ bank_account: e.target.value })}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </Field>
        <Field label={t("bankHolder")}>
          <input
            value={form.bank_holder}
            onChange={(e) => set({ bank_holder: e.target.value })}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </Field>
      </div>

      <div className="rounded-xl bg-white p-4 shadow-sm space-y-2">
        <h2 className="text-sm font-medium text-slate-700">{t("servicesSection")}</h2>
        <p className="text-xs text-slate-400">{t("servicesHint")}</p>
        <textarea
          value={servicesText}
          onChange={(e) => setServicesText(e.target.value)}
          rows={6}
          placeholder={t("servicesPlaceholder")}
          className="w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm"
        />
      </div>

      {save.isError && <div className="text-sm text-red-600">{String(save.error)}</div>}
      {save.isSuccess && !save.isPending && (
        <div className="text-sm text-green-600">{t("saved")}</div>
      )}

      <div className="flex justify-end">
        <button
          type="button"
          disabled={save.isPending}
          onClick={() => save.mutate()}
          className="cursor-pointer rounded-md bg-slate-900 px-6 py-2 text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {save.isPending ? tc("loading") : t("save")}
        </button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      {children}
    </label>
  );
}
