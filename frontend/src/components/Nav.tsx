"use client";

import { signOut } from "firebase/auth";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { firebaseAuth } from "@/lib/firebase";
import { LOCALE_COOKIE } from "@/i18n/shared";

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
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  function toggleLocale() {
    const next = locale === "vi" ? "en" : "vi";
    document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=${60 * 60 * 24 * 365}`;
    router.refresh();
  }

  async function logout() {
    await signOut(firebaseAuth());
    router.replace("/login");
  }

  function isActive(href: string) {
    return pathname === href || (href !== "/" && pathname.startsWith(href));
  }

  return (
    <nav className="sticky top-0 z-10 border-b border-slate-200/60 bg-white/70 backdrop-blur-xl">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-4 flex items-center gap-4">
        <Link
          href="/"
          aria-label="Garage AI home"
          className="flex items-center gap-2.5 font-semibold text-slate-900 shrink-0"
        >
          <span className="grid place-items-center size-9 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-md shadow-brand-600/25 ring-1 ring-white/20">
            <WrenchMark />
          </span>
          <span className="hidden sm:inline text-base tracking-tight">
            Garage AI
          </span>
        </Link>

        <ul className="hidden md:flex flex-1 items-center gap-1 text-sm pl-2 lg:pl-4">
          {items.map((it) => (
            <li key={it.key}>
              <Link
                href={it.href}
                className={`px-4 py-2.5 rounded-full whitespace-nowrap transition-colors ${
                  isActive(it.href)
                    ? "bg-brand-50 text-brand-700 font-medium"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                {t(it.key)}
              </Link>
            </li>
          ))}
        </ul>

        <div className="flex-1 md:flex-none" />

        <div className="flex items-center gap-1 md:gap-1 md:pl-2 md:border-l md:border-slate-200/70">
          <button
            onClick={toggleLocale}
            className="rounded-full px-3 py-1.5 text-xs font-semibold text-slate-500 hover:bg-slate-100 hover:text-slate-900 transition-colors"
          >
            {locale === "vi" ? "EN" : "VI"}
          </button>
          <button
            onClick={logout}
            className="hidden md:inline-flex rounded-full px-3 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-900 transition-colors"
          >
            {t("logout")}
          </button>
          <button
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            className="md:hidden grid place-items-center size-10 rounded-full text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors"
          >
            {open ? <CloseIcon /> : <MenuIcon />}
          </button>
        </div>
      </div>

      <div
        className={`md:hidden overflow-hidden border-t border-slate-200/60 transition-[max-height] duration-200 ${
          open ? "max-h-[500px]" : "max-h-0"
        }`}
      >
        <ul className="px-4 py-3 space-y-1">
          {items.map((it) => (
            <li key={it.key}>
              <Link
                href={it.href}
                className={`block px-4 py-3 rounded-xl text-sm transition-colors ${
                  isActive(it.href)
                    ? "bg-brand-50 text-brand-700 font-medium"
                    : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                {t(it.key)}
              </Link>
            </li>
          ))}
          <li className="pt-2 mt-2 border-t border-slate-200/70">
            <button
              onClick={logout}
              className="w-full text-left px-4 py-3 rounded-xl text-sm text-slate-600 hover:bg-slate-100"
            >
              {t("logout")}
            </button>
          </li>
        </ul>
      </div>
    </nav>
  );
}

function WrenchMark() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="size-5"
      aria-hidden="true"
    >
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
    </svg>
  );
}

function MenuIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      className="size-5"
      aria-hidden="true"
    >
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      className="size-5"
      aria-hidden="true"
    >
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}
