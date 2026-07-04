// Mock data mirroring the design plates. Swap for M1–M5 API calls later.
export const DREAM_TARGET = 7938838.98;

export const home = {
  greeting: "Good morning, Ajay.",
  dateLabel: "MONDAY · 3 JULY 2026",
  priorityScore: 84,
  executionScore: 92,
  executionDelta: 8,
  revenueToday: 1842,
  revenueSplit: "AI STUDIO 41%  ·  CAFETERIA 33%  ·  TRAVEL 18%",
  dreamCurrent: 18214,
  actions: [
    { title: "Approve AI Studio marketing allocation", dept: "FINANCE",
      meta: "$2,000 · ROI 31% · confidence 91%", tag: "APPROVAL" },
    { title: "Review Opportunity #218 — Bittensor", dept: "OPPORTUNITY",
      meta: "Due diligence passed · research 88%", tag: "REVIEW" },
    { title: "Publish Mr. Yeti Lesson #43", dept: "AI STUDIO",
      meta: "Queued · discovery gate passed", tag: "RUN" },
  ],
  approvals: { count: 2, items: ["1 investment", "1 allocation"] },
  notifications: [
    { text: "Knowledge promoted ×2", dept: "KNOWLEDGE" },
    { text: "Learning: 3 proposals", dept: "LEARNING" },
    { text: "Crypto above target", dept: "CRYPTO" },
    { text: "Storage at 71%", dept: "AI STUDIO" },
  ],
  briefing: [
    "Execution improved 8% overnight.",
    "AI Studio contributed 41% of today's revenue.",
    "Finance confidence is high — one trade awaits you.",
    "Momentum remains the strongest strategy.",
    "Fundamental research accuracy is 91%.",
  ],
  quickActions: [
    { label: "Review approvals", dept: "FINANCE", route: "/finance" },
    { label: "Open Mission Control", dept: "MISSION", route: "/mission" },
    { label: "Run AI Studio", dept: "AI STUDIO", route: "/studio" },
  ],
  calendar: [
    { time: "09:00", event: "Cafeteria production review" },
    { time: "13:00", event: "Travel leads follow-up" },
    { time: "16:30", event: "AI Studio publish window" },
  ],
};

// Center "+" quick actions (mobile CEO Companion).
export const quickActions = [
  { label: "Record Revenue", icon: "💰", dept: "CAFETERIA" },
  { label: "Add Expense", icon: "🧾", dept: "FINANCE" },
  { label: "Approve Trade", icon: "✅", dept: "FINANCE" },
  { label: "Publish Video", icon: "🎬", dept: "AI STUDIO" },
  { label: "Cafeteria Sales", icon: "🍚", dept: "CAFETERIA" },
  { label: "Capture Idea", icon: "💡", dept: "KNOWLEDGE" },
  { label: "Scan Receipt", icon: "📸", dept: "BUSINESS" },
  { label: "Voice Note", icon: "🎤", dept: "MEMORY" },
];

// Action-first notifications (each carries an action).
export const notices = [
  { dept: "FINANCE", title: "A better investment appeared.", action: "Review" },
  { dept: "AI STUDIO", title: "Video #42 finished rendering.", action: "View" },
  { dept: "CAFETERIA", title: "Rice waste exceeded target.", action: "Adjust" },
  { dept: "TRAVEL", title: "Two premium leads are waiting.", action: "Open" },
];

export const cafeteria = {
  sales: 235, salesUnits: 171, waste: 3.2, wasteTarget: 4.0,
  forecast: 180, kitchen: "Nominal", staff: "6 / 6 present",
  recommendation: "Reduce Dal Bhat by 8 portions tomorrow — waste trending 3.2%.",
};

export const studio = {
  todayVideo: "Mr. Yeti Lesson #43 — IELTS Speaking",
  publishing: "Queued · discovery gate passed",
  views: 4210, revenue: 86,
};

