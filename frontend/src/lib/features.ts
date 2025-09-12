import { API_ROUTES } from './api/routes';
import { apiFetch } from './api/fetch';

let _cache: any = null;

export async function fetchFeatures(): Promise<{ devices: boolean; transcribe: boolean; ollama: boolean; home_assistant: boolean; qdrant: boolean }> {
    if (_cache) return _cache;
    try {
        const res = await apiFetch(API_ROUTES.STATUS.FEATURES, { method: 'GET', auth: false, dedupe: true });
        if (!res.ok) {
            _cache = { devices: false, transcribe: false, ollama: false, home_assistant: false, qdrant: false };
            return _cache;
        }
        const j = await res.json();
        _cache = {
            devices: Boolean(j.devices),
            transcribe: Boolean(j.transcribe),
            ollama: Boolean(j.ollama),
            home_assistant: Boolean(j.home_assistant),
            qdrant: Boolean(j.qdrant),
        };
        try { sessionStorage.setItem('features', JSON.stringify(_cache)); } catch (e) { /* ignore */ }
        return _cache;
    } catch (e) {
        return { devices: false, transcribe: false, ollama: false, home_assistant: false, qdrant: false };
    }
}

export function clearFeaturesCache() {
    _cache = null;
    try { sessionStorage.removeItem('features'); } catch (e) { /* ignore */ }
}


