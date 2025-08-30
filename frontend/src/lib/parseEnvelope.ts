export async function parseEnvelope(resp: Response) {
  try {
    const body = await resp.json();
    if (body && (body.code || body.error || body.details)) {
      return body;
    }
    return { code: 'error', message: resp.statusText || 'error', details: { status: resp.status } };
  } catch (e) {
    return { code: 'error', message: resp.statusText || 'error', details: { status: resp.status } };
  }
}

