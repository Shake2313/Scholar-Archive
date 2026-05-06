export default function BrowseLoading() {
  return (
    <div className="stack">
      <section className="sectionPanel">
        <div className="skeletonLine" style={{ width: "4rem", marginBottom: 10 }} />
        <div className="skeletonLine" style={{ width: "18rem", height: "2.2rem", marginBottom: 14 }} />
        <div className="skeletonLine" style={{ width: "100%", maxWidth: "44rem", marginBottom: 6 }} />
        <div className="skeletonLine" style={{ width: "70%", maxWidth: "30rem", marginBottom: 20 }} />
        <div
          className="catalogFilters"
          style={{ pointerEvents: "none" }}
        >
          {[1, 2, 3, 4].map((i) => (
            <div className="catalogFilterField" key={i}>
              <div className="skeletonLine" style={{ width: "6rem" }} />
              <div className="skeletonBlock" style={{ minHeight: 50, borderRadius: 16 }} />
            </div>
          ))}
        </div>
      </section>

      <section className="sectionPanel">
        <div className="statsGrid">
          {[1, 2, 3, 4].map((i) => (
            <div className="statCard skeleton" key={i} style={{ minHeight: 80 }} />
          ))}
        </div>
      </section>

      <section className="sectionPanel">
        <div className="sectionHeader">
          <div style={{ display: "grid", gap: 8 }}>
            <div className="skeletonLine" style={{ width: "4rem" }} />
            <div className="skeletonLine" style={{ width: "14rem", height: "1.4rem" }} />
          </div>
        </div>
        <div className="cardGrid">
          {Array.from({ length: 6 }).map((_, i) => (
            <div className="documentCard skeleton" key={i} style={{ minHeight: 160 }} />
          ))}
        </div>
      </section>
    </div>
  );
}
