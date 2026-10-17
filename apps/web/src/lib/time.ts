/** Greeting based on the hour in the user's own timezone, not the browser's or server's. */
export function greetingFor(date: Date, timeZone: string): string {
  let hour: number;
  try {
    hour = Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hourCycle: "h23", timeZone }).format(date));
  } catch {
    hour = date.getUTCHours();
  }
  if (hour < 5) return "Good evening";
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

/**
 * Timezones the browser knows, always including UTC and `current`. Browsers differ on canonical
 * names (Chromium lists "Asia/Calcutta", the IANA database prefers "Asia/Kolkata"), so the user's
 * saved value is added if missing rather than silently disappearing from the dropdown.
 */
export function listTimeZones(current?: string): string[] {
  const intl = Intl as typeof Intl & { supportedValuesOf?: (key: "timeZone") => string[] };
  const zones = new Set(intl.supportedValuesOf?.("timeZone") ?? []);
  zones.add("UTC");
  if (current) zones.add(current);
  return [...zones].sort((a, b) => a.localeCompare(b));
}

export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}
