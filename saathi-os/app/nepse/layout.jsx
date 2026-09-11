import "./nepse.css";
import NepseShell from "@/components/nepse/NepseShell";

export const metadata = {
  title: "NEPSE Portfolio Tracker · SaathiOS",
  description:
    "Track a NEPSE portfolio, screen all listed stocks, and read market breadth — on an in-repo snapshot. Not a live feed, not investment advice.",
};

export default function NepseLayout({ children }) {
  return <NepseShell>{children}</NepseShell>;
}
