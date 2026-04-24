"use client";

import { signOut } from "firebase/auth";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { firebaseAuth } from "@/lib/firebase";

const items = [
  { href: "/", key: "dashboard" as const },
  { href: "/inventory", key: "inventory" as const },
  { href: "/invoices", key: "invoices" as const },
  { href: "/customers", key: "customers" as const },
  { href: "/suppliers", key: "suppliers" as const },
  { href: "/reports", key: "reports" as const },
];

export function Nav() {
  const t = useTranslations("nav");
  const pathname = usePathname();
  const locale = useLocale();
  const router = useRouter();

  async function logout() {
    await signOut(firebaseAuth());
    router.replace("/login");
  }

  function otherLocale(): string {
    return locale === "vi" ? "/en" : "/";
  }

  return (
    <nav className="bg-white border-b border-slate-200 sticky top-0 z-10">
      <div className="mx-auto max-w-6xl px-4 py-3 flex items-center gap-4">
        <Link href="/" className="font-semibold text-slate-900">
          Garage AI
        </Link>
        <ul className="flex-1 flex items-center gap-1 overflow-x-auto text-sm">
          {items.map((it) => {
            const active = pathname === it.href || (it.href !== "/" && pathname.startsWith(it.href));
            return (
              <li key={it.key}>
                <Link
                  href={it.href}
                  className={`px-3 py-1.5 rounded-md whitespace-nowrap ${
                    active ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"
                  }`}
                >
                  {t(it.key)}
                </Link>
              </li>
            );
          })}
        </ul>
        <Link
          href={otherLocale()}
          className="text-sm text-slate-600 hover:underline"
        >
          {locale === "vi" ? "EN" : "VI"}
        </Link>
        <button
          onClick={logout}
          className="text-sm text-slate-600 hover:underline"
        >
          {t("logout")}
        </button>
      </div>
    </nav>
  );
}
