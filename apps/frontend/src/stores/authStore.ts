import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface User {
  id: string;
  email: string;
  name: string;
  role: "user" | "admin";
  avatar_url?: string | null;
  is_verified?: boolean;
  auth_provider?: string;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  setAuth: (user: User, accessToken: string, refreshToken: string) => void;
  /** Handle the full AuthResponse from backend: { user, tokens: { access_token, refresh_token } } */
  setAuthFromResponse: (response: { user: User; tokens: { access_token: string; refresh_token: string } }) => void;
  updateToken: (accessToken: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,

      setAuth: (user, accessToken, refreshToken) =>
        set({ user, accessToken, refreshToken, isAuthenticated: true }),

      setAuthFromResponse: (response) =>
        set({
          user: response.user,
          accessToken: response.tokens.access_token,
          refreshToken: response.tokens.refresh_token,
          isAuthenticated: true,
        }),

      updateToken: (accessToken) => set({ accessToken }),

      logout: () => {
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
        set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false });
      },
    }),
    { name: "parikrama-auth" }
  )
);
