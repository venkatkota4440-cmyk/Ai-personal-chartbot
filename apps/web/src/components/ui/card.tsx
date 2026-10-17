import { clsx } from "clsx";
import type { ReactNode } from "react";

/** A plain grouped card, for content that is not a list of rows. */
export function Card({
  title,
  description,
  children,
  className,
}: {
  title?: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={clsx("animate-appear rounded-card bg-surface p-4", className)}>
      {title && <h2 className="text-headline font-semibold text-label">{title}</h2>}
      {description && <p className="mt-1 text-subhead text-label-2">{description}</p>}
      <div className={clsx(title && "mt-3")}>{children}</div>
    </section>
  );
}
