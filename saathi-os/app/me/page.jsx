import { redirect } from "next/navigation";

/**
 * M47.5 soft migration — profile absorbed into Settings.
 * Soft redirect also configured in next.config.mjs (query preserved).
 */
export default async function MeRedirectPage({ searchParams }) {
  const sp = typeof searchParams?.then === "function" ? await searchParams : searchParams || {};
  const q = new URLSearchParams(
    Object.entries(sp).flatMap(([k, v]) =>
      Array.isArray(v) ? v.map((x) => [k, String(x)]) : v != null ? [[k, String(v)]] : []
    )
  ).toString();
  redirect(q ? `/settings?${q}` : "/settings");
}
