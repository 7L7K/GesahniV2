import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/apiFetch";

type UserProfile = {
    name?: string;
    email?: string;
    timezone?: string;
    language?: string;
    communication_style?: string;
    interests?: string[];
    occupation?: string;
    home_location?: string;
    preferred_model?: string;
    notification_preferences?: Record<string, unknown>;
    calendar_integration?: boolean;
    gmail_integration?: boolean;
    onboarding_completed?: boolean;
};

export function useProfile() {
    return useQuery({
        queryKey: ["profile"],
        queryFn: () => apiFetch<UserProfile>("/v1/profile"),
    });
}


