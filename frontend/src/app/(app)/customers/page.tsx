"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { api } from "@/lib/api";

type Customer = {
  id: string;
  name: string;
  phone: string;
  vehicles: { license_plate: string; make: string; model: string }[];
  note: string;
};

export default function CustomersPage() {
  const t = useTranslations("customers");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");

  const customers = useQuery<Customer[]>({
    queryKey: ["customers", { search }],
    queryFn: () => api.get(`/customers${search ? `?query=${encodeURIComponent(search)}` : ""}`),
  });

  const create = useMutation({
    mutationFn: (body: { name: string; phone: string }) =>
      api.post("/customers", { ...body, vehicles: [], note: "" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["customers"] });
      setAdding(false);
      setName("");
      setPhone("");
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold flex-1">{t("title")}</h1>
        <button
          onClick={() => setAdding((v) => !v)}
          className="rounded-lg bg-slate-900 text-white px-4 py-2 text-sm"
        >
          {t("add")}
        </button>
      </div>

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search name or phone"
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
      />

      {adding && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!name) return;
            create.mutate({ name, phone });
          }}
          className="rounded-xl bg-white p-4 shadow-sm space-y-3"
        >
          <input
            autoFocus
            placeholder={t("name")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
          <input
            placeholder={t("phone")}
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setAdding(false)}
              className="flex-1 rounded-md border border-slate-300 py-2"
            >
              {tc("cancel")}
            </button>
            <button
              type="submit"
              disabled={create.isPending}
              className="flex-1 rounded-md bg-slate-900 text-white py-2 disabled:opacity-50"
            >
              {tc("save")}
            </button>
          </div>
        </form>
      )}

      <div className="rounded-xl bg-white shadow-sm divide-y divide-slate-100">
        {customers.data?.map((c) => (
          <div key={c.id} className="p-3 flex justify-between">
            <div>
              <div className="font-medium">{c.name}</div>
              <div className="text-sm text-slate-500">{c.phone || "—"}</div>
            </div>
            <div className="text-sm text-slate-400">
              {c.vehicles.length} {t("vehicles").toLowerCase()}
            </div>
          </div>
        ))}
        {customers.data?.length === 0 && (
          <div className="p-6 text-center text-slate-400 text-sm">—</div>
        )}
      </div>
    </div>
  );
}
