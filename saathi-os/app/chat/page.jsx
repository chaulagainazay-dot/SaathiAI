import ChatWorkspace from "@/components/chat/ChatWorkspace";

export const metadata = { title: "Saathi Chat" };

export default function ChatPage() {
  // The one host that opts into the route's own microphone surface. Every
  // other host of ChatWorkspace — the shell's Copilot panel included — leaves
  // it off, so the canonical VoiceRuntimeDock stays the only globally mounted
  // voice surface.
  return <ChatWorkspace voiceEnabled />;
}
