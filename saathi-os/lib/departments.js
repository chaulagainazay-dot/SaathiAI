// The immutable color system — each department owns one hue, forever.
export const DEPARTMENTS = {
  EXECUTIVE:   { name: "Executive",   color: "#F4F6FB", route: "/",          short: "Executive" },
  MISSION:     { name: "Mission",     color: "#C7CEDA", route: "/mission",   short: "Mission" },
  FINANCE:     { name: "Finance",     color: "#E8B84B", route: "/finance",   short: "Finance" },
  "AI STUDIO": { name: "AI Studio",   color: "#FF8A3D", route: "/studio",    short: "Studio" },
  KNOWLEDGE:   { name: "Knowledge",   color: "#3E7BFF", route: "/knowledge", short: "Knowledge" },
  LEARNING:    { name: "Learning",    color: "#9B6BFF", route: "/learning",  short: "Learning" },
  DISCOVERY:   { name: "Discovery",   color: "#35E0D0", route: "/discovery", short: "Discovery" },
  TRAVEL:      { name: "Travel",      color: "#5FC8FF", route: "/travel",    short: "Travel" },
  CAFETERIA:   { name: "Cafeteria",   color: "#4FD07A", route: "/cafeteria", short: "Cafe" },
  CRYPTO:      { name: "Crypto",      color: "#FF5A5A", route: "/crypto",    short: "Crypto" },
  OPPORTUNITY: { name: "Opportunity", color: "#14C7B0", route: "/opportunity", short: "Opportunity" },
  MEMORY:      { name: "Memory",      color: "#6E72F0", route: "/memory",    short: "Memory" },
  BUSINESS:    { name: "Business",    color: "#10C98A", route: "/business",  short: "Business" },
  INFRA:       { name: "Infrastructure", color: "#7CF5E4", route: "/infrastructure", short: "Infra" },
  AUTOMATION:  { name: "Automation",    color: "#FF8A3D", route: "/automation",   short: "Auto" },
  MATURITY:    { name: "Maturity",      color: "#E8B84B", route: "/maturity",     short: "Maturity" },
  LAB:         { name: "AI Lab",         color: "#22D3EE", route: "/lab",          short: "Lab" },
  OS:          { name: "Operating System", color: "#F4F6FB", route: "/os",        short: "OS" },
};

export const color = (key) => DEPARTMENTS[key]?.color ?? "#8FA0C4";

// Dock order (per spec) — Executive first, Settings last.
export const DOCK = [
  "OS", "EXECUTIVE", "MISSION", "FINANCE", "AI STUDIO", "KNOWLEDGE",
  "LEARNING", "TRAVEL", "CAFETERIA", "CRYPTO", "DISCOVERY", "INFRA", "AUTOMATION", "MATURITY", "LAB",
];
