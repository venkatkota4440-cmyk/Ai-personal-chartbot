import { clsx } from "clsx";
import type { ButtonHTMLAttributes } from "react";

type Variant = "filled" | "tinted" | "plain" | "destructive";

// Apple's button hierarchy: one filled action per view, tinted for secondary, plain for the rest.
const variants: Record<Variant, string> = {
  filled: "bg-blue text-white active:bg-blue-press disabled:bg-gray/40",
  tinted: "bg-blue-tint text-blue active:opacity-70",
  plain: "text-blue active:opacity-50",
  destructive: "bg-red-tint text-red active:opacity-70",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
}

export function Button({ variant = "filled", loading = false, className, children, disabled, ...props }: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={clsx(
        // min-h-11 is Apple's 44pt minimum hit target.
        "inline-flex min-h-11 items-center justify-center gap-2 rounded-control px-4 text-callout font-semibold",
        "transition-[opacity,background-color] duration-150 disabled:cursor-not-allowed disabled:opacity-60",
        variants[variant],
        className,
      )}
    >
      {loading && (
        <span
          aria-hidden="true"
          className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none"
        />
      )}
      {children}
    </button>
  );
}
