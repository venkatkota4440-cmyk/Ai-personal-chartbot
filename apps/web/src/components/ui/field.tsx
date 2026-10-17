import * as Label from "@radix-ui/react-label";
import { clsx } from "clsx";
import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";

const control =
  "min-h-11 w-full rounded-control border bg-surface px-3 text-body text-label placeholder:text-label-3 " +
  "focus-visible:border-blue aria-[invalid=true]:border-red";

interface ShellProps {
  label: string;
  hint?: string;
  error?: string;
  children: (ids: { id: string; describedBy: string | undefined; invalid: boolean }) => ReactNode;
}

function FieldShell({ label, hint, error, children }: ShellProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <Label.Root htmlFor={id} className="text-subhead font-medium text-label">
        {label}
      </Label.Root>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {hint && (
        <p id={hintId} className="text-footnote text-label-2">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-footnote text-red">
          {error}
        </p>
      )}
    </div>
  );
}

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string;
}

export function TextField({ label, hint, error, className, ...props }: TextFieldProps) {
  return (
    <FieldShell label={label} hint={hint} error={error}>
      {({ id, describedBy, invalid }) => (
        <input
          {...props}
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid}
          className={clsx(control, invalid ? "border-red" : "border-separator", className)}
        />
      )}
    </FieldShell>
  );
}

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  hint?: string;
  error?: string;
  options: { value: string; label: string }[];
}

export function SelectField({ label, hint, error, options, className, ...props }: SelectFieldProps) {
  return (
    <FieldShell label={label} hint={hint} error={error}>
      {({ id, describedBy, invalid }) => (
        <select
          {...props}
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid}
          className={clsx(control, invalid ? "border-red" : "border-separator", className)}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </FieldShell>
  );
}
