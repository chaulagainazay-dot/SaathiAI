// NEPSE snapshot seed — deterministic, in-repo, NOT a live feed.
//
// BOUNDARY: this is a single dated snapshot used to power the UI without any
// external side effect (no network, no broker, no OAuth). Figures are
// representative, not authoritative market data. See spec Article I alignment.

export const SNAPSHOT_DATE = "2026-08-30";
export const CURRENCY = "NPR";

export const SECTORS = [
  "Commercial Banks",
  "Development Banks",
  "Finance",
  "Microfinance",
  "Life Insurance",
  "Non-Life Insurance",
  "Hydropower",
  "Hotels & Tourism",
  "Manufacturing",
  "Investment",
  "Trading",
];

// symbol, name, sector, ltp, prevClose, high52, low52, eps, bookValue,
// paidUp (Rs, in mn), rsi, listedShares (mn). P/E, P/B, marketCap derived.
const RAW = [
  ["NABIL", "Nabil Bank", "Commercial Banks", 512, 508.5, 640, 448, 33.4, 320, 22400, 54, 435.9],
  ["NICA", "NIC Asia Bank", "Commercial Banks", 348, 352, 470, 300, 18.9, 210, 19800, 41, 480.2],
  ["SCB", "Standard Chartered Nepal", "Commercial Banks", 605, 601, 720, 520, 40.1, 355, 12700, 58, 210.1],
  ["EBL", "Everest Bank", "Commercial Banks", 640, 632, 780, 560, 44.7, 402, 13500, 61, 211.0],
  ["GBIME", "Global IME Bank", "Commercial Banks", 214, 217, 300, 190, 15.2, 165, 30800, 38, 1439.0],
  ["NRIC", "Nepal Reinsurance", "Non-Life Insurance", 780, 762, 980, 610, 21.0, 190, 19500, 66, 250.0],
  ["HRL", "Himalayan Reinsurance", "Non-Life Insurance", 505, 512, 700, 410, 12.3, 130, 11000, 44, 217.8],
  ["NLIC", "Nepal Life Insurance", "Life Insurance", 1040, 1012, 1400, 820, 41.5, 470, 17600, 63, 169.2],
  ["LICN", "Life Insurance Co. Nepal", "Life Insurance", 1520, 1498, 2100, 1180, 55.2, 560, 8300, 57, 54.6],
  ["CHCL", "Chilime Hydropower", "Hydropower", 505, 498, 640, 420, 20.4, 240, 15200, 49, 301.0],
  ["UPPER", "Upper Tamakoshi Hydropower", "Hydropower", 300, 306, 420, 250, 8.6, 128, 39300, 34, 1310.0],
  ["API", "Api Power", "Hydropower", 268, 259, 360, 195, 9.9, 96, 4400, 71, 164.2],
  ["SHIVM", "Shivam Cements", "Manufacturing", 585, 575, 720, 480, 34.8, 300, 13500, 52, 230.7],
  ["HDL", "Himalayan Distillery", "Manufacturing", 1720, 1690, 2200, 1300, 78.0, 640, 3600, 59, 20.9],
  ["UNL", "Unilever Nepal", "Manufacturing", 42500, 42010, 52000, 33000, 1450, 3400, 92, 68, 0.9],
  ["SONA", "Sona Hotel", "Hotels & Tourism", 610, 622, 820, 470, 14.2, 175, 800, 39, 13.1],
  ["OHL", "Oriental Hotels", "Hotels & Tourism", 705, 690, 900, 560, 19.1, 220, 1300, 55, 18.4],
  ["CIT", "Citizen Investment Trust", "Investment", 2350, 2298, 3100, 1900, 120.5, 900, 3200, 62, 13.6],
  ["NIFRA", "Nepal Infrastructure Bank", "Development Banks", 205, 210, 320, 178, 7.4, 118, 20000, 33, 976.1],
  ["SANIMA", "Sanima Bank", "Commercial Banks", 318, 315, 400, 270, 21.6, 190, 16600, 47, 521.9],
  ["CBBL", "Chhimek Laghubitta", "Microfinance", 890, 905, 1250, 700, 42.0, 360, 2600, 43, 29.2],
  ["SKBBL", "Sana Kisan Laghubitta", "Microfinance", 1180, 1150, 1600, 900, 61.5, 480, 2200, 60, 18.6],
  ["NRN", "NRN Infrastructure & Dev.", "Development Banks", 132, 135, 190, 110, 4.9, 105, 3000, 30, 22.7],
  ["PRVU", "Prabhu Bank", "Commercial Banks", 178, 176, 240, 150, 11.8, 150, 23400, 45, 1314.0],
];

function derive(r) {
  const [symbol, name, sector, ltp, prevClose, high52, low52, eps, bookValue, paidUp, rsi, listedShares] = r;
  const pe = eps > 0 ? +(ltp / eps).toFixed(2) : null;
  const pb = bookValue > 0 ? +(ltp / bookValue).toFixed(2) : null;
  const marketCap = ltp * listedShares * 1e6; // listedShares in millions
  return { symbol, name, sector, ltp, prevClose, high52, low52, eps, bookValue, paidUp, rsi, listedShares, pe, pb, marketCap };
}

export const STOCKS = RAW.map(derive);

export function getStock(symbol) {
  const s = String(symbol || "").toUpperCase();
  return STOCKS.find((x) => x.symbol === s) || null;
}

// Broker CODE → NAME only.
//
// The turnover, trade counts and ranking that used to sit here were invented, as
// was brokersForStock(), which generated a per-stock breakdown from the sum of a
// symbol's character codes. All of that now comes from the exchange floorsheet
// (/api/nepse/floorsheet). What survives is the one thing a name list can honestly
// provide: a mapping from the numeric code a floorsheet carries to a firm's name.
// It is INCOMPLETE — NEPSE licenses far more brokers than these — so a code absent
// from this list is rendered as a bare code, never as a guessed name.
export const BROKERS = [
  { code: 58, name: "Naasa Securities" },
  { code: 45, name: "Kumari Securities" },
  { code: 42, name: "Sani Securities" },
  { code: 34, name: "Online Securities" },
  { code: 28, name: "Nabil Investment" },
  { code: 13, name: "Sipla Securities" },
  { code: 17, name: "Agrawal Securities" },
  { code: 8, name: "Ashutosh Brokerage" },
];


// The market-wide snapshot and the index-history generator used to live here.
// Both were REMOVED: the snapshot carried a hardcoded index (2557.31) and a
// hardcoded turnover, and the history was a sine wave dressed as an index chart.
// Exchange-wide figures now come from /api/nepse/market, computed from the daily
// archive. Nothing in this file may manufacture a market-level number again.
