import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";

import { defaultLocale, isLocale, LOCALE_COOKIE, type Locale } from "./shared";

export default getRequestConfig(async () => {
  // Skip URL-based locale routing (next-intl middleware was over-rewriting
  // with route groups). Locale lives in a cookie set by the header toggle.
  const cookieStore = await cookies();
  const raw = cookieStore.get(LOCALE_COOKIE)?.value;
  const locale: Locale = isLocale(raw) ? raw : defaultLocale;
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
