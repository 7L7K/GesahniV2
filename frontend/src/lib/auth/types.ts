export type Nullish = null | undefined;

export enum AuthMode {
    Cookie = 'cookie',
    Header = 'header'
}

export type Whoami = {
    is_authenticated: boolean;
    user_id?: string;
    email?: string;
    name?: string;
    picture?: string;
    session_id?: string;
    csrf_token?: string;
    // Add any other fields your whoami endpoint returns
};

export interface AuthStrategy {
    mode: AuthMode;
    getAccessToken(): Promise<string | null>;
    getRefreshToken(): Promise<string | null>;
    setTokens(at: string, rt?: string): Promise<void>;
    clear(): Promise<void>;
    whoami(): Promise<Whoami>;
}

export interface AuthConfig {
    auth_mode?: 'cookie' | 'header';
    cookies_ok?: boolean;
    jwt_secret?: string;
    csrf_enabled?: boolean;
}