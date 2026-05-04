export default function EraLoading() {
  return (
    <div className="stack">
      <section className="sectionPanel">
        <div className="skeletonLine" style={{ width: "3rem", marginBottom: 10 }} />
        <div className="skeletonLine" style={{ width: "14rem", height: "2.2rem", marginBottom: 14 }} />
        <div className="skeletonLine" style={{ width: "100%", maxWidth: "38rem", marginBottom: 20 }} />
        <div className="timelineNav" style={{ pointerEvents: "none" }}>
          {[1, 2, 3, 4, 5].map((i) => (
            <div
              className="skeleton"
              key={i}
              style={{ height: 42, width: `${60 + i * 14}px`, borderRadius: 999 }}
            />
          ))}
        </div>
      </section>

      {[1, 2].map((section) => (
        <section className="sectionPanel eraSection" key={section}>
          <div className="eraSectionMeta" style={{ marginBottom: 20 }}>
            <div className="skeletonLine" style={{ width: "10rem", height: "2rem" }} />
            <div className="skeletonLine" style={{ width: "6rem" }} />
          </div>
          <div className="yearBucketList">
            {[1, 2].map((bucket) => (
              <div className="yearBucket" key={bucket}>
                <div className="yearBucketHeader">
                  <div className="skeletonLine" style={{ width: "5rem", height: "1.6rem" }} />
                  <div className="skeletonLine" style={{ width: "3rem" }} />
                </div>
                <div className="cardGrid">
                  {[1, 2].map((card) => (
                    <div className="documentCard skeleton" key={card} style={{ minHeight: 140 }} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
