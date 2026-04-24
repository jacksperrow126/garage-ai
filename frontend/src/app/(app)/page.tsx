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
    <div className="space-y-8">
      <header className="flex items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
            {t("today")}
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">
            {new Date().toLocaleDateString(undefined, {
              weekday: "long",
              day: "numeric",
              month: "long",
            })}
          </h1>
        </div>
      </header>

      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label={t("revenue")} value={formatVnd(daily.data?.total_revenue ?? 0)} />
        <StatCard label={t("cost")} value={formatVnd(daily.data?.total_cost ?? 0)} />
        <StatCard label={t("profit")} value={formatVnd(daily.data?.profit ?? 0)} emphasize />
        <StatCard label={t("invoiceCount")} value={String(daily.data?.invoice_count ?? 0)} />
      </section>

      <section className="grid md:grid-cols-2 gap-5">
        <Panel title={t("lowStock")}>
          {lowStock.data?.length === 0 && (
            <p className="text-sm text-slate-400">—</p>
          )}
          <ul className="divide-y divide-slate-100">
            {lowStock.data?.map((p) => (
              <li
                key={p.id}
                className="py-2.5 flex items-center justify-between gap-3"
              >
                <span className="text-slate-800 truncate">
                  {p.name}{" "}
                  <span className="font-mono text-xs text-slate-400">
                    · {p.sku}
                  </span>
                </span>
                <span className="shrink-0 rounded-full bg-amber-50 text-amber-700 px-2 py-0.5 font-mono text-xs font-medium">
                  {p.quantity}
                </span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title={t("recentInvoices")}>
          <ul className="divide-y divide-slate-100">
            {recent.data?.map((inv) => (
              <li
                key={inv.id}
                className="py-2.5 flex items-center justify-between gap-3 text-sm"
              >
                <span className="min-w-0 flex-1 truncate">
                  <span className="text-slate-400 mr-2 text-xs tabular-nums">
                    {formatDate(inv.created_at)}
                  </span>
                  <span className="text-slate-800">
                    {inv.customer_name || inv.supplier_name || "—"}
                  </span>{" "}
                  <span className="text-slate-400 text-xs">· {inv.type}</span>
                </span>
                <span className="font-mono tabular-nums text-slate-700">
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
  if (emphasize) {
    return (
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-brand-600 to-brand-800 p-5 text-white shadow-lg shadow-brand-600/20 ring-1 ring-white/10">
        <div className="absolute -right-8 -top-8 size-32 rounded-full bg-white/10 blur-2xl" />
        <div className="relative text-[11px] font-medium uppercase tracking-wider text-brand-100">
          {label}
        </div>
        <div className="relative mt-2 text-xl font-semibold tabular-nums">
          {value}
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-2xl bg-white p-5 ring-1 ring-slate-200/60 shadow-sm">
      <div className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
        {label}
      </div>
      <div className="mt-2 text-xl font-semibold tabular-nums text-slate-900">
        {value}
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl bg-white p-5 ring-1 ring-slate-200/60 shadow-sm">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
        {title}
      </h2>
      {children}
    </div>
  );
}
