import "./globals.css";
import { Jura, Outfit, Geist_Mono } from "next/font/google";
import Shell from "@/components/Shell";

const jura = Jura({ subsets: ["latin"], weight: ["300", "400", "500", "600"], variable: "--font-display", display: "swap" });
const outfit = Outfit({ subsets: ["latin"], weight: ["300", "400", "500", "600", "700"], variable: "--font-ui", display: "swap" });
const geist = Geist_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-mono", display: "swap" });

export const metadata = {
  title: "SaathiAI — Sovereign Orbit",
  description: "An AI Operating System with one center.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${jura.variable} ${outfit.variable} ${geist.variable}`}>
      <body>
        <div className="aurora" />
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
