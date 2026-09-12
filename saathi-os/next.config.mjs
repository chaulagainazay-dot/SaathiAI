import { toNextRedirects } from "./lib/redirects.js";

// Single-origin topology: the browser talks only to this Next origin (:3100).
// Backend (:8765) prefixes are proxied server-side to a FIXED loopback target —
// the browser never supplies the upstream, and only these exact SaathiOS backend
// prefixes are forwarded (local app/api/* route handlers are disjoint and win via
// afterFiles). Production behind Caddy is unaffected (Caddy proxies /api at the
// edge before Next). Override the target with SAATHI_API_BASE if ever needed.
const BACKEND = process.env.SAATHI_API_BASE || "http://127.0.0.1:8765";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: import.meta.dirname,
  async redirects() {
    // Soft redirects only (permanent: false). Query strings preserved by Next.js.
    return toNextRedirects();
  },
  async rewrites() {
    // afterFiles: filesystem routes (app/api/*) resolve first; only these backend
    // prefixes fall through to :8765. Fixed destination — never browser-supplied.
    return [
      { source: "/api/v1/:path*", destination: `${BACKEND}/api/v1/:path*` },
      { source: "/api/executive/:path*", destination: `${BACKEND}/api/executive/:path*` },
      { source: "/api/events/:path*", destination: `${BACKEND}/api/events/:path*` },
      { source: "/api/content/:path*", destination: `${BACKEND}/api/content/:path*` },
    ];
  },
};

export default nextConfig;
