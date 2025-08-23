export function emitUiDuck() { window.dispatchEvent(new CustomEvent("ui.duck")); }
export function emitUiRestore() { window.dispatchEvent(new CustomEvent("ui.restore")); }
export function emitVibeChanged(vibe: string) { window.dispatchEvent(new CustomEvent("ui.vibe.changed", { detail: { vibe } } as any)); }
