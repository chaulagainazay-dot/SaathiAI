import { toNextRedirects } from "./lib/redirects.js";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: import.meta.dirname,
  async redirects() {
    // Soft redirects only (permanent: false). Query strings preserved by Next.js.
    return toNextRedirects();
  },
};

export default nextConfig;
