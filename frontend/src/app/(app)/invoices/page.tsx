"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";

import { api } from "@/lib/api";
import { formatDate, formatVnd } from "@/lib/format";

type Invoice = {
  id: string;
  type: "import" | "service";
  status: "posted" | "adjusted";
  created_at: string;
  customer_name: string | null;
  supplier_name: string | null;
  total_revenue: number;
  total_cost: number;
  profit: number | null;
};

export default function InvoicesPage() {
  const t = useTranslations("invoices");
  const [typeFilter, setTypeFilter] = useState<"" | "import" | "service">("");

  const invoices = useQuery<Invoice[]>({
    queryKey: ["invoices", { typeFilter }],
    queryFn: () => {
      const qs = typeFilter ? `?type=${typeFilter}` : "";
      return api.get(`/invoices${qs}`);
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold flex-1">{t("title")}</h1>
        <Link
          href="/invoices/new"
          className="rounded-lg bg-slate-900 text-white px-4 py-2 text-sm"
        >
          {t("new")}
        </Link>
      </div>

      <div className="flex gap-2 text-sm">
        {(["", "import", "service"] as const).map((v) => (
          <button
            key={v || "all"}
            onClick={() => setTypeFilter(v)}
            className={`px-3 py-1.5 rounded-md border ${
              typeFilter === v
                ? "bg-slate-900 text-white border-slate-900"
                : "bg-white border-slate-200"
            }`}
          >
            {v === "" ? "All" : t(v)}
          </button>
        ))}
      </div>

      <div className="rounded-xl bg-white shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500 border-b border-slate-100">
            <tr>
              <th className="p-3">Date</th>
              <th className="p-3">{t("type")}</th>
              <th className="p-3">{t("customer")}/{t("supplier")}</th>
              <th className="p-3 text-right">{t("totalRevenue")}</th>
              <th className="p-3 text-right">{t("profit")}</th>
              <th className="p-3">{t("status")}</th>
            </tr>
          </thead>
          <tbody>
            {invoices.data?.map((inv) => (
              <tr key={inv.id} className="border-b border-slate-50 hover:bg-slate-50">
                <td className="p-3 text-slate-500 whitespace-nowrap">
                  <Link href={`/invoices/${inv.id}`}>{formatDate(inv.created_at)}</Link>
                </td>
                <td className="p-3">{t(inv.type)}</td>
                <td className="p-3">{inv.customer_name || inv.supplier_name || "—"}</td>
                <td className="p-3 text-right">{formatVnd(inv.total_revenue)}</td>
                <td className="p-3 text-right font-medium">{formatVnd(inv.profit)}</td>
                <td className="p-3">{t(inv.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
