"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { api } from "@/lib/api";

type Supplier = { id: string; name: string; phone: string; address: string };

export default function SuppliersPage() {
  const t = useTranslations("suppliers");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");

  const suppliers = useQuery<Supplier[]>({
    queryKey: ["suppliers"],
    queryFn: () => api.get("/suppliers"),
  });

  const create = useMutation({
    mutationFn: (body: { name: string; phone: string; address: string }) =>
      api.post("/suppliers", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["suppliers"] });
      setAdding(false);
      setName("");
      setPhone("");
      setAddress("");
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

      {adding && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!name) return;
            create.mutate({ name, phone, address });
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
          <input
            placeholder={t("address")}
            value={address}
            onChange={(e) => setAddress(e.target.value)}
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
        {suppliers.data?.map((s) => (
          <div key={s.id} className="p-3">
            <div className="font-medium">{s.name}</div>
            <div className="text-sm text-slate-500">
              {s.phone || "—"} · {s.address || "—"}
            </div>
          </div>
        ))}
        {suppliers.data?.length === 0 && (
          <div className="p-6 text-center text-slate-400 text-sm">—</div>
        )}
      </div>
    </div>
  );
}
