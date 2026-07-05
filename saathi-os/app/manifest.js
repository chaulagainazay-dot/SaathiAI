// PWA manifest — makes SaathiAI OS installable (ported from the Baadar PWA).
export default function manifest() {
  return {
    name: "SaathiAI OS",
    short_name: "Saathi",
    description: "Your AI Operating System",
    start_url: "/os",
    display: "standalone",
    background_color: "#090912",
    theme_color: "#090912",
    icons: [
      { src: "/icon.png", sizes: "512x512", type: "image/png", purpose: "any maskable" },
    ],
  };
}
