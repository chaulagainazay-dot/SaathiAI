"use client";
import { useLive } from "@/components/live/LiveProvider";
import { EnvironmentBadge, AuthorityBadge, StatusBadge } from "@/components/ui";
import { API_BASE } from "@/lib/api";
import { inferEnvironment } from "@/lib/navigation";
import { useShellChrome } from "./ShellChromeContext";

/**
 * Passive status strip. Never executes privileged actions.
 * approvalState: { status: 'ok'|'unavailable'|'loading', count?: number }
 */
export default function StatusBar({ approvalState }) {
  const live = useLive();
  const { prefs } = useShellChrome();
  const env = inferEnvironment(API_BASE);

  let approvalLabel = "Approvals unavailable";
  let approvalStatus = "neutral";
  if (approvalState?.status === "loading") {
    approvalLabel = "Approvals…";
    approvalStatus = "pending";
  } else if (approvalState?.status === "ok" && typeof approvalState.count === "number") {
    approvalLabel = `${approvalState.count} pending`;
    approvalStatus = approvalState.count > 0 ? "pending" : "success";
  } else if (approvalState?.status === "unavailable") {
    approvalLabel = "Approvals unavailable";
    approvalStatus = "warning";
  }

  return (
    <footer className="shell-statusbar only-desktop" role="status" aria-live="polite">
      <div className="shell-statusbar-seg">
        <StatusBadge
          status={live.connected ? "success" : "warning"}
          label={live.connected ? "Live connected" : "Live disconnected"}
        />
      </div>
      <div className="shell-statusbar-seg">
        <EnvironmentBadge env={env} />
      </div>
      <div className="shell-statusbar-seg">
        <AuthorityBadge authority="advisory" label="Operator · advisory default" />
      </div>
      <div className="shell-statusbar-seg">
        <StatusBadge status={approvalStatus} label={approvalLabel} />
      </div>
      <div className="shell-statusbar-seg shell-statusbar-muted mono">
        mode {prefs.experience || "expert"} · density {prefs.density || "standard"}
      </div>
      <div className="shell-statusbar-seg shell-statusbar-muted mono" title={API_BASE || "same-origin"}>
        api {API_BASE === "" ? "same-origin" : (API_BASE || "local").replace(/^https?:\/\//, "").slice(0, 28)}
      </div>
    </footer>
  );
}
