import { Sparkles } from "lucide-react";

export function Brand() {
  return (
    <span className="flex items-center gap-2 text-headline font-semibold tracking-tight text-label">
      <span className="grid size-7 place-items-center rounded-[0.45rem] bg-blue">
        <Sparkles aria-hidden="true" className="size-4 text-white" />
      </span>
      Personal Agent
    </span>
  );
}
