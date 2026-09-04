"use client";
import { useState, useEffect, useCallback } from "react";
import { usePathname, useRouter } from "next/navigation";
import Stars from "./Stars";
import TopBar from "./TopBar";
import CommandPalette from "./CommandPalette";
import CeoMode from "./CeoMode";
import PWA from "./PWA";
import MobileTopBar from "./mobile/MobileTopBar";
import MobileTabBar from "./mobile/MobileTabBar";
import QuickSheet from "./mobile/QuickSheet";
import { LiveProvider } from "./live/LiveProvider";
import LiveToasts from "./live/LiveToasts";
import MobileMic from "./MobileMic";
import Sidebar from "./shell/Sidebar";
import StatusBar from "./shell/StatusBar";
import CopilotPanel from "./shell/CopilotPanel";
import { ShellChromeProvider, useShellChrome } from "./shell/ShellChromeContext";
import { GO_SHORTCUTS } from "@/lib/navigation";
import { ModuleDiscoveryProvider } from "@/lib/modules/ModuleDiscoveryContext";
import { useModuleDiscoveryContext } from "@/lib/modules/ModuleDiscoveryContext";
import ModuleRouteBoundary from "./modules/ModuleRouteBoundary";
import { VoiceSessionProvider } from "./voice/VoiceSessionProvider";
import { VoiceOutputProvider } from "./voice/VoiceOutputProvider";
import VoiceOutputDock from "./voice/VoiceOutputDock";
import { VoiceRuntimeProvider } from "./voice/VoiceRuntimeProvider";
import VoiceRuntimeDock from "./voice/VoiceRuntimeDock";

function ShellInner({ children }) {
  const pathname = usePathname();
  const router = useRouter();
  const bare = pathname?.startsWith("/project/create/");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [ceoOpen, setCeoOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [approvalState, setApprovalState] = useState({ status: "loading" });
  const { sidebarExpanded, copilotOpen, toggleCopilot, closeCopilot, openCopilot } = useShellChrome();
  const moduleDiscovery = useModuleDiscoveryContext();

  useEffect(() => {
    if (bare) return undefined;
    let goArmed = false;
    let goTimer;

    const onKey = (e) => {
      const tag = document.activeElement?.tagName;
      const typing =
        ["INPUT", "TEXTAREA", "SELECT"].includes(tag) ||
        document.activeElement?.isContentEditable;

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
        return;
      }

      if (e.key === "Escape") {
        setPaletteOpen(false);
        setCeoOpen(false);
        setSheetOpen(false);
        closeCopilot();
        return;
      }

      if (typing || paletteOpen) return;

      if (e.key === " " && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        setCeoOpen((o) => !o);
        return;
      }

      if (e.key === "]" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        toggleCopilot();
        return;
      }

      if (e.key === "g" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        goArmed = true;
        clearTimeout(goTimer);
        goTimer = setTimeout(() => {
          goArmed = false;
        }, 800);
        return;
      }
      if (goArmed && e.key.length === 1) {
        const href = GO_SHORTCUTS[e.key.toLowerCase()];
        goArmed = false;
        clearTimeout(goTimer);
        if (href) {
          e.preventDefault();
          router.push(href);
        }
      }
    };

    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      clearTimeout(goTimer);
    };
  }, [bare, paletteOpen, closeCopilot, toggleCopilot, router]);

  const setApproval = useCallback((s) => setApprovalState(s), []);

  if (bare) {
    return <main style={{ minHeight: "100vh" }}>{children}</main>;
  }

  return (
    <LiveProvider>
      <PWA />
      <Stars count={90} />

      {/* Desktop chrome */}
      <div
        className="only-desktop shell-desktop"
        data-sidebar={sidebarExpanded ? "expanded" : "collapsed"}
        data-copilot={copilotOpen ? "open" : "closed"}
      >
        <Sidebar moduleDiscovery={moduleDiscovery} />
        <div className="shell-desktop-main">
          <TopBar
            onSearch={() => setPaletteOpen(true)}
            approvalState={approvalState}
            setApprovalState={setApproval}
          />
        </div>
        <StatusBar approvalState={approvalState} />
        <CopilotPanel />
      </div>

      {/* Mobile chrome */}
      <MobileTopBar />
      <MobileTabBar onAdd={() => setSheetOpen(true)} onCopilot={openCopilot} />
      <QuickSheet open={sheetOpen} onClose={() => setSheetOpen(false)} />
      <div className="only-touch">
        <MobileMic />
      </div>

      {/* Single main content tree (desktop + mobile) */}
      <main
        className="app-main shell-main"
        data-sidebar={sidebarExpanded ? "expanded" : "collapsed"}
        data-copilot={copilotOpen ? "open" : "closed"}
      >
        <ModuleRouteBoundary>{children}</ModuleRouteBoundary>
      </main>

      {copilotOpen && (
        <div className="only-mobile shell-mobile-copilot">
          <div className="shell-mobile-copilot-back" onClick={closeCopilot} aria-hidden="true" />
          <div className="shell-mobile-copilot-sheet" role="dialog" aria-label="Ask Saathi">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <strong>Ask Saathi</strong>
              <button type="button" onClick={closeCopilot} className="shell-topbar-chip">
                Close
              </button>
            </div>
            <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
              Advisory helper. Sensitive actions require Approvals or Command Center.
            </p>
            <a href="/chat" style={{ color: "var(--accent)" }}>
              Open full chat →
            </a>
          </div>
        </div>
      )}

      <LiveToasts />
      <VoiceRuntimeDock />
      <VoiceOutputDock />
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        moduleNavigation={moduleDiscovery.isReady ? moduleDiscovery.navigation : null}
      />
      <CeoMode open={ceoOpen} onClose={() => setCeoOpen(false)} />
    </LiveProvider>
  );
}

export default function Shell({ children }) {
  return (
    <ShellChromeProvider>
      <ModuleDiscoveryProvider>
        <VoiceSessionProvider>
          <VoiceOutputProvider>
            <VoiceRuntimeProvider>
              <ShellInner>{children}</ShellInner>
            </VoiceRuntimeProvider>
          </VoiceOutputProvider>
        </VoiceSessionProvider>
      </ModuleDiscoveryProvider>
    </ShellChromeProvider>
  );
}
