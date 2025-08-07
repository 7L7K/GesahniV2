const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function sendPrompt(
  prompt: string,
  modelOverride: string,
): Promise<string> {
  const url = `${API_URL}/v1/ask`;
  console.debug('API_URL baked into bundle:', API_URL);
  console.debug('Sending request to', url);

  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, model_override: modelOverride })
  });

  console.debug('Received response', res.status, res.statusText);

  const contentType = res.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const body = isJson ? await res.json() : await res.text();

  if (!res.ok) {
    const message =
      typeof body === 'string'
        ? body
        : body.error || body.message || body.detail || JSON.stringify(body);
    throw new Error(`Request failed: ${res.status} - ${message}`);
  }

  if (isJson) {
    return (body as { response: string }).response;
  }

  return body as string;
}
