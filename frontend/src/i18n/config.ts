import { getRequestConfig } from "next-intl/server";

export const locales = ["vi", "en"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "vi";

export default getRequestConfig(async ({ locale }) => {
  const active = (locales as readonly string[]).includes(locale ?? "")
    ? (locale as Locale)
    : defaultLocale;
  return {
    locale: active,
    messages: (await import(`../messages/${active}.json`)).default,
  };
});
