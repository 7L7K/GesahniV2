export function logAuth(event: string, data: any = {}) {
  if (process.env.NEXT_PUBLIC_AUTH_DEBUG !== "1") return;
  // eslint-disable-next-line no-console
  console.info("[AUTH]", event, { ...data, ts: new Date().toISOString() });
}

