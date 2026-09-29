// Presentation only. The cloud gateway enforces access independently.
export function isLocalEntry(hostname: string): boolean {
  return ['localhost', '127.0.0.1', '[::1]', '::1'].includes(hostname)
}
