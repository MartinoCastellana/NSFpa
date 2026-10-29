export function StatusPill({ status }: { status: string }) {
  return <span className={`pill pill-${status.toLowerCase().replaceAll("_", "-")}`}>{status.replaceAll("_", " ")}</span>;
}
