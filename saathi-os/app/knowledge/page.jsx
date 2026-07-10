"use client";
import { useState, useEffect, useMemo } from "react";
import { motion } from "framer-motion";
import { Panel, Eyebrow, Pill, Bar } from "@/components/ui";
import { fetchMissions } from "@/lib/api";
import { color } from "@/lib/departments";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_SAATHI_API || "http://localhost:8765";

const NODE_TYPE_META = {
  company: { label: "Company", color: "#E8B84B" },
  brand: { label: "Brand", color: "#C7CEDA" },
  product: { label: "Product", color: "#FF8A3D" },
  service: { label: "Service", color: "#FF8A3D" },
  customer: { label: "Customer", color: "#3E7BFF" },
  employee: { label: "Employee", color: "#3E7BFF" },
  partner: { label: "Partner", color: "#3E7BFF" },
  competitor: { label: "Competitor", color: "#FF5252" },
  document: { label: "Document", color: "#6E72F0" },
  asset: { label: "Asset", color: "#6E72F0" },
  workflow: { label: "Workflow", color: "#35E0D0" },
  automation: { label: "Automation", color: "#35E0D0" },
  prompt: { label: "Prompt", color: "#9B6BFF" },
  dataset: { label: "Dataset", color: "#9B6BFF" },
  evidence: { label: "Evidence", color: "#6E72F0" },
  learning: { label: "Learning", color: "#4FD07A" },
  revenue: { label: "Revenue", color: "#4FD07A" },
  kpi: { label: "KPI", color: "#4FD07A" },
  timeline: { label: "Timeline", color: "#C7CEDA" },
  decision: { label: "Decision", color: "#9B6BFF" },
  risk: { label: "Risk", color: "#FF5252" },
  opportunity: { label: "Opportunity", color: "#4FD07A" },
  account: { label: "Account", color: "#3E7BFF" },
  social_channel: { label: "Social", color: "#3E7BFF" },
  website: { label: "Website", color: "#3E7BFF" },
  file: { label: "File", color: "#6E72F0" },
  meeting: { label: "Meeting", color: "#C7CEDA" },
  task: { label: "Task", color: "#35E0D0" },
};

