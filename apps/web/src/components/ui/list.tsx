import { clsx } from "clsx";
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

/**
 * Apple's inset grouped list: an optional uppercase header, a rounded white
 * card, and hairline separators that stop short of the left edge.
 */
export function ListSection({
  header,
  footer,
  children,
  className,
}: {
  header?: string;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={clsx("flex flex-col gap-2", className)}>
      {header && (
        <h2 className="px-4 text-footnote font-medium uppercase tracking-wide text-label-2">{header}</h2>
      )}
      <div className="overflow-hidden rounded-card bg-surface">
        <div className="hairline flex flex-col">{children}</div>
      </div>
      {footer && <p className="px-4 text-footnote text-label-2">{footer}</p>}
    </section>
  );
}

interface RowProps {
  title: ReactNode;
  subtitle?: ReactNode;
  leading?: ReactNode;
  trailing?: ReactNode;
  href?: string;
  onClick?: () => void;
  className?: string;
}

export function Row({ title, subtitle, leading, trailing, href, onClick, className }: RowProps) {
  const body = (
    <>
      {leading && <span className="flex-none">{leading}</span>}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-body text-label">{title}</span>
        {/* line-clamp keeps a long value, such as a URL, from making the row unreadably tall,
            and [overflow-wrap:anywhere] breaks unbroken strings instead of overflowing the row. */}
        {subtitle && (
          <span className="mt-0.5 line-clamp-2 block text-subhead text-label-2 [overflow-wrap:anywhere]">
            {subtitle}
          </span>
        )}
      </span>
      {trailing}
      {(href || onClick) && <ChevronRight aria-hidden="true" className="size-4 flex-none text-label-3" />}
    </>
  );
  const shared = clsx("flex min-h-11 w-full items-center gap-3 px-4 py-2.5 text-left", className);

  if (href) {
    return (
      <Link href={href} className={clsx(shared, "active:bg-fill")}>
        {body}
      </Link>
    );
  }
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={clsx(shared, "active:bg-fill")}>
        {body}
      </button>
    );
  }
  return <div className={shared}>{body}</div>;
}
