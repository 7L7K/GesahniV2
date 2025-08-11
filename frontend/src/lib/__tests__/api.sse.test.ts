/** @jest-environment jsdom */
import { sendPrompt } from '@/lib/api';

describe('sendPrompt SSE', () => {
  beforeEach(() => {
    (global as any).fetch = jest.fn(async () => {
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('data: a\n\n'));
          controller.enqueue(encoder.encode('data: b\n\n'));
          controller.close();
        },
      });
      return new Response(stream as any, { status: 200, headers: { 'content-type': 'text/event-stream' } } as any) as any;
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


