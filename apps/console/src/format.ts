export function formatUtc(value: string): string {
  return `${new Intl.DateTimeFormat("it-IT", { timeZone: "UTC", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(value))} UTC`;
}
