"use client";
import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import Stars from "./Stars";
import TopBar from "./TopBar";
import Dock from "./Dock";
import CommandPalette from "./CommandPalette";
import CeoMode from "./CeoMode";
import PWA from "./PWA";
import MobileTopBar from "./mobile/MobileTopBar";
import MobileTabBar from "./mobile/MobileTabBar";
import QuickSheet from "./mobile/QuickSheet";
import { LiveProvider } from "./live/LiveProvider";
import LiveToasts from "./live/LiveToasts";
import MobileMic from "./MobileMic";

export default function Shell({ children }) {
  const pathname = usePathname();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [ceoOpen, setCeoOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);

  // Public, client-facing pages (shared smart-form) render bare — no dashboard
  // dock/nav/toasts. This is what a client sees when you send them the link.
  if (pathname?.startsWith("/project/create/")) {
    return <main style={{ minHeight: "100vh" }}>{children}</main>;
  }

  useEffect(() => {
    const onKey = (e) => {
      const typing = ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName);
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault(); setPaletteOpen((o) => !o);
      } else if (e.key === " " && !typing && !paletteOpen) {
        e.preventDefault(); setCeoOpen((o) => !o);
      } else if (e.key === "Escape") {
        setPaletteOpen(false); setCeoOpen(false); setSheetOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paletteOpen]);

  return (
    <LiveProvider>
      <PWA />
      <Stars count={90} />

      {/* desktop = Control Center */}
      <div className="only-desktop">
        <TopBar onSearch={() => setPaletteOpen(true)} />
      </div>
      {/* mobile = CEO Companion */}
      <MobileTopBar />

      <main className="app-main">{children}</main>

      {/* chrome */}
      <div className="only-desktop"><Dock /></div>
      <MobileTabBar onAdd={() => setSheetOpen(true)} />
      <QuickSheet open={sheetOpen} onClose={() => setSheetOpen(false)} />
      <div className="only-mobile"><MobileMic /></div>

      <LiveToasts />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <CeoMode open={ceoOpen} onClose={() => setCeoOpen(false)} />
    </LiveProvider>
  );
}
