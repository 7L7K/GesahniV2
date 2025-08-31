export default function SettingsLoading() {
    return (
        <div className="min-h-screen bg-background p-6">
            <div className="max-w-6xl mx-auto">
                <div className="animate-pulse">
                    <div className="h-8 bg-muted rounded mb-6"></div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {Array.from({ length: 6 }).map((_, i) => (
                            <div key={i} className="h-64 bg-muted rounded-lg"></div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
