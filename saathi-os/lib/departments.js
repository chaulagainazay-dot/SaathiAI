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
  PROJECTS:    { name: "Projects",       color: "#6C3FCF", route: "/projects",     short: "Projects" },
  OS:          { name: "Operating System", color: "#F4F6FB", route: "/os",        short: "OS" },
  EVIDENCE:    { name: "Evidence",        color: "#6E72F0", route: "/evidence",   short: "Evidence" },
  MISSIONS:    { name: "Missions",        color: "#9B6BFF", route: "/missions",   short: "Missions" },
  SKILLS:      { name: "Skill Library",   color: "#22D3EE", route: "/skills",     short: "Skills" },
  LIBRARY:     { name: "Knowledge Library", color: "#3E7BFF", route: "/knowledge/library", short: "Library" },
  PRODUCTION:  { name: "Production",      color: "#FF8A3D", route: "/automation/production", short: "Production" },
  CONTROL:     { name: "Control Room",    color: "#FF8A3D", route: "/studio/control-room", short: "Control" },
  VOICE:       { name: "Voice",           color: "#00BFA5", route: "/voice",      short: "Voice" },
  WORKSPACE:   { name: "Workspace",       color: "#9B6BFF", route: "/workspace",  short: "Chat" },
  CHAT:        { name: "Saathi Chat",     color: "#00BFA5", route: "/chat",       short: "Chat" },
  STUDIO_OS:   { name: "AI Studio",       color: "#FF8A3D", route: "/studio-os",  short: "Studio" },
  CEO_OS:      { name: "CEO OS",          color: "#F4F6FB", route: "/ceo",        short: "CEO" },
  UNLOCK:      { name: "Unlock",           color: "#7CF5E4", route: "/unlock",     short: "Unlock" },
  CONTROL:     { name: "Control Center",   color: "#7CF5E4", route: "/control",    short: "Control" },
  CONNECTORS:  { name: "Connectors",       color: "#7CF5E4", route: "/connectors", short: "Connect" },
  SECURITY:    { name: "Security",         color: "#FF5A5A", route: "/security",   short: "Security" },
};

export const color = (key) => DEPARTMENTS[key]?.color ?? "#8FA0C4";

// Dock = the REAL, working subsystems (scaffold department pages removed).
export const DOCK = [
  "OS", "CEO_OS", "CHAT", "STUDIO_OS", "WORKSPACE", "EXECUTIVE", "MISSIONS", "VOICE", "AI STUDIO", "CONTROL", "PRODUCTION",
  "EVIDENCE", "LEARNING", "SKILLS", "LIBRARY", "CONNECTORS", "PROJECTS", "LAB", "INFRA", "UNLOCK",
];
