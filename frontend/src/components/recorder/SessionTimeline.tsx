"use client";

export function SessionTimeline({ meta }: { meta: { status?: string; tags?: string[]; created_at?: string; errors?: string[] } | null }) {
    if (!meta) return null;
    return (
        <div className="mt-4 flex flex-col items-center gap-2 text-sm text-gray-600">
            <span> Status: <strong>{meta.status || '—'}</strong> </span>
            {Array.isArray(meta.tags) && meta.tags.length > 0 && (
                <div className="flex flex-wrap justify-center gap-2">
                    {meta.tags.map((t) => (
                        <span key={t} className="px-2 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">#{t}</span>
                    ))}
                </div>
            )}
            {Array.isArray(meta.errors) && meta.errors.length > 0 && (
                <div className="text-red-600">Last error: {meta.errors[meta.errors.length - 1]}</div>
            )}
        </div>
    );
}
