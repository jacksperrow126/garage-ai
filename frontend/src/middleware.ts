import createMiddleware from "next-intl/middleware";

import { defaultLocale, locales } from "@/i18n/config";

export default createMiddleware({
  locales: locales as unknown as string[],
  defaultLocale,
  // Keep URLs clean: don't prefix the default locale in the path.
  localePrefix: "as-needed",
});

export const config = {
  matcher: ["/((?!api|mcp|_next|.*\\..*).*)"],
};
