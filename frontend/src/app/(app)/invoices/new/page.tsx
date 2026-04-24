"use client";

import { useMutation } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { api } from "@/lib/api";
import { formatVnd, parseVnd } from "@/lib/format";

type Line = {
  sku?: string;
  description?: string;
  quantity: number;
  unit_price: number;
};

type InvoiceType = "import" | "service";

export default function NewInvoicePage() {
  const t = useTranslations("invoices");
  const tc = useTranslations("common");
  const router = useRouter();
  const [type, setType] = useState<InvoiceType>("service");
  const [customerName, setCustomerName] = useState("");
  const [supplierName, setSupplierName] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<Line[]>([
    { sku: "", quantity: 1, unit_price: 0 },
  ]);

  const totals = useMemo(() => {
    const revenue = lines.reduce((s, l) => s + l.quantity * l.unit_price, 0);
    return { revenue };
  }, [lines]);

  const create = useMutation({
    mutationFn: () => {
      if (type === "import") {
        return api.post("/invoices", {
          type: "import",
          supplier_name: supplierName || null,
          items: lines
            .filter((l) => l.sku)
            .map((l) => ({
              sku: l.sku!,
              quantity: l.quantity,
              unit_price: l.unit_price,
            })),
          notes,
        });
      }
      return api.post("/invoices", {
        type: "service",
        customer_name: customerName || null,
        items: lines.map((l) => ({
          sku: l.sku || undefined,
          description: l.description || undefined,
          quantity: l.quantity,
          unit_price: l.unit_price,
        })),
        notes,
      });
    },
    onSuccess: (inv: { id: string }) => router.replace(`/invoices/${inv.id}`),
  });

  function updateLine(idx: number, patch: Partial<Line>) {
    setLines((ls) => ls.map((l, i) => (i === idx ? { ...l, ...patch } : l)));
  }
  function removeLine(idx: number) {
    setLines((ls) => ls.filter((_, i) => i !== idx));
  }

  return (
    <div className="space-y-4 max-w-2xl">
      <h1 className="text-xl font-semibold">{t("new")}</h1>

      <div className="flex gap-2">
        {(["service", "import"] as const).map((v) => (
          <button
            key={v}
            onClick={() => setType(v)}
            className={`flex-1 py-2 rounded-lg border ${
              type === v
                ? "bg-slate-900 text-white border-slate-900"
                : "bg-white border-slate-200"
            }`}
          >
            {t(v)}
          </button>
        ))}
      </div>

      <div className="rounded-xl bg-white p-4 shadow-sm space-y-3">
        {type === "service" ? (
          <Field label={t("customer")}>
            <input
              value={customerName}
              onChange={(e) => setCustomerName(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2"
            />
          </Field>
        ) : (
          <Field label={t("supplier")}>
            <input
              value={supplierName}
              onChange={(e) => setSupplierName(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2"
            />
          </Field>
        )}

        <div className="space-y-2">
          {lines.map((line, i) => (
            <div key={i} className="flex flex-wrap gap-2 items-end">
              <div className="flex-1 min-w-[140px]">
                <div className="text-xs text-slate-500 mb-1">{t("description")} / SKU</div>
                <input
                  value={line.sku || line.description || ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (/^[A-Z0-9\-_]+$/.test(v.toUpperCase()) && v.length <= 40) {
                      updateLine(i, { sku: v.toUpperCase(), description: undefined });
                    } else {
                      updateLine(i, { description: v, sku: undefined });
                    }
                  }}
                  className="w-full rounded-md border border-slate-300 px-3 py-2"
                />
              </div>
              <div className="w-20">
                <div className="text-xs text-slate-500 mb-1">{t("quantity")}</div>
                <input
                  type="number"
                  min={1}
                  value={line.quantity}
                  onChange={(e) => updateLine(i, { quantity: Math.max(1, Number(e.target.value)) })}
                  className="w-full rounded-md border border-slate-300 px-3 py-2"
                />
              </div>
              <div className="w-36">
                <div className="text-xs text-slate-500 mb-1">{t("unitPrice")}</div>
                <input
                  inputMode="numeric"
                  value={line.unit_price || ""}
                  onChange={(e) =>
                    updateLine(i, { unit_price: parseVnd(e.target.value) ?? 0 })
                  }
                  className="w-full rounded-md border border-slate-300 px-3 py-2"
                />
              </div>
              {lines.length > 1 && (
                <button
                  onClick={() => removeLine(i)}
                  className="text-slate-400 hover:text-red-600 px-2 py-2"
                  aria-label="remove line"
                >
                  ×
                </button>
              )}
            </div>
          ))}
          <div className="flex gap-2 text-sm">
            <button
              onClick={() => setLines((l) => [...l, { sku: "", quantity: 1, unit_price: 0 }])}
              className="rounded-md border border-slate-300 px-3 py-1.5"
            >
              {t("addItem")}
            </button>
            {type === "service" && (
              <button
                onClick={() =>
                  setLines((l) => [
                    ...l,
                    { description: "", quantity: 1, unit_price: 0 },
                  ])
                }
                className="rounded-md border border-slate-300 px-3 py-1.5"
              >
                {t("addLabor")}
              </button>
            )}
          </div>
        </div>

        <Field label={t("notes")}>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </Field>

        <div className="flex items-center justify-between border-t border-slate-100 pt-3">
          <span className="text-sm text-slate-500">{t("totalRevenue")}</span>
          <span className="font-semibold">{formatVnd(totals.revenue)}</span>
        </div>

        {create.isError && (
          <div className="text-sm text-red-600">{String(create.error)}</div>
        )}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => router.back()}
            className="flex-1 rounded-md border border-slate-300 py-2"
          >
            {tc("cancel")}
          </button>
          <button
            type="button"
            disabled={create.isPending}
            onClick={() => {
              if (confirm(t("confirmCreate"))) create.mutate();
            }}
            className="flex-1 rounded-md bg-slate-900 text-white py-2 disabled:opacity-50"
          >
            {t("submit")}
          </button>
        </div>
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
