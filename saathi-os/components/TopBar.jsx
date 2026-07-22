"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { breadcrumbFor, inferEnvironment } from "@/lib/navigation";
import { API_BASE, platformPendingApprovals } from "@/lib/api";
import {
  EnvironmentBadge,
  AuthorityBadge,
  StatusBadge,
  Button,
  IconButton,
} from "@/components/ui";
import { useShellChrome } from "@/components/shell/ShellChromeContext";
import { useLive } from "@/components/live/LiveProvider";

/**
 * Operator TopBar (M47.2).
 * Never executes privileged actions. Approvals count is honest (unavailable ≠ 0).
 */
export default function TopBar({ onSearch, approvalState, setApprovalState }) {
  const path = usePathname();
  const router = useRouter();
  const crumb = breadcrumbFor(path || "/");
  const env = inferEnvironment(API_BASE);
  const { toggleCopilot } = useShellChrome();
  const live = useLive();
  const [clock, setClock] = useState("");

  useEffect(() => {
    const tick = () =>
      setClock(
        new Date().toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "Asia/Kathmandu",
        })
      );
    tick();
    const id = setInterval(tick, 30000);
    return () => clearInterval(id);
  }, []);

  // Fetch approvals — never invent zero on failure
  useEffect(() => {
    let cancelled = false;
    setApprovalState?.({ status: "loading" });
    platformPendingApprovals()
      .then((data) => {
        if (cancelled) return;
        const list = Array.isArray(data) ? data : data?.items || data?.approvals || data?.pending;
        if (Array.isArray(list)) {
          setApprovalState?.({ status: "ok", count: list.length, source: "connectors" });
        } else if (typeof data?.count === "number") {
          setApprovalState?.({ status: "ok", count: data.count, source: "connectors" });
        } else {
          // Payload shape unexpected — not "zero"
          setApprovalState?.({ status: "unavailable", reason: "unexpected payload shape" });
        }
      })
      .catch(() => {
        if (!cancelled) setApprovalState?.({ status: "unavailable", reason: "fetch failed" });
      });
    return () => {
      cancelled = true;
    };
  }, [setApprovalState]);

  const approvalsDisplay = () => {
    if (!approvalState || approvalState.status === "loading") {
      return { label: "Approvals…", status: "pending" };
    }
    if (approvalState.status === "ok") {
      const n = approvalState.count;
      return {
        label: n === 0 ? "No pending" : `${n} approval${n === 1 ? "" : "s"}`,
        status: n > 0 ? "pending" : "success",
      };
    }
    return { label: "Approvals unavailable", status: "warning" };
  };

  const ap = approvalsDisplay();
  const alertCount = live.notifications?.length || 0;

  return (
    <header className="shell-topbar" role="banner">
      <div className="shell-topbar-left">
        <EnvironmentBadge env={env} />
        <nav className="shell-breadcrumb" aria-label="Breadcrumb">
          <span className="shell-breadcrumb-group mono">{crumb.group}</span>
          <span className="shell-breadcrumb-sep" aria-hidden="true">
            /
          </span>
          <span className="shell-breadcrumb-area">{crumb.area}</span>
        </nav>
      </div>

      <div className="shell-topbar-right">
        {clock && (
          <span className="shell-topbar-clock mono" title="Asia/Kathmandu">
            {clock} KTM
          </span>
        )}

        <Button variant="secondary" size="sm" onClick={onSearch} aria-label="Open command palette">
          ⌘K
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={() => router.push("/command")}
          aria-label="Create or command — opens Command Center"
          title="Sensitive create/act flows open Command Center"
        >
          + Create
        </Button>

        <button
          type="button"
          className="shell-topbar-chip"
          onClick={() => router.push("/approvals")}
          aria-label={`Approvals: ${ap.label}`}
        >
          <StatusBadge status={ap.status} label={ap.label} />
        </button>

        <button
          type="button"
          className="shell-topbar-chip"
          onClick={() => router.push("/monitoring")}
          aria-label={alertCount ? `${alertCount} recent alerts` : "Alerts — open monitoring"}
        >
          <StatusBadge
            status={alertCount ? "pending" : "neutral"}
            label={alertCount ? `${alertCount} alert${alertCount === 1 ? "" : "s"}` : "Alerts"}
          />
        </button>

        <Button variant="primary" size="sm" onClick={toggleCopilot} aria-label="Ask Saathi">
          Ask Saathi
        </Button>

        <AuthorityBadge authority="advisory" label="Owner · advisory default" />

        <IconButton
          label="Settings"
          size={32}
          onClick={() => router.push("/settings")}
        >
          A
        </IconButton>
      </div>
    </header>
  );
}