export default function Knowledge() {
  const [missions, setMissions] = useState([]);
  const [selectedMission, setSelectedMission] = useState(null);
  const [knowledge, setKnowledge] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [selectedTypes, setSelectedTypes] = useState(new Set());
  const [expandedNode, setExpandedNode] = useState(null);

  // Fetch missions on mount
  useEffect(() => {
    fetchMissions()
      .then((ms) => {
        setMissions(ms || []);
        if (ms && ms.length > 0) setSelectedMission(ms[0]);
      })
      .catch(() => setError("Unable to load missions"))
      .finally(() => setLoading(false));
  }, []);

  // Fetch knowledge when mission changes
  useEffect(() => {
    if (!selectedMission) return;
    setLoading(true);
    setError("");
    const mid = selectedMission.id || selectedMission.key;
    fetch(`${API_BASE}/api/v1/missions/${mid}/knowledge`, { credentials: "include" })
      .then((r) => r.json())
      .then((d) => {
        if (d.error) throw new Error(d.error);
        setKnowledge(d);
      })
      .catch((e) => setError(e.message || "Failed to load knowledge graph"))
      .finally(() => setLoading(false));
  }, [selectedMission]);

  // Filtered nodes
  const filteredNodes = useMemo(() => {
    if (!knowledge?.nodes) return [];
    let nodes = knowledge.nodes;
    if (search.trim()) {
      const s = search.toLowerCase();
      nodes = nodes.filter((n) =>
        (n.label || n.key || "").toLowerCase().includes(s) ||
        (n.type || "").toLowerCase().includes(s) ||
        (typeof n.data === "string" ? n.data : JSON.stringify(n.data || "")).toLowerCase().includes(s)
      );
    }
    if (selectedTypes.size > 0) {
      nodes = nodes.filter((n) => selectedTypes.has(n.type || "asset"));
    }
    return nodes;
  }, [knowledge, search, selectedTypes]);

  // Group filtered nodes by type
  const byType = useMemo(() => {
    const groups = {};
    for (const n of filteredNodes) {
      const t = n.type || "asset";
      if (!groups[t]) groups[t] = [];
      groups[t].push(n);
    }
    return groups;
  }, [filteredNodes]);

  const sortedTypes = Object.keys(byType).sort((a, b) => byType[b].length - byType[a].length);
  const allTypes = useMemo(() => {
    if (!knowledge?.nodes) return [];
    const types = new Set(knowledge.nodes.map((n) => n.type || "asset"));
    return Array.from(types).sort((a, b) => {
      const ca = knowledge.nodes.filter((n) => (n.type || "asset") === a).length;
      const cb = knowledge.nodes.filter((n) => (n.type || "asset") === b).length;
      return cb - ca;
    });
  }, [knowledge]);

  const toggleType = (type) => {
    setSelectedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const clearFilters = () => {
    setSearch("");
    setSelectedTypes(new Set());
  };

  if (loading && !knowledge) {
    return (
      <div style={{ maxWidth: 1620, margin: "0 auto", padding: 40 }}>
        <Panel style={{ padding: 60, textAlign: "center" }}>
          <Eyebrow>Loading Knowledge Graph...</Eyebrow>
        </Panel>
      </div>
    );
  }

  const coverage = knowledge?.coverage || {};
  const overall = coverage.overall || 0;
  const counts = knowledge?.counts || {};
  const totalNodes = knowledge?.nodes?.length || 0;

  return (
    <div style={{ maxWidth: 1620, margin: "0 auto" }}>
      {/* Header: mission selector + coverage */}
      <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 24, flexWrap: "wrap" }}>
        <Eyebrow>Knowledge Graph</Eyebrow>
        {missions.length > 1 && (
          <select
            value={selectedMission?.id || ""}
            onChange={(e) => {
              const m = missions.find((x) => x.id === e.target.value);
              if (m) setSelectedMission(m);
            }}
            style={{
              background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: 10,
              padding: "8px 14px",
              color: "var(--color-ink-200)",
              fontSize: 13,
            }}
          >
            {missions.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        )}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 16 }}>
          <span className="mono" style={{ fontSize: 11, color: "var(--color-ink-400)" }}>
            {totalNodes} nodes
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="mono" style={{ fontSize: 11, color: "var(--color-ink-400)" }}>Coverage</span>
            <span
              className="display"
              style={{ fontSize: 22, color: overall >= 0.7 ? "#4FD07A" : overall >= 0.4 ? "#E8B84B" : "#FF5252" }}
            >
              {Math.round(overall * 100)}%
            </span>
          </div>
        </div>
      </div>

      {/* Search + type filters */}
      {totalNodes > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: "flex", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search nodes…"
              style={{
                flex: 1,
                minWidth: 260,
                padding: "10px 14px",
                borderRadius: 12,
                border: "1px solid rgba(255,255,255,0.12)",
                background: "rgba(255,255,255,0.05)",
                color: "inherit",
                fontSize: 14,
              }}
            />
            {(search || selectedTypes.size > 0) && (
              <button
                onClick={clearFilters}
                style={{
                  padding: "10px 16px",
                  borderRadius: 12,
                  border: "1px solid rgba(255,255,255,0.12)",
                  background: "transparent",
                  color: "var(--color-ink-400)",
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                Clear filters
              </button>
            )}
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {allTypes.map((type) => {
              const meta = NODE_TYPE_META[type] || { label: type, color: "#8B98B4" };
              const active = selectedTypes.has(type);
              return (
                <button
                  key={type}
                  onClick={() => toggleType(type)}
                  style={{
                    padding: "5px 12px",
                    borderRadius: 999,
                    border: `1px solid ${active ? meta.color : "rgba(255,255,255,0.12)"}`,
                    background: active ? `${meta.color}18` : "transparent",
                    color: active ? meta.color : "var(--color-ink-400)",
                    fontSize: 12,
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <span style={{ width: 7, height: 7, borderRadius: "50%", background: meta.color }} />
                  {meta.label}
                  <span className="mono" style={{ fontSize: 10, opacity: 0.6 }}>
                    {byType[type]?.length || 0}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Coverage breakdown */}
      {coverage && Object.keys(coverage).length > 1 && (
        <Panel style={{ padding: 24, marginBottom: 24 }}>
          <Eyebrow>Coverage by Category</Eyebrow>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
              gap: 16,
              marginTop: 16,
            }}
          >
            {Object.entries(coverage)
              .filter(([k]) => k !== "overall")
              .map(([k, v]) => (
                <div key={k}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: 11,
                      color: "var(--color-ink-400)",
                      marginBottom: 4,
                      textTransform: "capitalize",
                    }}
                  >
                    <span>{k}</span>
                    <span>{Math.round((v || 0) * 100)}%</span>
                  </div>
                  <Bar frac={v || 0} color={color("KNOWLEDGE")} label="" value="" />
                </div>
              ))}
          </div>
        </Panel>
      )}

      {/* Node type cards */}
      {sortedTypes.length === 0 ? (
        <Panel style={{ padding: 60, textAlign: "center" }}>
          <Eyebrow>No Knowledge Nodes</Eyebrow>
          <p style={{ color: "var(--color-ink-400)", fontSize: 14, marginTop: 12, lineHeight: 1.5 }}>
            {search || selectedTypes.size > 0
              ? "No nodes match your search or filters. Try clearing them."
              : "This mission has no knowledge nodes. Use Mission Intake to add business data, or upload documents to populate the graph."}
          </p>
          {!search && selectedTypes.size === 0 && selectedMission && (
            <Link
              href={`/missions/${selectedMission.id}/intake`}
              style={{
                display: "inline-block",
                marginTop: 16,
                padding: "10px 20px",
                borderRadius: 12,
                background: "#9B6BFF",
                color: "#fff",
                fontSize: 14,
                fontWeight: 600,
                textDecoration: "none",
              }}
            >
              Go to Mission Intake →
            </Link>
          )}
        </Panel>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: 20,
          }}
        >
          {sortedTypes.map((type) => {
            const meta = NODE_TYPE_META[type] || { label: type, color: "#8B98B4" };
            const typeNodes = byType[type];
            return (
              <motion.div
                key={type}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
              >
                <Panel style={{ padding: 22 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: "50%",
                        background: meta.color,
                        boxShadow: `0 0 8px ${meta.color}`,
                      }}
                    />
                    <span style={{ fontWeight: 600, fontSize: 14, color: "var(--color-ink-100)" }}>
                      {meta.label}
                    </span>
                    <Pill color={meta.color} filled={0.16}>
                      {typeNodes.length}
                    </Pill>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {typeNodes.slice(0, 8).map((n) => (
                      <div
                        key={n.key}
                        className="glass-soft"
                        style={{
                          padding: "10px 14px",
                          borderRadius: 10,
                          fontSize: 13,
                          color: "var(--color-ink-200)",
                          cursor: n.data ? "pointer" : "default",
                          transition: "background 0.15s ease",
                        }}
                        onClick={() => n.data && setExpandedNode(expandedNode === n.key ? null : n.key)}
                      >
                        <div style={{ fontWeight: 500 }}>{n.label || n.key}</div>
                        {n.data && (
                          <div
                            className="mono"
                            style={{ fontSize: 10, color: "var(--color-ink-500)", marginTop: 4, lineHeight: 1.5 }}
                          >
                            {expandedNode === n.key
                              ? typeof n.data === "string"
                                ? n.data
                                : JSON.stringify(n.data, null, 2)
                              : typeof n.data === "string"
                                ? n.data.slice(0, 100)
                                : JSON.stringify(n.data).slice(0, 100)}
                          </div>
                        )}
                      </div>
                    ))}
                    {typeNodes.length > 8 && (
                      <div
                        style={{
                          fontSize: 11,
                          color: "var(--color-ink-500)",
                          textAlign: "center",
                          padding: 8,
                        }}
                      >
                        +{typeNodes.length - 8} more
                      </div>
                    )}
                  </div>
                </Panel>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
