"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";

import { api } from "@/lib/api";
import { formatDate, formatVnd } from "@/lib/format";

type InvoiceLine = {
  sku: string | null;
  description: string;
  quantity: number;
  unit_price: number;
  cost_price: number;
  line_total_revenue: number;
  line_total_cost: number;
};

type Invoice = {
  id: string;
  type: "import" | "service";
  status: "posted" | "adjusted";
  created_at: string;
  created_by: string;
  supplier_name: string | null;
  customer_name: string | null;
  items: InvoiceLine[];
  total_revenue: number;
  total_cost: number;
  profit: number | null;
  notes: string;
  adjustments: { id: string; type: string; reason: string; created_at: string }[];
};

export default function InvoiceDetailPage() {
  const t = useTranslations("invoices");
  const { id } = useParams<{ id: string }>();

  const invoice = useQuery<Invoice>({
    queryKey: ["invoice", id],
    queryFn: () => api.get(`/invoices/${id}`),
    enabled: !!id,
  });

  if (invoice.isLoading) return <div className="text-slate-500">Loading...</div>;
  if (!invoice.data) return <div className="text-slate-500">Not found.</div>;

  const inv = invoice.data;
  return (
    <div className="space-y-4">
      <div>
        <Link href="/invoices" className="text-sm text-slate-500 hover:underline">
          ← {t("title")}
        </Link>
        <h1 className="text-xl font-semibold mt-2">
          {t(inv.type)} · {formatDate(inv.created_at)}
        </h1>
        <div className="text-sm text-slate-500">
          {inv.customer_name || inv.supplier_name || "—"} · {t(inv.status)} ·{" "}
          <span className="font-mono">{inv.id}</span>
        </div>
      </div>

      <div className="rounded-xl bg-white p-4 shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500">
            <tr>
              <th className="p-2">SKU</th>
              <th className="p-2">{t("description")}</th>
              <th className="p-2 text-right">Qty</th>
              <th className="p-2 text-right">Unit</th>
              <th className="p-2 text-right">Cost</th>
              <th className="p-2 text-right">{t("totalRevenue")}</th>
            </tr>
          </thead>
          <tbody>
            {inv.items.map((it, i) => (
              <tr key={i} className="border-t border-slate-100">
                <td className="p-2 font-mono text-xs">{it.sku ?? "—"}</td>
                <td className="p-2">{it.description}</td>
                <td className="p-2 text-right">{it.quantity}</td>
                <td className="p-2 text-right">{formatVnd(it.unit_price)}</td>
                <td className="p-2 text-right text-slate-500">
                  {formatVnd(it.cost_price)}
                </td>
                <td className="p-2 text-right">{formatVnd(it.line_total_revenue)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t border-slate-200">
            <tr>
              <td colSpan={5} className="p-2 text-right text-slate-500">
                {t("totalRevenue")}
              </td>
              <td className="p-2 text-right font-medium">
                {formatVnd(inv.total_revenue)}
              </td>
            </tr>
            <tr>
              <td colSpan={5} className="p-2 text-right text-slate-500">
                {t("totalCost")}
              </td>
              <td className="p-2 text-right text-slate-500">
                {formatVnd(inv.total_cost)}
              </td>
            </tr>
            <tr>
              <td colSpan={5} className="p-2 text-right">
                {t("profit")}
              </td>
              <td className="p-2 text-right font-semibold">{formatVnd(inv.profit)}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      {inv.notes && (
        <div className="rounded-xl bg-white p-4 shadow-sm text-sm">
          <div className="text-slate-500 mb-1">{t("notes")}</div>
          <div>{inv.notes}</div>
        </div>
      )}

      {inv.adjustments.length > 0 && (
        <div className="rounded-xl bg-white p-4 shadow-sm">
          <h2 className="text-sm text-slate-500 mb-2">{t("adjustments")}</h2>
          <ul className="space-y-2 text-sm">
            {inv.adjustments.map((a) => (
              <li key={a.id} className="border-l-2 border-amber-400 pl-3">
                <div className="text-xs text-slate-500">
                  {formatDate(a.created_at)} · {a.type}
                </div>
                <div>{a.reason}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
