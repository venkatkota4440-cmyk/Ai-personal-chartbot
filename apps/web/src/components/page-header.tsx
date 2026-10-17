import type { ReactNode } from "react";

/** Apple's large title, with an optional trailing action. */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-largetitle font-bold tracking-tight text-label [overflow-wrap:anywhere]">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-subhead text-label-2">{description}</p>}
      </div>
      {actions && <div className="flex flex-none gap-2">{actions}</div>}
    </div>
  );
}
