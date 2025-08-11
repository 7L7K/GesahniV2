"use client";

export function LiveTranscript({ text, onClear }: { text: string; onClear: () => void }) {
    return (
        <div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl p-6 h-full min-h-[400px] lg:min-h-[500px] border border-gray-200/50">
            <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-semibold text-gray-800 flex items-center gap-2">
                    <div className="relative w-2 h-2">
                        <span className="absolute inset-0 w-2 h-2 bg-blue-500 rounded-full animate-pulse" aria-hidden="true"></span>
                        <span className="sr-only">Listening</span>
                    </div>
                    Listening…
                </h3>
                {text && (
                    <button onClick={onClear} className="text-sm text-blue-600 hover:text-blue-700 font-medium">Clear</button>
                )}
            </div>
            <div className="flex-1 overflow-y-auto">
                {text ? (
                    <div className="space-y-3">
                        <p className="text-gray-500 text-sm">You said:</p>
                        {text.split('\n').map((line, i) => (
                            <p key={i} className="text-gray-800 leading-relaxed text-2xl">{line}</p>
                        ))}
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center h-full text-center">
                        <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
                            <span className="text-2xl">🎤</span>
                        </div>
                        <p className="text-gray-500 text-lg mb-2">Press and hold to speak or say “Hey Sweetie”.</p>
                        <p className="text-gray-400 text-sm">Partial captions will appear here in real time.</p>
                    </div>
                )}
            </div>
        </div>
    );
}


