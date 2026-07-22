"use client";
import Link from "next/link";
import {
  Card,
  Heading,
  Text,
  Button,
  AuthorityBadge,
  StatusBadge,
} from "@/components/ui";
import { useShellChrome } from "@/components/shell/ShellChromeContext";

const THEMES = [
  { id: "dark", label: "Dark" },
  { id: "light", label: "Light" },
  { id: "system", label: "System" },
];
const DENSITIES = [
  { id: "compact", label: "Compact" },
  { id: "standard", label: "Standard" },
  { id: "comfortable", label: "Comfortable" },
];
const EXPERIENCE = [
  { id: "beginner", label: "Beginner", hint: "Plainer language, fewer IDs" },
  { id: "expert", label: "Expert", hint: "Full detail — same authority" },
];

/**
 * Shell preferences only. Credentials/security policy live under Security.
 * Experience mode never changes authority.
 */
export default function SettingsPage() {
  const { prefs, updatePref, sidebarExpanded, setSidebarExpanded } = useShellChrome();

  return (
    <div className="page shell-page">
      <div className="shell-page-header">
        <Text tone="muted" size="xs" mono>
          Global · Settings
        </Text>
        <Heading level={1} size="xl">
          Settings
        </Heading>
        <Text tone="muted" size="sm" style={{ maxWidth: 560, marginTop: 8, display: "block" }}>
          Appearance and explanation density. Authority and credentials are not controlled here.
        </Text>
        <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
          <AuthorityBadge authority="advisory" label="Authority unchanged by these prefs" />
          <StatusBadge status="info" label={`Experience · ${prefs.experience}`} />
        </div>
      </div>

      <div className="shell-page-grid">
        <Card>
          <Heading level={2} size="md">
            Theme
          </Heading>
          <div className="shell-pref-row">
            {THEMES.map((t) => (
              <Button
                key={t.id}
                size="sm"
                variant={prefs.theme === t.id ? "primary" : "secondary"}
                onClick={() => updatePref("theme", t.id)}
                aria-pressed={prefs.theme === t.id}
              >
                {t.label}
              </Button>
            ))}
          </div>
        </Card>

        <Card>
          <Heading level={2} size="md">
            Density
          </Heading>
          <div className="shell-pref-row">
            {DENSITIES.map((d) => (
              <Button
                key={d.id}
                size="sm"
                variant={prefs.density === d.id ? "primary" : "secondary"}
                onClick={() => updatePref("density", d.id)}
                aria-pressed={prefs.density === d.id}
              >
                {d.label}
              </Button>
            ))}
          </div>
        </Card>

        <Card>
          <Heading level={2} size="md">
            Experience mode
          </Heading>
          <Text tone="muted" size="sm" style={{ display: "block", marginBottom: 12 }}>
            Changes copy density only. Does not unlock actions or bypass approvals.
          </Text>
          <div className="shell-pref-row">
            {EXPERIENCE.map((e) => (
              <Button
                key={e.id}
                size="sm"
                variant={prefs.experience === e.id ? "primary" : "secondary"}
                onClick={() => updatePref("experience", e.id)}
                aria-pressed={prefs.experience === e.id}
                title={e.hint}
              >
                {e.label}
              </Button>
            ))}
          </div>
        </Card>

        <Card>
          <Heading level={2} size="md">
            Sidebar
          </Heading>
          <div className="shell-pref-row">
            <Button
              size="sm"
              variant={sidebarExpanded ? "primary" : "secondary"}
              onClick={() => {
                const next = !sidebarExpanded;
                setSidebarExpanded(next);
                updatePref("sidebarExpanded", next);
              }}
            >
              {sidebarExpanded ? "Expanded" : "Collapsed"}
            </Button>
          </div>
        </Card>

        <Card>
          <Heading level={2} size="md">
            Security & credentials
          </Heading>
          <Text tone="muted" size="sm" style={{ display: "block", marginBottom: 12 }}>
            Sensitive settings stay on the Security surface.
          </Text>
          <Link href="/security">
            <Button size="sm" variant="outline">
              Open Security
            </Button>
          </Link>
          <div style={{ marginTop: 8 }}>
            <Link href="/me">
              <Button size="sm" variant="ghost">
                Legacy profile (/me)
              </Button>
            </Link>
          </div>
        </Card>
      </div>
    </div>
  );
}
