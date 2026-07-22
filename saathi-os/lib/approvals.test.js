import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  normalizeConnectorApproval,
  normalizeRecommendation,
  aggregateApprovals,
  filterApprovals,
  sortApprovals,
  extractList,
} from "./approvals.js";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("approval normalization", () => {
  it("connector canDecide only with id", () => {
    const a = normalizeConnectorApproval({ id: "x1", title: "Run tool" });
    assert.equal(a.canDecide, true);
    assert.equal(a.decideKind, "connector");
    const b = normalizeConnectorApproval({ title: "No id" });
    assert.equal(b.canDecide, false);
  });

  it("recommendation maps pending", () => {
    const r = normalizeRecommendation({ id: "r1", title: "Try X", status: "pending" });
    assert.equal(r.type, "recommendation");
    assert.equal(r.canDecide, true);
  });
});

describe("aggregateApprovals honesty", () => {
  it("unavailable is not zero total", () => {
    const r = aggregateApprovals({
      connectorsStatus: "unavailable",
      connectorsError: "fail",
      controlStatus: "unavailable",
      recommendationsStatus: "unavailable",
    });
    assert.equal(r.hasConnectedSource, false);
    assert.equal(r.pendingTotal, null);
    assert.ok(r.sources.some((s) => s.status === "not_integrated"));
  });

  it("connected empty list yields pendingTotal 0 from that source", () => {
    const r = aggregateApprovals({
      connectors: [],
      connectorsStatus: "connected",
      controlStatus: "unavailable",
      recommendations: [],
      recommendationsStatus: "connected",
    });
    assert.equal(r.pendingTotal, 0);
    assert.equal(r.hasConnectedSource, true);
  });

  it("partial when mix connected and unavailable", () => {
    const r = aggregateApprovals({
      connectors: [{ id: "1", title: "A" }],
      connectorsStatus: "connected",
      controlStatus: "unavailable",
      recommendationsStatus: "unavailable",
    });
    assert.equal(r.partial, true);
    assert.equal(r.items.length, 1);
  });
});

describe("filter/sort", () => {
  const items = [
    normalizeConnectorApproval({ id: "1", title: "Alpha", risk: "high" }),
    normalizeRecommendation({ id: "2", title: "Beta", status: "pending" }),
  ];
  it("filters by type", () => {
    assert.equal(filterApprovals(items, { type: "connector" }).length, 1);
  });
  it("sorts urgency with canDecide first", () => {
    const s = sortApprovals(items, "urgency");
    assert.ok(s[0].canDecide);
  });
});

describe("extractList", () => {
  it("reads items array", () => {
    assert.deepEqual(extractList({ items: [1] }), [1]);
  });
});

describe("approvals page safety", () => {
  const src = readFileSync(join(root, "app/approvals/page.jsx"), "utf8");
  it("uses ConfirmDialog before decide", () => {
    assert.match(src, /ConfirmDialog/);
    assert.match(src, /platformDecideApproval/);
    assert.match(src, /not_integrated|not shown as zero|not displayed as zero/i);
  });
  it("does not call decide inside load()", () => {
    const loadBlock = src.match(/const load = useCallback\(async \(\) => \{[\s\S]*?\}, \[\]\);/);
    assert.ok(loadBlock, "load callback present");
    assert.doesNotMatch(loadBlock[0], /platformDecideApproval|decideRecommendation/);
    assert.match(src, /runDecision/);
  });
});
