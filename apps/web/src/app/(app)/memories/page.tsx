import type { Metadata } from "next";

import { MemoryManager } from "@/components/memory/memory-manager";

export const metadata: Metadata = { title: "Memory" };

export default function MemoriesPage() {
  return <MemoryManager />;
}
