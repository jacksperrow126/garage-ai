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
    mutationFn: (body: { name: string; sku: string; selling_price: number }) =>
      api.post<Product>("/products", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["products"] });
      setAddOpen(false);
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold flex-1">{t("title")}</h1>
        <button
          className="rounded-lg bg-slate-900 text-white px-4 py-2 text-sm"
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
          className="flex-1 min-w-[200px] rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
        <label className="text-sm flex items-center gap-2">
          <input
            type="checkbox"
            checked={lowOnly}
            onChange={(e) => setLowOnly(e.target.checked)}
          />
          {t("lowStockOnly")}
        </label>
      </div>

      <div className="rounded-xl bg-white shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500 border-b border-slate-100">
            <tr>
              <th className="p-3">{t("sku")}</th>
              <th className="p-3">{t("name")}</th>
              <th className="p-3 text-right">{t("quantity")}</th>
              <th className="p-3 text-right">{t("avgCost")}</th>
              <th className="p-3 text-right">{t("sellingPrice")}</th>
            </tr>
          </thead>
          <tbody>
            {products.data?.map((p) => (
              <tr key={p.id} className="border-b border-slate-50">
                <td className="p-3 font-mono">{p.sku}</td>
                <td className="p-3">{p.name}</td>
                <td className="p-3 text-right font-mono">{p.quantity}</td>
                <td className="p-3 text-right">{formatVnd(p.average_cost)}</td>
                <td className="p-3 text-right">{formatVnd(p.selling_price)}</td>
              </tr>
            ))}
            {products.data?.length === 0 && (
              <tr>
                <td colSpan={5} className="p-6 text-center text-slate-400">
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
            sku: t("sku"),
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
  onSubmit: (body: { name: string; sku: string; selling_price: number }) => void;
  busy: boolean;
  labels: { name: string; sku: string; price: string; save: string; cancel: string };
}) {
  const [name, setName] = useState("");
  const [sku, setSku] = useState("");
  const [price, setPrice] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const parsed = parseVnd(price);
    if (!name || !sku || parsed == null) return;
    onSubmit({ name, sku, selling_price: parsed });
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center p-4 z-20">
      <form
        onSubmit={submit}
        className="w-full max-w-sm bg-white rounded-xl shadow-lg p-6 space-y-4"
      >
        <Field label={labels.name}>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </Field>
        <Field label={labels.sku}>
          <input
            value={sku}
            onChange={(e) => setSku(e.target.value.toUpperCase())}
            className="w-full rounded-md border border-slate-300 px-3 py-2 font-mono"
          />
        </Field>
        <Field label={labels.price}>
          <input
            inputMode="numeric"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </Field>
        <div className="flex gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 rounded-md border border-slate-300 py-2"
          >
            {labels.cancel}
          </button>
          <button
            type="submit"
            disabled={busy}
            className="flex-1 rounded-md bg-slate-900 text-white py-2 disabled:opacity-50"
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
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      {children}
    </label>
  );
}
