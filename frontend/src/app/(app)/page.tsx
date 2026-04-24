"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { api } from "@/lib/api";
import { formatDate, formatVnd } from "@/lib/format";

type DailyReport = {
  date: string;
  invoice_count: number;
  total_revenue: number;
  total_cost: number;
  profit: number;
};

type Product = { id: string; name: string; sku: string; quantity: number };

type Invoice = {
  id: string;
  type: "import" | "service";
  status: string;
  created_at: string;
  total_revenue: number;
  profit: number | null;
  customer_name?: string | null;
  supplier_name?: string | null;
};

export default function Dashboard() {
  const t = useTranslations("dashboard");

  const daily = useQuery<DailyReport>({
    queryKey: ["reports", "daily"],
    queryFn: () => api.get("/reports/daily"),
  });

  const lowStock = useQuery<Product[]>({
    queryKey: ["products", "low"],
    queryFn: () => api.get("/products?low_stock_only=true"),
  });

  const recent = useQuery<Invoice[]>({
    queryKey: ["invoices", "recent"],
    queryFn: () => api.get("/invoices?limit=10"),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">{t("today")}</h1>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label={t("revenue")} value={formatVnd(daily.data?.total_revenue ?? 0)} />
        <StatCard label={t("cost")} value={formatVnd(daily.data?.total_cost ?? 0)} />
        <StatCard label={t("profit")} value={formatVnd(daily.data?.profit ?? 0)} emphasize />
        <StatCard label={t("invoiceCount")} value={String(daily.data?.invoice_count ?? 0)} />
      </section>

      <section className="grid md:grid-cols-2 gap-6">
        <Panel title={t("lowStock")}>
          {lowStock.data?.length === 0 && (
            <p className="text-sm text-slate-500">—</p>
          )}
          <ul className="divide-y divide-slate-100">
            {lowStock.data?.map((p) => (
              <li key={p.id} className="py-2 flex justify-between">
                <span className="text-slate-800">
                  {p.name} <span className="text-slate-400">· {p.sku}</span>
                </span>
                <span className="font-mono text-sm text-amber-700">{p.quantity}</span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title={t("recentInvoices")}>
          <ul className="divide-y divide-slate-100">
            {recent.data?.map((inv) => (
              <li key={inv.id} className="py-2 flex justify-between text-sm">
                <span>
                  <span className="text-slate-400 mr-2">
                    {formatDate(inv.created_at)}
                  </span>
                  {inv.customer_name || inv.supplier_name || "—"}{" "}
                  <span className="text-slate-400">· {inv.type}</span>
                </span>
                <span className="font-mono">
                  {formatVnd(inv.profit ?? inv.total_revenue)}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      </section>
    </div>
  );
}

function StatCard({
  label,
  value,
  emphasize,
}: {
  label: string;
  value: string;
  emphasize?: boolean;
}) {
  return (
    <div
      className={`rounded-xl p-4 ${
        emphasize ? "bg-slate-900 text-white" : "bg-white"
      } shadow-sm`}
    >
      <div className={`text-xs ${emphasize ? "text-slate-300" : "text-slate-500"}`}>
        {label}
      </div>
      <div className="text-lg font-semibold mt-1">{value}</div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-white p-4 shadow-sm">
      <h2 className="text-sm font-medium text-slate-500 mb-2">{title}</h2>
      {children}
    </div>
  );
}
