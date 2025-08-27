import axios, { AxiosError } from "axios";

const api = axios.create({
    baseURL: process.env.NEXT_PUBLIC_API_ORIGIN || "http://localhost:8000",
    withCredentials: true,
});

function shouldForceLogout(err: AxiosError) {
    const res = err.response;
    const url = err.config?.url || "";

    // Only treat 401s from true auth endpoints as fatal
    const isAuthRoute = url.includes("/api/auth/") || url.includes("/auth/");
    const headerCode = res?.headers?.["x-auth-error"] as string | undefined;
    const bodyCode = (res?.data as any)?.error_code as string | undefined;

    const fatalCodes = new Set(["invalid_token", "expired_token", "no_token", "auth_required"]);
    return res?.status === 401 && isAuthRoute && (headerCode ? fatalCodes.has(headerCode) : fatalCodes.has(bodyCode || ""));
}

api.interceptors.response.use(
    r => r,
    err => {
        if (shouldForceLogout(err)) {
            // your logout util here:
            // logoutAndRedirect()
            window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
            return;
        }
        return Promise.reject(err);
    }
);

export default api;
