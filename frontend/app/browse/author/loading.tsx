export default function AuthorLoading() {
  return (
    <div className="stack">
      <section className="sectionPanel">
        <div className="skeletonLine" style={{ width: "3rem", marginBottom: 10 }} />
        <div className="skeletonLine" style={{ width: "16rem", height: "2.2rem", marginBottom: 14 }} />
        <div className="skeletonLine" style={{ width: "100%", maxWidth: "40rem", marginBottom: 20 }} />
        <div className="searchBar" style={{ pointerEvents: "none", marginTop: 0 }}>
          <div className="skeletonBlock" style={{ flex: 1, height: 52, borderRadius: 999 }} />
          <div className="skeletonBlock" style={{ width: 140, height: 52, borderRadius: 999 }} />
        </div>
      </section>

      <section className="sectionPanel">
        <div className="sectionHeader" style={{ marginBottom: 16 }}>
          <div style={{ display: "grid", gap: 8 }}>
            <div className="skeletonLine" style={{ width: "5rem" }} />
            <div className="skeletonLine" style={{ width: "10rem", height: "1.4rem" }} />
          </div>
        </div>
        <div className="facetList">
          {Array.from({ length: 8 }).map((_, i) => (
            <div className="facetRow skeleton" key={i} style={{ minHeight: 52 }} />
          ))}
        </div>
      </section>
    </div>
  );
}
