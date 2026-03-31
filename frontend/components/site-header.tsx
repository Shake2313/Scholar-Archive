import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="siteHeader">
      <div className="siteHeaderInner">
        <Link className="brandBlock" href="/">
          <span className="brandKicker">Digital humanities archive</span>
          <span className="brandTitle">Scholar Archive</span>
        </Link>
        <nav className="siteNav">
          <Link href="/">Home</Link>
          <Link href="/browse/era">By Era</Link>
          <Link href="/browse/author">By Author</Link>
        </nav>
      </div>
    </header>
  );
}
