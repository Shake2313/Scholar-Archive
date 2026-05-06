export default function DocumentDetailLoading() {
  return (
    <div className="viewerShell">
      <aside className="viewerSidebar">
        <div className="viewerSidebarCard">
          <div className="skeletonLine" style={{ width: "8rem", marginBottom: 14 }} />
          <div className="skeletonLine" style={{ width: "3rem", marginBottom: 8 }} />
          <div className="skeletonLine" style={{ width: "90%", height: "1.8rem", marginBottom: 12 }} />
          <div className="skeletonLine" style={{ width: "100%", marginBottom: 6 }} />
          <div className="skeletonLine" style={{ width: "85%", marginBottom: 20 }} />
          <div className="metadataGrid" style={{ pointerEvents: "none" }}>
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i}>
                <div className="skeletonLine" style={{ width: "4rem", marginBottom: 6 }} />
                <div className="skeletonLine" style={{ width: "7rem" }} />
              </div>
            ))}
          </div>
        </div>

        <div className="viewerSidebarCard">
          <div className="skeletonLine" style={{ width: "5rem", marginBottom: 12 }} />
          <div className="skeletonBlock" style={{ height: 72, borderRadius: 14 }} />
        </div>

        <div className="viewerSidebarCard">
          <div className="skeletonLine" style={{ width: "4rem", marginBottom: 12 }} />
          <div style={{ display: "flex", gap: 10 }}>
            <div className="skeletonBlock" style={{ height: 44, flex: 1, borderRadius: 999 }} />
            <div className="skeletonBlock" style={{ height: 44, flex: 1, borderRadius: 999 }} />
          </div>
        </div>

        <div className="viewerSidebarCard">
          <div className="skeletonLine" style={{ width: "4rem", marginBottom: 14 }} />
          <div style={{ display: "grid", gap: 8 }}>
            {Array.from({ length: 5 }).map((_, i) => (
              <div className="skeletonBlock" key={i} style={{ height: 58, borderRadius: 14 }} />
            ))}
          </div>
        </div>
      </aside>

      <section className="viewerMain">
        <div className="viewerToolbar" style={{ pointerEvents: "none" }}>
          <div style={{ display: "flex", gap: 10 }}>
            {[1, 2, 3].map((i) => (
              <div className="skeletonBlock" key={i} style={{ height: 42, width: 130, borderRadius: 999 }} />
            ))}
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            {[1, 2, 3].map((i) => (
              <div className="skeletonBlock" key={i} style={{ height: 42, width: 90, borderRadius: 999 }} />
            ))}
          </div>
        </div>

        <div className="viewerPanels">
          <div className="viewerImagePanel skeleton" style={{ minHeight: "70vh" }} />
          <div className="viewerTextPanel skeleton" style={{ minHeight: "70vh" }} />
        </div>
      </section>
    </div>
  );
}
