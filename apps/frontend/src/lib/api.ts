import { useAuthStore } from "@/stores/authStore";

const getBaseUrl = () => {
  if (typeof window !== "undefined") {
    return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
}

const BASE_URL = getBaseUrl()

class ApiClient {
  getBaseUrl(): string {
    return getBaseUrl();
  }

  private getHeaders(): HeadersInit {
    const { accessToken } = useAuthStore.getState();
    const headers: HeadersInit = { "Content-Type": "application/json" };
    if (accessToken) {
      headers["Authorization"] = `Bearer ${accessToken}`;
    }
    return headers;
  }

  async request<T>(path: string, options: RequestInit = {}, _retried = false): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${BASE_URL}${path}`, {
        ...options,
        headers: { ...this.getHeaders(), ...options.headers },
      });
    } catch {
      throw new Error("Cannot connect to the server. Please check your connection or make sure the backend is running.");
    }

    // Handle token expiration — only retry ONCE to avoid infinite loop
    if (response.status === 401 && !_retried) {
      const refreshed = await this.refreshToken();
      if (refreshed) {
        return this.request(path, options, true); // retry once with new token
      }
      // Refresh failed — log out
      useAuthStore.getState().logout();
      throw new Error("Session expired. Please sign in again.");
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    // Attempt to parse JSON; fallback to returning raw text/blob if parsing fails.
    const contentType = response.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      return response.json();
    }
    
    // For PDFs and non-JSON responses
    return response as any;
  }

  async get<T>(path: string, options?: RequestInit): Promise<T> {
    return this.request(path, { ...options });
  }

  async post<T>(path: string, body?: any, options?: RequestInit): Promise<T> {
    return this.request(path, {
      ...options,
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async patch<T>(path: string, body?: any): Promise<T> {
    return this.request(path, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async delete(path: string): Promise<void> {
    await this.request(path, { method: "DELETE" });
  }

  private async refreshToken(): Promise<boolean> {
    const { refreshToken, updateToken } = useAuthStore.getState();
    if (!refreshToken) return false;

    try {
      const response = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (response.ok) {
        const data = await response.json();
        updateToken(data.access_token);
        return true;
      }
    } catch {}

    return false;
  }
}

export const api = new ApiClient();
