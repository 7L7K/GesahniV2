const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function sendPrompt(
  prompt: string,
  modelOverride: string,
  onToken?: (chunk: string) => void,
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

  if (!res.ok) {
    const body = isJson ? await res.json() : await res.text();
    const message =
      typeof body === 'string'
        ? body
        : body.error || body.message || body.detail || JSON.stringify(body);
    throw new Error(`Request failed: ${res.status} - ${message}`);
  }

  if (isJson) {
    const body = await res.json();
    return (body as { response: string }).response;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error('Response body missing');
  }

  const decoder = new TextDecoder();
  let result = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    if (chunk.startsWith('[error')) {
      throw new Error(chunk.replace(/\[error:?|\]$/g, ''));
    }
    result += chunk;
    onToken?.(chunk);
  }

  return result;
}
