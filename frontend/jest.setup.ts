import '@testing-library/jest-dom';

// Ensure ReadableStream exists for SSE tests in jsdom
try {
  if (typeof (global as any).ReadableStream === 'undefined') {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { ReadableStream } = require('stream/web');
    ; (global as any).ReadableStream = ReadableStream;
  }
} catch { }


// JSDOM environment stubs for media APIs used by recorder & onboarding previews
// MediaRecorder
class MockMediaRecorder {
  ondataavailable: ((ev: BlobEvent) => void) | null = null;
  private _interval: any;
  static isTypeSupported(): boolean { return true }
  constructor(_stream?: any, _opts?: any) { }
  start(_ms?: number) {
    // Emit empty data periodically
    this._interval = setInterval(() => {
      const blob = new Blob([new Uint8Array([0])], { type: 'application/octet-stream' })
      // @ts-ignore
      this.ondataavailable && this.ondataavailable({ data: blob })
    }, 50)
  }
  stop() { if (this._interval) clearInterval(this._interval) }
  pause() { }
  addEventListener(type: string, cb: () => void) { if (type === 'stop') setTimeout(cb, 0) }
}
// @ts-ignore
if (typeof globalThis.MediaRecorder === 'undefined') {
  // @ts-ignore
  globalThis.MediaRecorder = MockMediaRecorder as any
}

// navigator.mediaDevices.getUserMedia
// @ts-ignore
if (typeof globalThis.navigator === 'undefined') {
  // @ts-ignore
  globalThis.navigator = {} as any
}
// @ts-ignore
if (!globalThis.navigator.mediaDevices) {
  // @ts-ignore
  globalThis.navigator.mediaDevices = {} as any
}
// @ts-ignore
globalThis.navigator.mediaDevices.getUserMedia = jest.fn(async () => ({
  getTracks: () => [],
}))
// @ts-ignore
if (!globalThis.navigator.mediaDevices.enumerateDevices) {
  // @ts-ignore
  globalThis.navigator.mediaDevices.enumerateDevices = jest.fn(async () => []);
}

// AudioContext stub
class MockAnalyser {
  fftSize = 2048
  getByteTimeDomainData(arr: Uint8Array) { arr.fill(128) }
}
class MockAudioContext {
  createMediaStreamSource(_s: any) { return { connect: () => { } } }
  createAnalyser() { return new MockAnalyser() }
}
// @ts-ignore
if (typeof globalThis.AudioContext === 'undefined') {
  // @ts-ignore
  globalThis.AudioContext = MockAudioContext as any
}
// @ts-ignore
if (typeof globalThis.webkitAudioContext === 'undefined') {
  // @ts-ignore
  globalThis.webkitAudioContext = MockAudioContext as any
}

// requestAnimationFrame
// @ts-ignore
if (typeof globalThis.requestAnimationFrame === 'undefined') {
  // @ts-ignore
  globalThis.requestAnimationFrame = (cb: FrameRequestCallback) => setTimeout(() => cb(0), 16) as unknown as number
}

// speechSynthesis stub
// @ts-ignore
if (typeof globalThis.speechSynthesis === 'undefined') {
  // @ts-ignore
  globalThis.speechSynthesis = { cancel: () => { }, speak: () => { } }
}

// TextDecoder polyfill for Node
if (!(global as any).TextDecoder) {
  const { TextDecoder } = require('util');
  (global as any).TextDecoder = TextDecoder;
}

// scrollIntoView stub for JSDOM
if (!(HTMLElement as any).prototype.scrollIntoView) {
  (HTMLElement as any).prototype.scrollIntoView = function () { };
}

// Polyfill crypto.randomUUID for tests
if (!(global as any).crypto) {
  (global as any).crypto = {} as any;
}
if (!(global as any).crypto.randomUUID) {
  (global as any).crypto.randomUUID = () =>
    `uuid-${Math.random().toString(16).slice(2)}-${Date.now()}`;
}

// Polyfill fetch for Node test env
// Basic fetch/Response polyfills for Node without undici
if (!(global as any).fetch) {
  (global as any).fetch = async (url: string, init?: any) => {
    // minimal mock; tests will spyOn and override as needed
    return new (global as any).Response('', { status: 200, headers: { 'content-type': 'text/plain' } });
  };
}
if (!(global as any).Response) {
  class SimpleResponse {
    private _body: any;
    status: number;
    private _headers: Record<string, string>;
    constructor(body?: any, init?: any) {
      this._body = body ?? '';
      this.status = init?.status ?? 200;
      this._headers = init?.headers || {};
    }
    get ok() { return this.status >= 200 && this.status < 300; }
    get headers() {
      const self = this;
      return { get(k: string) { return self._headers[k.toLowerCase()] || self._headers[k] || ''; } } as any;
    }
    async json() { return typeof this._body === 'string' ? JSON.parse(this._body || '{}') : this._body; }
    async text() { return typeof this._body === 'string' ? this._body : JSON.stringify(this._body || ''); }
    get body() {
      // emulate ReadableStream and reader for SSE tests
      const encoder = new TextEncoder();
      const chunk = typeof this._body === 'string' ? this._body : JSON.stringify(this._body || '');
      const data = encoder.encode(chunk);
      return {
        getReader() {
          let done = false;
          return {
            async read() {
              if (done) return { value: undefined, done: true };
              done = true;
              return { value: data, done: false };
            },
          } as any;
        },
        async *[Symbol.asyncIterator]() { yield data; },
      } as any;
    }
    clone() { return new (SimpleResponse as any)(this._body, { status: this.status, headers: this._headers }); }
    arrayBuffer() {
      const encoder = new TextEncoder();
      const chunk = typeof this._body === 'string' ? this._body : JSON.stringify(this._body || '');
      return Promise.resolve(encoder.encode(chunk).buffer);
    }
  }
  (global as any).Response = SimpleResponse as any;
}

// Polyfill TextEncoder for Node
if (!(global as any).TextEncoder) {
  const { TextEncoder } = require('util');
  (global as any).TextEncoder = TextEncoder;
}

// Polyfill ReadableStream for Node
if (!(global as any).ReadableStream) {
  try {
    const { ReadableStream } = require('stream/web');
    (global as any).ReadableStream = ReadableStream;
  } catch { }
}

// Note: react-markdown and remark-gfm are mapped to local stubs via moduleNameMapper



// WebSocket polyfill (force override to avoid Node/builtin differences in tests)
class MockWS {
  readyState = 1;
  onopen?: () => void;
  onmessage?: (e: { data: unknown }) => void;
  onclose?: () => void;
  constructor(_url: string) {
    setTimeout(() => this.onopen && this.onopen(), 0);
    // expose last instance for tests
    ; (global as any).WebSocket.mockInstance = this
  }
  send(_data: unknown) { /* noop */ }
  close() { this.readyState = 3; this.onclose && this.onclose(); }
  addEventListener() { /* noop */ }
}
// @ts-ignore
(global as any).WebSocket = MockWS as any;
