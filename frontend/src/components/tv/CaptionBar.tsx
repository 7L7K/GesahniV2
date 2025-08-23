"use client";

export function CaptionBar({ text }: { text?: string }) {
    return (
        <div className="fixed bottom-0 left-0 right-0 bg-black/70 text-white text-2xl p-6">
            You said: <span className="font-mono opacity-90">{text ?? ""}</span>
        </div>
    );
}
