"use client";

import { clsx } from "clsx";

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
}

/** Apple's segmented control: one selected segment with a raised thumb. */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  className,
}: {
  label: string;
  value: T;
  options: SegmentOption<T>[];
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={clsx("flex gap-0.5 rounded-control bg-fill p-0.5", className)}
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.value)}
            className={clsx(
              "min-h-9 flex-1 whitespace-nowrap rounded-[0.6rem] px-3 text-subhead transition-colors",
              selected ? "bg-surface font-semibold text-label shadow-sm" : "font-medium text-label-2",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
