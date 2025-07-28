const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function sendPrompt(prompt: string): Promise<string> {
  const res = await fetch(`${API_URL}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt })
  });

  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }

  const data: { response: string } = await res.json();
  return data.response;
}
