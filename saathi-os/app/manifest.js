export default function manifest() {
  return {
    name: "SaathiAI — CEO Companion",
    short_name: "SaathiAI",
    description: "Your AI Operating System. Mobile is for deciding.",
    start_url: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#05070f",
    theme_color: "#070c17",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
