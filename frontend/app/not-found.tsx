import Link from "next/link";

export default function NotFound() {
  return (
    <section className="emptyState">
      <h1>Document not found</h1>
      <p>The requested archive entry does not exist or has not been published.</p>
      <Link className="primaryLink" href="/">
        Return home
      </Link>
    </section>
  );
}
