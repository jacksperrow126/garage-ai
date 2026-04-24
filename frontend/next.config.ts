import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";

const withNextIntl = createNextIntlPlugin("./src/i18n/config.ts");

/**
 * App Hosting serves the Next.js app; /api/** and /mcp/** are proxied to the
 * FastAPI service on Cloud Run. Same-origin from the browser's perspective
 * means we avoid CORS entirely — the browser calls /api/v1/products and
 * Next.js rewrites server-side to the Cloud Run URL.
 */
const nextConfig: NextConfig = {
  async rewrites() {
    const api = process.env.NEXT_PUBLIC_API_URL;
    if (!api) return [];
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      { source: "/mcp/:path*", destination: `${api}/mcp/:path*` },
    ];
  },
};

export default withNextIntl(nextConfig);
