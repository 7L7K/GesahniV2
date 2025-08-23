/** @jest-environment jsdom */
import { sendPrompt } from '@/lib/api';

describe('sendPrompt SSE', () => {
  beforeEach(() => {
    (global as any).fetch = jest.fn(async () => {
      // Use our setup's SimpleResponse which supports getReader()
      const body = 'data: a\n\ndata: b\n\n';
      return new (global as any).Response(body, { status: 200, headers: { 'content-type': 'text/event-stream' } });
    });
  });

  afterEach(() => { (global as any).fetch = undefined; });

  it('streams SSE data events and calls onToken', async () => {
    const chunks: string[] = [];
    const res = await sendPrompt('x', 'auto', (c) => chunks.push(c));
    expect(chunks.join('')).toBe('ab');
    expect(res).toBe('ab');
  });
});
