"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useState, type ReactNode } from "react";

/** Apple's alert: centred card, title, message, cancel on the left of the destructive action. */
export function ConfirmDialog({
  trigger,
  title,
  description,
  confirmLabel,
  onConfirm,
}: {
  trigger: ReactNode;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  return (
    <Dialog.Root open={open} onOpenChange={(next) => !pending && setOpen(next)}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(20rem,calc(100vw-3rem))] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl bg-surface text-center shadow-xl">
          <div className="px-5 py-4">
            <Dialog.Title className="text-headline font-semibold text-label">{title}</Dialog.Title>
            <Dialog.Description className="mt-1 text-footnote text-label-2">{description}</Dialog.Description>
          </div>
          <div className="grid grid-cols-2 border-t border-separator">
            <Dialog.Close asChild>
              <button type="button" disabled={pending} className="min-h-11 text-body text-blue active:bg-fill">
                Cancel
              </button>
            </Dialog.Close>
            <button
              type="button"
              disabled={pending}
              onClick={async () => {
                setPending(true);
                try {
                  await onConfirm();
                  setOpen(false);
                } finally {
                  setPending(false);
                }
              }}
              className="min-h-11 border-l border-separator text-body font-semibold text-red active:bg-fill disabled:opacity-50"
            >
              {confirmLabel}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
