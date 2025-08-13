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
                <div className="flex items-center gap-3">
                    {text && (
                        <button onClick={onClear} className="text-sm text-blue-600 hover:text-blue-700 font-medium">Clear</button>
                    )}
                    {text && (
                        <button
                            onClick={() => navigator.clipboard?.writeText(text).catch(() => { })}
                            className="text-sm text-gray-600 hover:text-gray-800"
                        >Copy</button>
                    )}
                    {text && (
                        <a
                            download="transcript.txt"
                            href={`data:text/plain;charset=utf-8,${encodeURIComponent(text)}`}
                            className="text-sm text-gray-600 hover:text-gray-800"
                        >Download</a>
                    )}
                </div>
            </div>
            <div className="flex-1 overflow-y-auto" id="transcript-root">
                {text ? (
                    <div className="space-y-3">
                        <p className="text-gray-500 text-sm">You said:</p>
                        {text.split('\n').map((line, i) => (
                            <p key={i} className="leading-relaxed text-2xl text-gray-900">{line}</p>
                        ))}
                        {/* Answer track placeholder: consumer appends answer tokens below when available */}
                        <div id="answer-track" className="mt-6 text-2xl font-medium text-gray-800"></div>
                        <style>{`
                          body.tts-active #answer-track { text-shadow: 0 0 12px rgba(0, 120, 255, 0.35); }
                          body.quiet-hours #transcript-root { filter: saturate(0.75) brightness(0.95); }
                          @media (prefers-reduced-motion: reduce) {
                            body.tts-active #answer-track { text-shadow: none; }
                          }
                        `}</style>
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


