/** Spec §14.2: the page reached CodeTortoise over plain HTTP from another machine (a TLS proxy in front makes it https:). */
export function plainHttpOnNetwork(protocol: string, hostname: string): boolean {
  if (protocol !== "http:") return false;
  const h = hostname.toLowerCase();
  return !(h === "localhost" || h === "[::1]" || /^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(h));
}
