"use client";
import { useParams, usePathname } from "next/navigation";
import Link from "next/link";

const TABS = [
  { key: "overview", label: "Overview", href: (id) => `/missions/${id}` },
  { key: "intake", label: "Intake", href: (id) => `/missions/${id}/intake` },
  { key: "knowledge", label: "Knowledge", href: (id) => `/knowledge` },
  { key: "website", label: "Website", href: (id) => `/missions/${id}/website` },
  { key: "reference", label: "Reference", href: (id) => `/missions/${id}/reference` },
  { key: "proposal", label: "Proposal", href: (id) => `/missions/${id}/proposal` },
  { key: "voice", label: "Voice", href: (id) => `/missions/${id}/voice` },
  { key: "evidence", label: "Evidence", href: (id) => `/evidence` },
  { key: "learning", label: "Learning", href: (id) => `/learning` },
];

export default function MissionNav({ missionName, missionType }) {
  const { id } = useParams();
  const pathname = usePathname();
  const mid = id || "";

  const active = (tab) => {
    const href = tab.href(mid);
    if (tab.key === "overview" || tab.key === "timeline") {
      return pathname === href;
    }
    return pathname === href || pathname.startsWith(href);
  };

  return (
    <div
      style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        background: "rgba(10,17,32,0.85)",
        backdropFilter: "blur(16px)",
        borderBottom: "1px solid rgba(255,255,255,0.08)",
        padding: "12px 0",
        marginBottom: 20,
      }}
    >
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "0 20px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 10,
          }}
        >
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: "var(--color-ink-300)",
            }}
          />
          <span
            style={{
              fontSize: 15,
              fontWeight: 600,
              color: "var(--text-primary)",
            }}
          >
            {missionName || "Mission"}
          </span>
          {missionType && (
            <span
              className="mono"
              style={{
                fontSize: 10,
                padding: "2px 8px",
                borderRadius: 999,
                background: "rgba(255,255,255,0.08)",
                color: "var(--color-ink-400)",
              }}
            >
              {missionType}
            </span>
          )}
        </div>
        <div
          style={{
            display: "flex",
            gap: 4,
            overflowX: "auto",
            scrollbarWidth: "none",
          }}
        >
          {TABS.map((tab) => {
            const isActive = active(tab);
            return (
              <Link
                key={tab.key}
                href={tab.href(mid)}
                style={{
                  padding: "6px 14px",
                  borderRadius: 10,
                  fontSize: 12.5,
                  fontWeight: 500,
                  whiteSpace: "nowrap",
                  textDecoration: "none",
                  color: isActive
                    ? "var(--text-primary)"
                    : "var(--color-ink-400)",
                  background: isActive
                    ? "rgba(255,255,255,0.10)"
                    : "transparent",
                  border: isActive
                    ? "1px solid rgba(255,255,255,0.15)"
                    : "1px solid transparent",
                  transition: "all 0.15s ease",
                }}
              >
                {tab.label}
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
