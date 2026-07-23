/**
 * Operator preferences — theme, density, experience mode.
 * Experience mode changes explanation density only — never authority.
 */

export const PREF_KEYS = {
  theme: "saathi_pref_theme",
  density: "saathi_pref_density",
  experience: "saathi_pref_experience",
  sidebarExpanded: "saathi_pref_sidebar_expanded",
  copilotOpen: "saathi_pref_copilot_open",
};

export const DEFAULTS = {
  theme: "dark", // dark | light | system
  density: "standard", // compact | standard | comfortable
  experience: "expert", // beginner | expert
  sidebarExpanded: true,
  copilotOpen: false,
};

function read(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    if (v == null || v === "") return fallback;
    if (v === "true") return true;
    if (v === "false") return false;
    return v;
  } catch {
    return fallback;
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, String(value));
  } catch {
    /* ignore */
  }
}

export function loadPreferences() {
  return {
    theme: read(PREF_KEYS.theme, DEFAULTS.theme),
    density: read(PREF_KEYS.density, DEFAULTS.density),
    experience: read(PREF_KEYS.experience, DEFAULTS.experience),
    sidebarExpanded: read(PREF_KEYS.sidebarExpanded, DEFAULTS.sidebarExpanded),
    copilotOpen: read(PREF_KEYS.copilotOpen, DEFAULTS.copilotOpen),
  };
}

export function savePreference(key, value) {
  const map = {
    theme: PREF_KEYS.theme,
    density: PREF_KEYS.density,
    experience: PREF_KEYS.experience,
    sidebarExpanded: PREF_KEYS.sidebarExpanded,
    copilotOpen: PREF_KEYS.copilotOpen,
  };
  if (map[key]) write(map[key], value);
}

/**
 * Apply theme + density to documentElement.
 * Theme "system" resolves via matchMedia.
 */
export function applyDocumentPreferences({ theme, density }) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  let resolved = theme || "dark";
  if (resolved === "system") {
    const dark = window.matchMedia?.("(prefers-color-scheme: dark)")?.matches;
    resolved = dark === false ? "light" : "dark";
  }
  if (resolved === "light") {
    root.setAttribute("data-theme", "light");
  } else {
    root.removeAttribute("data-theme");
  }
  if (density && density !== "standard") {
    root.setAttribute("data-density", density);
  } else {
    root.removeAttribute("data-density");
  }
  root.setAttribute("data-experience-mode", theme ? (arguments[0]?.experience || "expert") : "expert");
}

export function applyAllPreferences(prefs) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  let resolved = prefs.theme || "dark";
  if (resolved === "system") {
    const dark = window.matchMedia?.("(prefers-color-scheme: dark)")?.matches;
    resolved = dark === false ? "light" : "dark";
  }
  if (resolved === "light") root.setAttribute("data-theme", "light");
  else root.removeAttribute("data-theme");

  if (prefs.density && prefs.density !== "standard") root.setAttribute("data-density", prefs.density);
  else root.removeAttribute("data-density");

  root.setAttribute("data-experience-mode", prefs.experience || "expert");
}

/** Experience copy helper — never changes authority strings. */
export function experienceLabel(experience, { beginner, expert }) {
  return experience === "beginner" ? beginner : expert;
}
