export const locales = ["vi", "en"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "vi";
export const LOCALE_COOKIE = "garage_locale";

export function isLocale(v: string | undefined): v is Locale {
  return !!v && (locales as readonly string[]).includes(v);
}
