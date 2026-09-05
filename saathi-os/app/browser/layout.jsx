// The Browser surface reuses the NEPSE module's visual language: same tokens,
// tables and callouts. It lives outside /nepse because it is not a market screen —
// it reads any allowlisted page — so the stylesheet is imported here rather than
// inherited from that route's layout.
import "../nepse/nepse.css";

export const metadata = {
  title: "Browser · SaathiOS",
  description:
    "Read a real page through the governed browser: domain policy, risk and the execution ledger apply to every request. Read-only.",
};

export default function BrowserLayout({ children }) {
  return children;
}
