"use client";

import { useMutation } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import { formatVnd, parseVnd } from "@/lib/format";

type Line = {
  sku?: string;
  description?: string;
  quantity: number;
  unit_price: number;
};

// A category groups one or more lines. The grouping lives only in the form;
// at submit time each line is flattened to a flat invoice item carrying its
// group's name as `category` (empty name → ungrouped).
type Group = {
  id: number;
  name: string;
  lines: Line[];
};

type InvoiceType = "import" | "service";

const newLine = (labor = false): Line =>
  labor ? { description: "", quantity: 1, unit_price: 0 } : { sku: "", quantity: 1, unit_price: 0 };

export default function NewInvoicePage() {
  const t = useTranslations("invoices");
  const tc = useTranslations("common");
  const router = useRouter();
  const nextId = useRef(1);
  const [type, setType] = useState<InvoiceType>("service");
  const [customerName, setCustomerName] = useState("");
  const [supplierName, setSupplierName] = useState("");
  const [discount, setDiscount] = useState(0);
  const [deposit, setDeposit] = useState(0);
  const [notes, setNotes] = useState("");
  const [groups, setGroups] = useState<Group[]>([
    { id: 0, name: "", lines: [newLine()] },
  ]);

  const totals = useMemo(() => {
    const revenue = groups.reduce(
      (s, g) => s + g.lines.reduce((ls, l) => ls + l.quantity * l.unit_price, 0),
      0,
    );
    const amountDue = Math.max(0, revenue - discount - deposit);
    return { revenue, amountDue };
  }, [groups, discount, deposit]);

  // Build the request body for the current form state. Shared by both the
  // create mutation and the live preview so they can never diverge.
  const buildPayload = useCallback(() => {
    // Flatten groups → flat items, tagging each with its group's category.
    const items = groups.flatMap((g) =>
      g.lines.map((l) => ({ line: l, category: g.name.trim() || undefined })),
    );
    if (type === "import") {
      return {
        type: "import",
        supplier_name: supplierName || null,
        items: items
          .filter(({ line }) => line.sku)
          .map(({ line, category }) => ({
            sku: line.sku!,
            category,
            quantity: line.quantity,
            unit_price: line.unit_price,
          })),
        notes,
      };
    }
    return {
      type: "service",
      customer_name: customerName || null,
      items: items.map(({ line, category }) => ({
        sku: line.sku || undefined,
        description: line.description || undefined,
        category,
        quantity: line.quantity,
        unit_price: line.unit_price,
      })),
      discount,
      deposit,
      notes,
    };
  }, [groups, type, supplierName, customerName, discount, deposit, notes]);

  const create = useMutation<{ id: string }>({
    mutationFn: () => api.post<{ id: string }>("/invoices", buildPayload()),
    onSuccess: (inv) => router.replace(`/invoices/${inv.id}`),
  });

  // ── Live PDF preview (debounced) ────────────────────────────────────
  // POST the unsaved payload to the preview endpoint and show the real PDF
  // (exact print output) in an iframe. Only fires once there's a priced line.
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const hasPricedLine = useMemo(
    () => groups.some((g) => g.lines.some((l) => (l.sku || l.description) && l.unit_price > 0)),
    [groups],
  );

  useEffect(() => {
    if (!hasPricedLine) {
      setPreviewUrl(null);
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    setPreviewLoading(true);
    const handle = setTimeout(async () => {
      try {
        const { blob } = await api.postBlob("/invoices/preview-pdf", buildPayload());
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setPreviewUrl(objectUrl);
      } catch {
        if (!cancelled) setPreviewUrl(null);
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    }, 600);
    return () => {
      cancelled = true;
      clearTimeout(handle);
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [buildPayload, hasPricedLine]);

  function updateGroup(gid: number, patch: Partial<Group>) {
    setGroups((gs) => gs.map((g) => (g.id === gid ? { ...g, ...patch } : g)));
  }
  function addGroup() {
    setGroups((gs) => [...gs, { id: nextId.current++, name: "", lines: [newLine()] }]);
  }
  function removeGroup(gid: number) {
    setGroups((gs) => gs.filter((g) => g.id !== gid));
  }
  function addLine(gid: number, labor = false) {
    setGroups((gs) =>
      gs.map((g) => (g.id === gid ? { ...g, lines: [...g.lines, newLine(labor)] } : g)),
    );
  }
  function updateLine(gid: number, idx: number, patch: Partial<Line>) {
    setGroups((gs) =>
      gs.map((g) =>
        g.id === gid
          ? { ...g, lines: g.lines.map((l, i) => (i === idx ? { ...l, ...patch } : l)) }
          : g,
      ),
    );
  }
  function removeLine(gid: number, idx: number) {
    setGroups((gs) =>
      gs.map((g) =>
        g.id === gid ? { ...g, lines: g.lines.filter((_, i) => i !== idx) } : g,
      ),
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{t("new")}</h1>

      <div className="flex flex-col gap-6 xl:flex-row xl:items-start">
        <div className="w-full space-y-4 xl:max-w-2xl xl:shrink-0">
      <div className="flex gap-2">
        {(["service", "import"] as const).map((v) => (
          <button
            key={v}
            onClick={() => setType(v)}
            className={`flex-1 py-2 rounded-lg border cursor-pointer ${
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

        <div className="space-y-3">
          {groups.map((group) => (
            <div key={group.id} className="rounded-lg border border-slate-200">
              {/* Category header */}
              <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2">
                <span className="text-xs font-medium text-slate-500 whitespace-nowrap">
                  {t("category")}
                </span>
                <input
                  value={group.name}
                  onChange={(e) => updateGroup(group.id, { name: e.target.value })}
                  placeholder={t("categoryPlaceholder")}
                  className="flex-1 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
                />
                {groups.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeGroup(group.id)}
                    className="cursor-pointer px-2 py-1 text-slate-400 hover:text-red-600"
                    aria-label="remove category"
                  >
                    ×
                  </button>
                )}
              </div>

              {/* Lines */}
              <div className="space-y-2 p-3">
                {group.lines.map((line, i) => (
                  <div key={i} className="flex flex-wrap items-end gap-2">
                    <div className="min-w-[140px] flex-1">
                      <div className="mb-1 text-xs text-slate-500">{t("description")} / SKU</div>
                      <input
                        value={line.sku || line.description || ""}
                        onChange={(e) => {
                          const v = e.target.value;
                          if (/^[A-Z0-9\-_]+$/.test(v.toUpperCase()) && v.length <= 40) {
                            updateLine(group.id, i, { sku: v.toUpperCase(), description: undefined });
                          } else {
                            updateLine(group.id, i, { description: v, sku: undefined });
                          }
                        }}
                        className="w-full rounded-md border border-slate-300 px-3 py-2"
                      />
                    </div>
                    <div className="w-20">
                      <div className="mb-1 text-xs text-slate-500">{t("quantity")}</div>
                      <input
                        type="number"
                        min={1}
                        value={line.quantity}
                        onChange={(e) =>
                          updateLine(group.id, i, { quantity: Math.max(1, Number(e.target.value)) })
                        }
                        className="w-full rounded-md border border-slate-300 px-3 py-2"
                      />
                    </div>
                    <div className="w-36">
                      <div className="mb-1 text-xs text-slate-500">{t("unitPrice")}</div>
                      <input
                        inputMode="numeric"
                        value={line.unit_price || ""}
                        onChange={(e) =>
                          updateLine(group.id, i, { unit_price: parseVnd(e.target.value) ?? 0 })
                        }
                        className="w-full rounded-md border border-slate-300 px-3 py-2"
                      />
                    </div>
                    {group.lines.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeLine(group.id, i)}
                        className="cursor-pointer px-2 py-2 text-slate-400 hover:text-red-600"
                        aria-label="remove line"
                      >
                        ×
                      </button>
                    )}
                  </div>
                ))}
                <div className="flex gap-2 text-sm">
                  <button
                    type="button"
                    onClick={() => addLine(group.id)}
                    className="cursor-pointer rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-50"
                  >
                    {t("addItem")}
                  </button>
                  {type === "service" && (
                    <button
                      type="button"
                      onClick={() => addLine(group.id, true)}
                      className="cursor-pointer rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-50"
                    >
                      {t("addLabor")}
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}

          <button
            type="button"
            onClick={addGroup}
            className="w-full cursor-pointer rounded-lg border border-dashed border-slate-300 py-2 text-sm font-medium text-slate-600 hover:border-slate-400 hover:bg-slate-50"
          >
            + {t("addCategory")}
          </button>
        </div>

        <Field label={t("notes")}>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </Field>

        <div className="space-y-2 border-t border-slate-100 pt-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-500">{t("totalRevenue")}</span>
            <span className="font-medium">{formatVnd(totals.revenue)}</span>
          </div>
          {type === "service" && (
            <>
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-slate-500">{t("discount")}</span>
                <input
                  inputMode="numeric"
                  value={discount || ""}
                  onChange={(e) => setDiscount(parseVnd(e.target.value) ?? 0)}
                  className="w-36 rounded-md border border-slate-300 px-3 py-1.5 text-right"
                />
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-slate-500">{t("deposit")}</span>
                <input
                  inputMode="numeric"
                  value={deposit || ""}
                  onChange={(e) => setDeposit(parseVnd(e.target.value) ?? 0)}
                  className="w-36 rounded-md border border-slate-300 px-3 py-1.5 text-right"
                />
              </div>
              <div className="flex items-center justify-between border-t border-slate-100 pt-2">
                <span className="text-sm font-medium text-slate-700">{t("amountDue")}</span>
                <span className="text-lg font-semibold">{formatVnd(totals.amountDue)}</span>
              </div>
            </>
          )}
        </div>

        {create.isError && (
          <div className="text-sm text-red-600">{String(create.error)}</div>
        )}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => router.back()}
            className="flex-1 cursor-pointer rounded-md border border-slate-300 py-2"
          >
            {tc("cancel")}
          </button>
          <button
            type="button"
            disabled={create.isPending}
            onClick={() => {
              if (confirm(t("confirmCreate"))) create.mutate();
            }}
            className="flex-1 cursor-pointer rounded-md bg-slate-900 py-2 text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t("submit")}
          </button>
        </div>
      </div>
        </div>

        {/* Live preview — uses the empty space on wide screens. */}
        <div className="hidden flex-1 xl:block">
          <div className="sticky top-20">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
                {t("preview")}
              </span>
              {previewLoading && (
                <span className="text-xs text-slate-400">{t("previewUpdating")}</span>
              )}
            </div>
            <div className="h-[80vh] overflow-hidden rounded-xl border border-slate-200 bg-slate-100 shadow-sm">
              {previewUrl ? (
                <iframe
                  title="invoice-preview"
                  src={`${previewUrl}#toolbar=0&navpanes=0&view=FitH`}
                  className="h-full w-full"
                />
              ) : (
                <div className="grid h-full place-items-center px-6 text-center text-sm text-slate-400">
                  {t("previewEmpty")}
                </div>
              )}
            </div>
          </div>
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
