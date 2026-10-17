import {
  Bell,
  FileText,
  FolderKanban,
  House,
  ListChecks,
  MessageSquare,
  Settings,
  ShieldCheck,
  Workflow,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

// Full list for the desktop sidebar, in the order the PRD gives.
export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Home", icon: House },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/tasks", label: "Tasks", icon: ListChecks },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/automations", label: "Automations", icon: Workflow },
  { href: "/approvals", label: "Approvals", icon: ShieldCheck },
  { href: "/files", label: "Files", icon: FileText },
  { href: "/notifications", label: "Notifications", icon: Bell },
  { href: "/settings", label: "Settings", icon: Settings },
];

// A tab bar holds five items at most, so the rest live under "More" on Settings.
export const TAB_ITEMS: NavItem[] = [
  { href: "/", label: "Home", icon: House },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/tasks", label: "Tasks", icon: ListChecks },
  { href: "/approvals", label: "Approvals", icon: ShieldCheck },
  { href: "/settings", label: "Settings", icon: Settings },
];

// Pages reached from inside a section keep that section highlighted.
const SECTION_ALIASES: Record<string, string> = {
  "/memories": "/chat",
  "/projects": "/tasks",
  "/automations": "/approvals",
  "/files": "/settings",
  "/notifications": "/settings",
};

export function isActive(pathname: string, href: string, aliases = true): boolean {
  if (href === "/") return pathname === "/";
  const section = aliases ? (SECTION_ALIASES[pathname] ?? pathname) : pathname;
  return section === href || section.startsWith(`${href}/`);
}
