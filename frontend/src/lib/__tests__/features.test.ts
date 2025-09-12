import { fetchFeatures, clearFeaturesCache } from '../features';

describe('fetchFeatures', () => {
    const originalFetch = global.fetch;

    beforeEach(() => {
        clearFeaturesCache();
        global.fetch = jest.fn();
    });

    afterEach(() => {
        global.fetch = originalFetch;
    });

    it('fetches features successfully', async () => {
        const mockFeatures = {
            devices: false,
            transcribe: true,
            ollama: false,
            home_assistant: false,
            qdrant: false,
        };

        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: jest.fn().mockResolvedValue(mockFeatures),
        });

        const result = await fetchFeatures();
        expect(result).toEqual(mockFeatures);
        expect(global.fetch).toHaveBeenCalledWith('/v1/status/features', { credentials: 'include' });
    });

    it('returns fallback when fetch fails', async () => {
        (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'));

        const result = await fetchFeatures();
        expect(result).toEqual({
            devices: false,
            transcribe: false,
            ollama: false,
            home_assistant: false,
            qdrant: false,
        });
    });

    it('caches results', async () => {
        const mockFeatures = { devices: true, transcribe: true, ollama: true, home_assistant: true, qdrant: true };

        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: jest.fn().mockResolvedValue(mockFeatures),
        });

        // First call should fetch
        const result1 = await fetchFeatures();
        expect(result1).toEqual(mockFeatures);
        expect(global.fetch).toHaveBeenCalledTimes(1);

        // Second call should use cache
        const result2 = await fetchFeatures();
        expect(result2).toEqual(mockFeatures);
        expect(global.fetch).toHaveBeenCalledTimes(1); // Still only 1 call
    });

    it('clears cache when requested', async () => {
        const mockFeatures = { devices: true, transcribe: true, ollama: true, home_assistant: true, qdrant: true };

        (global.fetch as jest.Mock).mockResolvedValue({
            ok: true,
            json: jest.fn().mockResolvedValue(mockFeatures),
        });

        await fetchFeatures();
        expect(global.fetch).toHaveBeenCalledTimes(1);

        clearFeaturesCache();

        await fetchFeatures();
        expect(global.fetch).toHaveBeenCalledTimes(2); // Cache cleared, should fetch again
    });
});
