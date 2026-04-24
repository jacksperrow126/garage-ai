"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { api } from "@/lib/api";
import { formatVnd, parseVnd } from "@/lib/format";

type Product = {
  id: string;
  name: string;
  sku: string;
  quantity: number;
  selling_price: number;
  average_cost: number;
};

export default function InventoryPage() {
  const t = useTranslations("inventory");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [addOpen, setAddOpen] = useState(false);

  const products = useQuery<Product[]>({
    queryKey: ["products", { search, lowOnly }],
    queryFn: () => {
      const params = new URLSearchParams();
      if (search) params.set("query", search);
      if (lowOnly) params.set("low_stock_only", "true");
      const qs = params.toString();
      return api.get(`/products${qs ? `?${qs}` : ""}`);
    },
  });

  const create = useMutation({
    mutationFn: (body: { name: string; selling_price: number }) =>
      api.post<Product>("/products", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["products"] });
      setAddOpen(false);
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="flex-1 text-2xl font-semibold tracking-tight text-slate-900">
          {t("title")}
        </h1>
        <button
          className="rounded-xl bg-brand-600 text-white px-4 py-2 text-sm font-medium shadow-sm shadow-brand-600/20 hover:bg-brand-700 transition-colors"
          onClick={() => setAddOpen(true)}
        >
          {t("addProduct")}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <input
          placeholder={t("searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[220px] rounded-xl bg-white ring-1 ring-slate-200 px-4 py-2.5 text-sm placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500 focus:outline-none transition-shadow"
        />
        <label className="flex items-center gap-2 text-sm text-slate-600 select-none cursor-pointer">
          <input
            type="checkbox"
            checked={lowOnly}
            onChange={(e) => setLowOnly(e.target.checked)}
            className="size-4 rounded accent-brand-600"
          />
          {t("lowStockOnly")}
        </label>
      </div>

      <div className="rounded-2xl bg-white ring-1 ring-slate-200/60 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400 bg-slate-50/60">
            <tr>
              <th className="px-4 py-3">{t("sku")}</th>
              <th className="px-4 py-3">{t("name")}</th>
              <th className="px-4 py-3 text-right">{t("quantity")}</th>
              <th className="px-4 py-3 text-right">{t("avgCost")}</th>
              <th className="px-4 py-3 text-right">{t("sellingPrice")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {products.data?.map((p) => (
              <tr key={p.id} className="hover:bg-slate-50/70 transition-colors">
                <td className="px-4 py-3 font-mono text-slate-500">{p.sku}</td>
                <td className="px-4 py-3 text-slate-800">{p.name}</td>
                <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700">
                  {p.quantity}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-600">
                  {formatVnd(p.average_cost)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums font-medium text-slate-900">
                  {formatVnd(p.selling_price)}
                </td>
              </tr>
            ))}
            {products.data?.length === 0 && (
              <tr>
                <td colSpan={5} className="p-8 text-center text-slate-400">
                  —
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {addOpen && (
        <AddProductModal
          onCancel={() => setAddOpen(false)}
          onSubmit={(payload) => create.mutate(payload)}
          busy={create.isPending}
          labels={{
            name: t("name"),
            price: t("sellingPrice"),
            save: tc("save"),
            cancel: tc("cancel"),
          }}
        />
      )}
    </div>
  );
}

function AddProductModal({
  onCancel,
  onSubmit,
  busy,
  labels,
}: {
  onCancel: () => void;
  onSubmit: (body: { name: string; selling_price: number }) => void;
  busy: boolean;
  labels: { name: string; price: string; save: string; cancel: string };
}) {
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const parsed = parseVnd(price);
    if (!name || parsed == null) return;
    onSubmit({ name, selling_price: parsed });
  }

  return (
    <div className="fixed inset-0 bg-slate-900/30 backdrop-blur-sm flex items-center justify-center p-4 z-20">
      <form
        onSubmit={submit}
        className="w-full max-w-sm bg-white rounded-2xl shadow-2xl ring-1 ring-slate-200/60 p-6 space-y-4"
      >
        <Field label={labels.name}>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-lg bg-white ring-1 ring-slate-200 px-3 py-2 focus:ring-2 focus:ring-brand-500 focus:outline-none transition-shadow"
          />
        </Field>
        <Field label={labels.price}>
          <input
            inputMode="numeric"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            className="w-full rounded-lg bg-white ring-1 ring-slate-200 px-3 py-2 focus:ring-2 focus:ring-brand-500 focus:outline-none transition-shadow"
          />
        </Field>
        <div className="flex gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 rounded-lg ring-1 ring-slate-200 text-slate-700 py-2 font-medium hover:bg-slate-50 transition-colors"
          >
            {labels.cancel}
          </button>
          <button
            type="submit"
            disabled={busy}
            className="flex-1 rounded-lg bg-brand-600 text-white py-2 font-medium shadow-sm shadow-brand-600/20 hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {labels.save}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="text-xs font-medium text-slate-500 mb-1.5">{label}</div>
      {children}
    </label>
  );
}