export const saathiExamples = [
  "Today's cafeteria sold 171 Dal Bhat.",
  "Approve the AI Studio campaign.",
  "How much revenue did we make today?",
  "Show today's priorities.",
];

// Mission Control universe — ring (1..3) and angle in degrees.
export const universe = [
  { dept: "EXECUTIVE", ring: 1, angle: 90 },
  { dept: "FINANCE", ring: 1, angle: 210 },
  { dept: "MISSION", ring: 1, angle: 330 },
  { dept: "AI STUDIO", ring: 2, angle: 40 },
  { dept: "KNOWLEDGE", ring: 2, angle: 130 },
  { dept: "LEARNING", ring: 2, angle: 220 },
  { dept: "DISCOVERY", ring: 2, angle: 315 },
  { dept: "CRYPTO", ring: 3, angle: 15 },
  { dept: "TRAVEL", ring: 3, angle: 100 },
  { dept: "CAFETERIA", ring: 3, angle: 200 },
  { dept: "OPPORTUNITY", ring: 3, angle: 270 },
  { dept: "BUSINESS", ring: 3, angle: 335 },
];

export const flows = [
  { from: "LEARNING", to: "AI STUDIO", color: "#B78CFF" },
  { from: "AI STUDIO", to: "FINANCE", color: "#FFB25A" },
  { from: "KNOWLEDGE", to: "EXECUTIVE", color: "#6E9BFF" },
];

export const health = [
  { name: "Core Runtime", dept: "EXECUTIVE", value: 0.99 },
  { name: "Learning Runtime", dept: "LEARNING", value: 0.94 },
  { name: "Financial Intelligence", dept: "FINANCE", value: 0.97 },
  { name: "Knowledge Graph", dept: "KNOWLEDGE", value: 0.92 },
  { name: "Revenue Engine", dept: "CAFETERIA", value: 0.88 },
  { name: "Governance (L4)", dept: "MISSION", value: 1.0 },
  { name: "Storage Intelligence", dept: "AI STUDIO", value: 0.71 },
  { name: "Mission Control", dept: "MISSION", value: 0.95 },
];

export const finance = {
  health: 91,
  value: 42350,
  valueDelta: 6.2,
  allocation: [
    { name: "Crypto", frac: 0.30, dept: "CRYPTO" },
    { name: "ETF", frac: 0.40, dept: "KNOWLEDGE" },
    { name: "Business", frac: 0.20, dept: "BUSINESS" },
    { name: "Cash", frac: 0.10, dept: "MISSION" },
  ],
  kpis: [
    { k: "WIN RATE", v: "60%", dept: "CAFETERIA" },
    { k: "EXPECTANCY", v: "$88", dept: "FINANCE" },
    { k: "SHARPE", v: "1.4", dept: "KNOWLEDGE" },
    { k: "MAX DD", v: "$300", dept: "CRYPTO" },
  ],
  approvals: [
    { title: "Bittensor (TAO)", verdict: "BUY", meta: "L4 · $5,000" },
    { title: "AI Studio marketing", verdict: "BUY", meta: "L4 · $2,000" },
  ],
  research: [
    { name: "Fundamentals", value: 0.91, dept: "FINANCE" },
    { name: "On-chain", value: 0.86, dept: "KNOWLEDGE" },
    { name: "Sentiment", value: 0.41, dept: "LEARNING" },
  ],
  tabs: ["Portfolio", "Research", "Opportunities", "Trade Journal", "Simulation",
    "Risk", "Capital", "Performance", "Reports"],
  // a deterministic-ish 90d equity curve (0..1 normalized)
  curve: [0.35, 0.33, 0.38, 0.36, 0.34, 0.40, 0.44, 0.42, 0.47, 0.45, 0.50, 0.48,
    0.53, 0.57, 0.55, 0.60, 0.58, 0.63, 0.61, 0.66, 0.64, 0.69, 0.72, 0.70, 0.75,
    0.73, 0.78, 0.76, 0.81, 0.79, 0.84, 0.82, 0.86, 0.88, 0.85, 0.90],
};

