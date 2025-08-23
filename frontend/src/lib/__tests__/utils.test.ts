import { sanitizeNextPath } from "@/lib/utils";

describe("sanitizeNextPath", () => {
  it("returns fallback when input is empty", () => {
    expect(sanitizeNextPath("", "/home")).toBe("/home");
    expect(sanitizeNextPath(undefined as any, "/x")).toBe("/x");
    expect(sanitizeNextPath(null as any, "/x")).toBe("/x");
  });

  it("rejects absolute http/https URLs", () => {
    expect(sanitizeNextPath("https://evil.com/a", "/")).toBe("/");
    expect(sanitizeNextPath("http://evil.com/a", "/")).toBe("/");
  });

  it("rejects protocol-relative URLs", () => {
    expect(sanitizeNextPath("//evil.com/a", "/safe")).toBe("/safe");
  });

  it("rejects paths not starting with a slash", () => {
    expect(sanitizeNextPath("foo/bar", "/")).toBe("/");
    expect(sanitizeNextPath("./bar", "/")).toBe("/");
  });

  it("normalizes duplicate slashes", () => {
    expect(sanitizeNextPath("/foo//bar///baz", "/")).toBe("/foo/bar/baz");
  });

  it("passes through a valid relative path", () => {
    expect(sanitizeNextPath("/chat", "/")).toBe("/chat");
    expect(sanitizeNextPath("/settings?tab=profile", "/")).toBe("/settings?tab=profile");
  });
});
