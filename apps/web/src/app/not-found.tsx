import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="text-title1 font-bold text-label">Page not found</h1>
      <p className="text-subhead text-label-2">
        This page does not exist, or you do not have access to it.
      </p>
      <Link href="/" className="min-h-11 text-body font-semibold text-blue">
        Go to Home
      </Link>
    </main>
  );
}
