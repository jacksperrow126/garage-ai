"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { api } from "@/lib/api";
import { formatVnd } from "@/lib/format";

type PeriodReport = {
  total_revenue: number;
  total_cost: number;
  profit: number;
  invoice_count: number;
};

type TopProduct = {
  sku: string;
  description: string;
  quantity: number;
  revenue: number;
  cost: number;
  profit: number;
};

export default function ReportsPage() {
  const t = useTranslations("reports");
  const td = useTranslations("dashboard");
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  const monthly = useQuery<PeriodReport>({
    queryKey: ["reports", "monthly", year, month],
    queryFn: () => api.get(`/reports/monthly?year=${year}&month=${month}`),
  });

  const top = useQuery<TopProduct[]>({
    queryKey: ["reports", "top"],
    queryFn: () => api.get(`/reports/top-products?period=month&limit=10`),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">{t("title")}</h1>

      <section className="rounded-xl bg-white p-4 shadow-sm space-y-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium text-slate-500 flex-1">{t("monthly")}</h2>
          <input
            type="number"
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="w-24 rounded-md border border-slate-300 px-2 py-1 text-sm"
          />
          <select
            value={month}
            onChange={(e) => setMonth(Number(e.target.value))}
            className="rounded-md border border-slate-300 px-2 py-1 text-sm"
          >
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label={td("revenue")} value={formatVnd(monthly.data?.total_revenue ?? 0)} />
          <Stat label={td("cost")} value={formatVnd(monthly.data?.total_cost ?? 0)} />
          <Stat
            label={td("profit")}
            value={formatVnd(monthly.data?.profit ?? 0)}
            emphasize
          />
          <Stat
            label={td("invoiceCount")}
            value={String(monthly.data?.invoice_count ?? 0)}
          />
        </div>
      </section>

      <section className="rounded-xl bg-white p-4 shadow-sm">
        <h2 className="text-sm font-medium text-slate-500 mb-3">{t("topProducts")}</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-slate-400">
            <tr>
              <th className="p-2">SKU</th>
              <th className="p-2">Name</th>
              <th className="p-2 text-right">Qty</th>
              <th className="p-2 text-right">Profit</th>
            </tr>
          </thead>
          <tbody>
            {top.data?.map((p) => (
              <tr key={p.sku} className="border-t border-slate-100">
                <td className="p-2 font-mono text-xs">{p.sku}</td>
                <td className="p-2">{p.description}</td>
                <td className="p-2 text-right">{p.quantity}</td>
                <td className="p-2 text-right font-medium">{formatVnd(p.profit)}</td>
              </tr>
            ))}
            {top.data?.length === 0 && (
              <tr>
                <td colSpan={4} className="p-4 text-center text-slate-400">
                  —
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function Stat({
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
      className={`rounded-lg p-3 ${emphasize ? "bg-slate-900 text-white" : "bg-slate-50"}`}
    >
      <div
        className={`text-xs ${emphasize ? "text-slate-300" : "text-slate-500"}`}
      >
        {label}
      </div>
      <div className="font-semibold mt-1">{value}</div>
    </div>
  );
}
