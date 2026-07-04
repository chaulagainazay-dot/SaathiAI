import MobileMe from "@/components/mobile/MobileMe";

export default function MePage() {
  return (
    <>
      <div className="only-mobile"><MobileMe /></div>
      <div className="only-desktop" style={{ maxWidth: 720, margin: "40px auto" }}>
        <MobileMe />
      </div>
    </>
  );
}
