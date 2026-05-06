export default function HomeLoading() {
  return (
    <div className="stack">
      <section className="heroPanel heroPanelWide">
        <div className="heroCopyBlock">
          <div className="skeletonLine" style={{ width: "6rem", marginBottom: 12 }} />
          <div className="skeletonLine" style={{ width: "16rem", height: "3.5rem", borderRadius: 12, marginBottom: 14 }} />
          <div className="skeletonLine" style={{ width: "100%", maxWidth: "36rem", marginBottom: 6 }} />
          <div className="skeletonLine" style={{ width: "80%", maxWidth: "28rem", marginBottom: 20 }} />
          <div className="skeletonBlock" style={{ height: 52, borderRadius: 999 }} />
        </div>
        <div className="heroAside">
          <div style={{ display: "grid", gap: 10 }}>
            <div className="skeletonBlock" style={{ height: 48, borderRadius: 999 }} />
            <div className="skeletonBlock" style={{ height: 48, borderRadius: 999 }} />
            <div className="skeletonBlock" style={{ height: 48, borderRadius: 999 }} />
          </div>
          <div className="heroStatStrip">
            {[1, 2, 3].map((i) => (
              <div className="heroStatChip skeleton" key={i} style={{ minWidth: 120 }}>
                <div className="skeletonLine" style={{ width: "3rem", height: "1.6rem" }} />
                <div className="skeletonLine" style={{ width: "5rem" }} />
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="sectionPanel">
        <div className="sectionHeader">
          <div style={{ display: "grid", gap: 8 }}>
            <div className="skeletonLine" style={{ width: "4rem" }} />
            <div className="skeletonLine" style={{ width: "10rem", height: "1.6rem" }} />
          </div>
        </div>
        <div className="cardGrid">
          {[1, 2, 3].map((i) => (
            <div className="documentCard skeleton" key={i} style={{ minHeight: 160 }} />
          ))}
        </div>
      </section>
    </div>
  );
}
