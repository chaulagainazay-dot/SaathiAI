import MobileSaathi from "@/components/mobile/MobileSaathi";

export default function SaathiPage() {
  return (
    <>
      <div className="only-mobile"><MobileSaathi /></div>
      <div className="only-desktop" style={{ maxWidth: 720, margin: "40px auto" }}>
        <MobileSaathi />
      </div>
    </>
  );
}
