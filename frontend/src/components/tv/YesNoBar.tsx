"use client";

export function YesNoBar({ onYes, onNo }: { onYes?: () => void; onNo?: () => void }) {
    return (
        <div className="fixed bottom-0 left-0 right-0 bg-zinc-900 text-white flex justify-center gap-8 p-6 text-3xl">
            <button className="bg-green-700 px-8 py-4 rounded-2xl" onClick={onYes}>Yes</button>
            <button className="bg-red-700 px-8 py-4 rounded-2xl" onClick={onNo}>No</button>
        </div>
    );
}