// Knowledge graph — normalized coords (0..1), colored by node type.
export const graph = {
  nodes: {
    GOAL: { x: 0.50, y: 0.20, color: "#E8B84B", r: 22, label: "Dream $7.9M", type: "Goal" },
    "STRATEGY A": { x: 0.30, y: 0.34, color: "#C7CEDA", r: 15, label: "Content engine", type: "Strategy" },
    "STRATEGY B": { x: 0.70, y: 0.34, color: "#C7CEDA", r: 15, label: "Capital compounding", type: "Strategy" },
    "CAP · AI STUDIO": { x: 0.18, y: 0.50, color: "#FF8A3D", r: 13, label: "Autonomous video", type: "Capability" },
    "CAP · FINANCE": { x: 0.82, y: 0.50, color: "#E8B84B", r: 13, label: "Decision support", type: "Capability" },
    "KNOWLEDGE 1": { x: 0.34, y: 0.56, color: "#3E7BFF", r: 11, label: "Fundamentals>80", type: "Knowledge" },
    "KNOWLEDGE 2": { x: 0.66, y: 0.56, color: "#3E7BFF", r: 11, label: "Sentiment ≠ basis", type: "Knowledge" },
    DECISION: { x: 0.50, y: 0.48, color: "#9B6BFF", r: 12, label: "Approve TAO", type: "Decision" },
    EXPERIMENT: { x: 0.50, y: 0.62, color: "#35E0D0", r: 11, label: "Template B test", type: "Experiment" },
    "EVIDENCE 1": { x: 0.24, y: 0.66, color: "#6E72F0", r: 9, label: "47 trades", type: "Evidence" },
    "EVIDENCE 2": { x: 0.40, y: 0.70, color: "#6E72F0", r: 9, label: "22 losses", type: "Evidence" },
    IMPROVEMENT: { x: 0.62, y: 0.68, color: "#4FD07A", r: 11, label: "+5% weighting", type: "Improvement" },
    "PRODUCT · YETI": { x: 0.14, y: 0.64, color: "#FF8A3D", r: 10, label: "Mr. Yeti", type: "Product" },
    "PRODUCT · POS": { x: 0.86, y: 0.64, color: "#4FD07A", r: 10, label: "HCG POS", type: "Product" },
  },
  edges: [
    ["GOAL", "STRATEGY A"], ["GOAL", "STRATEGY B"], ["STRATEGY A", "CAP · AI STUDIO"],
    ["STRATEGY B", "CAP · FINANCE"], ["CAP · AI STUDIO", "PRODUCT · YETI"], ["CAP · FINANCE", "DECISION"],
    ["KNOWLEDGE 1", "DECISION"], ["KNOWLEDGE 2", "DECISION"], ["DECISION", "GOAL"],
    ["EXPERIMENT", "IMPROVEMENT"], ["EVIDENCE 1", "IMPROVEMENT"], ["EVIDENCE 2", "KNOWLEDGE 2"],
    ["IMPROVEMENT", "CAP · FINANCE"], ["STRATEGY A", "EXPERIMENT"], ["CAP · FINANCE", "PRODUCT · POS"],
    ["KNOWLEDGE 1", "EVIDENCE 1"],
  ],
  types: [
    { name: "Goal", color: "#E8B84B" }, { name: "Strategy", color: "#C7CEDA" },
    { name: "Capability", color: "#FF8A3D" }, { name: "Knowledge", color: "#3E7BFF" },
    { name: "Decision", color: "#9B6BFF" }, { name: "Experiment", color: "#35E0D0" },
    { name: "Evidence", color: "#6E72F0" }, { name: "Improvement", color: "#4FD07A" },
  ],
};
