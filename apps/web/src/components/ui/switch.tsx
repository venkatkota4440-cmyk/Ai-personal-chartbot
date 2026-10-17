import * as Label from "@radix-ui/react-label";
import * as RadixSwitch from "@radix-ui/react-switch";
import { useId } from "react";

/** Apple's switch: grey when off, green when on, inside a list row. */
export function SwitchField({
  label,
  description,
  checked,
  onCheckedChange,
  disabled,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  const id = useId();
  const descriptionId = description ? `${id}-desc` : undefined;
  return (
    <div className="flex min-h-11 items-center justify-between gap-4 px-4 py-2.5">
      <div className="min-w-0">
        <Label.Root htmlFor={id} className="text-body text-label">
          {label}
        </Label.Root>
        {description && (
          <p id={descriptionId} className="mt-0.5 text-footnote text-label-2">
            {description}
          </p>
        )}
      </div>
      <RadixSwitch.Root
        id={id}
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
        aria-describedby={descriptionId}
        className="relative h-[31px] w-[51px] flex-none rounded-full bg-fill transition-colors data-[state=checked]:bg-green disabled:opacity-50"
      >
        <RadixSwitch.Thumb className="block size-[27px] translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[22px]" />
      </RadixSwitch.Root>
    </div>
  );
}
