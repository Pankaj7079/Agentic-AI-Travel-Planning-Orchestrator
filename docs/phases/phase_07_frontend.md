# Phase 7: Frontend (Next.js 14)

## Overview

Phase 7 builds the **user-facing interface** — a modern, responsive Next.js 14 application with real-time agent updates, voice input, approval cards, and a polished trip itinerary display. The frontend consumes every API built in Phases 1-6.

### Key UI Components
- **Chat Interface** — streaming responses with agent progress indicators
- **Voice Button** — press-and-hold voice input with waveform visualization
- **Approval Cards** — interactive cards for approve/reject actions
- **Itinerary View** — day-by-day expandable itinerary with map
- **Notification Center** — real-time notifications with badge count
- **Admin Dashboard** — system health, user management, analytics

---

## Architecture Decisions

### Decision 1: App Router vs Pages Router
**Why App Router:** Server Components reduce bundle size, streaming SSR gives faster first paint, and nested layouts eliminate redundant re-renders. The App Router is the standard for new Next.js projects.

### Decision 2: Zustand vs Redux
**Why Zustand:** Minimal boilerplate, TypeScript-first, tiny bundle (1KB). We have ~5 stores total — Redux would be massive overhead. Zustand's `create` + `useStore` pattern is cleaner than Redux's action/reducer ceremony.

### Decision 3: Tailwind CSS + Shadcn/ui
**Why this combo:** Tailwind provides utility-first styling with zero runtime CSS. Shadcn/ui gives us pre-built, accessible, customizable components that we copy into our project (not a dependency). Full design control with production-quality defaults.

---

## Folder Structure

```
apps/frontend/src/
├── app/
│   ├── layout.tsx                    # Root layout with providers
│   ├── page.tsx                      # Landing page
│   ├── globals.css                   # Tailwind directives + custom styles
│   ├── (auth)/
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx                # Dashboard shell (sidebar + header)
│   │   ├── page.tsx                  # Dashboard home
│   │   ├── trips/
│   │   │   ├── page.tsx              # Trip list
│   │   │   ├── [id]/page.tsx         # Trip detail + itinerary
│   │   │   └── new/page.tsx          # New trip (chat interface)
│   │   ├── documents/page.tsx        # Knowledge base management
│   │   ├── notifications/page.tsx    # Notification history
│   │   └── settings/page.tsx         # User preferences
│   └── admin/
│       ├── layout.tsx
│       ├── page.tsx                  # Admin overview
│       ├── users/page.tsx            # User management
│       └── analytics/page.tsx        # Cost + usage analytics
│
├── components/
│   ├── ui/                           # Shadcn components
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── dialog.tsx
│   │   ├── input.tsx
│   │   ├── badge.tsx
│   │   ├── skeleton.tsx
│   │   ├── toast.tsx
│   │   └── ...
│   ├── chat/
│   │   ├── ChatInterface.tsx         # Main chat container
│   │   ├── MessageBubble.tsx         # Individual messages
│   │   ├── VoiceButton.tsx           # Voice input with waveform
│   │   ├── AgentProgress.tsx         # Agent status indicators
│   │   └── ApprovalCard.tsx          # Approve/reject cards
│   ├── trip/
│   │   ├── ItineraryView.tsx         # Day-by-day itinerary
│   │   ├── DayCard.tsx               # Single day expansion
│   │   ├── BudgetBreakdown.tsx       # Cost visualization
│   │   └── TripCard.tsx              # Trip list item
│   ├── layout/
│   │   ├── Sidebar.tsx               # Navigation sidebar
│   │   ├── Header.tsx                # Top bar
│   │   └── NotificationBell.tsx      # Notification center
│   └── shared/
│       ├── LoadingSpinner.tsx
│       └── ErrorBoundary.tsx
│
├── hooks/
│   ├── useWebSocket.ts              # WebSocket connection + events
│   ├── useVoice.ts                   # Voice recording + LiveKit
│   ├── useAuth.ts                    # Auth state + token refresh
│   └── useNotifications.ts          # Notification subscription
│
├── stores/
│   ├── authStore.ts                  # User session state
│   ├── tripStore.ts                  # Active trip state
│   └── notificationStore.ts         # Notification state
│
├── lib/
│   ├── api.ts                        # Fetch wrapper with auth
│   ├── socket.ts                     # Socket.io client setup
│   └── utils.ts                      # Formatting utilities
│
└── types/
    ├── trip.ts                       # Trip interfaces
    ├── user.ts                       # User interfaces
    └── api.ts                        # API response types
```

---

## Implementation

### WebSocket Hook

```typescript
// apps/frontend/src/hooks/useWebSocket.ts
"use client";
import { useEffect, useRef, useCallback } from "react";
import { io, Socket } from "socket.io-client";
import { useAuthStore } from "@/stores/authStore";
import { useNotificationStore } from "@/stores/notificationStore";

interface WebSocketMessage {
  type: string;
  [key: string]: any;
}

export function useWebSocket() {
  const socketRef = useRef<Socket | null>(null);
  const { accessToken, user } = useAuthStore();
  const { addNotification, incrementUnread } = useNotificationStore();

  useEffect(() => {
    if (!accessToken || !user) return;

    // connect to backend WebSocket
    const socket = io(process.env.NEXT_PUBLIC_WS_URL!, {
      auth: { token: accessToken },
      transports: ["websocket"],
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
    });

    socket.on("connect", () => {
      console.log("WebSocket connected");
    });

    // handle different message types
    socket.on("agent_update", (data: WebSocketMessage) => {
      // agent progress update — update trip store
      window.dispatchEvent(
        new CustomEvent("agent-update", { detail: data })
      );
    });

    socket.on("approval_request", (data: WebSocketMessage) => {
      // new approval needed — show card
      window.dispatchEvent(
        new CustomEvent("approval-request", { detail: data })
      );
    });

    socket.on("notification", (data: WebSocketMessage) => {
      addNotification(data);
      incrementUnread();
    });

    socket.on("disconnect", () => {
      console.log("WebSocket disconnected");
    });

    socketRef.current = socket;

    return () => {
      socket.disconnect();
    };
  }, [accessToken, user]);

  const sendMessage = useCallback((event: string, data: any) => {
    socketRef.current?.emit(event, data);
  }, []);

  return { sendMessage, isConnected: socketRef.current?.connected ?? false };
}
```

### Chat Interface Component

```tsx
// apps/frontend/src/components/chat/ChatInterface.tsx
"use client";
import { useState, useRef, useEffect } from "react";
import { MessageBubble } from "./MessageBubble";
import { VoiceButton } from "./VoiceButton";
import { AgentProgress } from "./AgentProgress";
import { ApprovalCard } from "./ApprovalCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Send } from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { api } from "@/lib/api";

interface Message {
  id: string;
  role: "user" | "agent" | "system";
  content: string;
  agent?: string;
  timestamp: Date;
}

interface AgentStatus {
  name: string;
  status: "queued" | "running" | "completed" | "failed";
  message: string;
}

export function ChatInterface({ tripId }: { tripId?: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [agentStatuses, setAgentStatuses] = useState<AgentStatus[]>([]);
  const [pendingApproval, setPendingApproval] = useState<any | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { sendMessage } = useWebSocket();

  // listen for real-time agent updates
  useEffect(() => {
    const handleAgentUpdate = (e: CustomEvent) => {
      const data = e.detail;
      setAgentStatuses((prev) => {
        const existing = prev.findIndex((a) => a.name === data.agent);
        if (existing >= 0) {
          const updated = [...prev];
          updated[existing] = {
            name: data.agent,
            status: data.status,
            message: data.message,
          };
          return updated;
        }
        return [...prev, { name: data.agent, status: data.status, message: data.message }];
      });

      // add agent message to chat
      if (data.message) {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "agent",
            content: data.message,
            agent: data.agent,
            timestamp: new Date(),
          },
        ]);
      }
    };

    const handleApproval = (e: CustomEvent) => {
      setPendingApproval(e.detail);
    };

    window.addEventListener("agent-update", handleAgentUpdate as any);
    window.addEventListener("approval-request", handleApproval as any);

    return () => {
      window.removeEventListener("agent-update", handleAgentUpdate as any);
      window.removeEventListener("approval-request", handleApproval as any);
    };
  }, []);

  // auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: input,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await api.post("/api/v1/trips", {
        raw_input: input,
      });

      // trip started — updates will come via WebSocket
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          content: `Trip planning started! I'm working on your itinerary...`,
          timestamp: new Date(),
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          content: "Something went wrong. Please try again.",
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleVoiceTranscript = (transcript: string) => {
    setInput(transcript);
    // auto-send voice input
    handleSend();
  };

  const handleApprovalResponse = async (approved: boolean) => {
    if (!pendingApproval) return;
    const endpoint = approved ? "approve" : "reject";
    await api.post(`/api/v1/approvals/${pendingApproval.approval_id}/${endpoint}`);
    setPendingApproval(null);
  };

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Agent progress bar */}
      {agentStatuses.length > 0 && (
        <AgentProgress agents={agentStatuses} />
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {/* Approval card */}
        {pendingApproval && (
          <ApprovalCard
            approval={pendingApproval}
            onApprove={() => handleApprovalResponse(true)}
            onReject={() => handleApprovalResponse(false)}
          />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="border-t p-4">
        <div className="flex items-center gap-2 max-w-4xl mx-auto">
          <VoiceButton onTranscript={handleVoiceTranscript} />
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Plan a trip... e.g., Delhi to Manali, 5 days, ₹15,000"
            className="flex-1"
            disabled={isLoading}
          />
          <Button onClick={handleSend} disabled={isLoading || !input.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
```

### Auth Store (Zustand)

```typescript
// apps/frontend/src/stores/authStore.ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface User {
  id: string;
  email: string;
  name: string;
  role: "user" | "admin";
  avatar_url?: string;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  setAuth: (user: User, accessToken: string, refreshToken: string) => void;
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
      updateToken: (accessToken) =>
        set({ accessToken }),
      logout: () =>
        set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false }),
    }),
    { name: "parikrama-auth" }
  )
);
```

### API Client

```typescript
// apps/frontend/src/lib/api.ts
import { useAuthStore } from "@/stores/authStore";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiClient {
  private getHeaders(): HeadersInit {
    const { accessToken } = useAuthStore.getState();
    const headers: HeadersInit = { "Content-Type": "application/json" };
    if (accessToken) {
      headers["Authorization"] = `Bearer ${accessToken}`;
    }
    return headers;
  }

  async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers: { ...this.getHeaders(), ...options.headers },
    });

    // handle token expiration
    if (response.status === 401) {
      const refreshed = await this.refreshToken();
      if (refreshed) {
        return this.request(path, options); // retry with new token
      }
      useAuthStore.getState().logout();
      window.location.href = "/login";
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async get<T>(path: string): Promise<T> {
    return this.request(path);
  }

  async post<T>(path: string, body?: any): Promise<T> {
    return this.request(path, {
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
```

### Itinerary View Component

```tsx
// apps/frontend/src/components/trip/ItineraryView.tsx
"use client";
import { useState } from "react";
import { DayCard } from "./DayCard";
import { BudgetBreakdown } from "./BudgetBreakdown";
import { Button } from "@/components/ui/button";
import { Download, Share2, Calendar } from "lucide-react";
import { api } from "@/lib/api";

interface DayPlan {
  day: number;
  title: string;
  activities: { time: string; activity: string; location: string; cost_inr: number }[];
  meals: { time: string; suggestion: string; estimated_cost_inr: number }[];
  tips: string[];
}

interface Props {
  tripId: string;
  itinerary: DayPlan[];
  budgetBreakdown: any;
  summary: string;
}

export function ItineraryView({ tripId, itinerary, budgetBreakdown, summary }: Props) {
  const [expandedDay, setExpandedDay] = useState<number | null>(0);

  const handleDownloadPDF = async () => {
    const blob = await api.request<Blob>(`/api/v1/trips/${tripId}/export/pdf`, {
      headers: { Accept: "application/pdf" },
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `trip-${tripId.slice(0, 8)}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleShareLink = async () => {
    const { share_url } = await api.post<{ share_url: string }>(
      `/api/v1/trips/${tripId}/share`
    );
    await navigator.clipboard.writeText(share_url);
    // show toast
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Summary */}
      <div className="bg-gradient-to-r from-indigo-500 to-purple-600 rounded-2xl p-6 text-white">
        <h2 className="text-2xl font-bold mb-2">Your Trip Itinerary</h2>
        <p className="text-indigo-100">{summary}</p>
      </div>

      {/* Action buttons */}
      <div className="flex gap-3">
        <Button onClick={handleDownloadPDF} variant="outline">
          <Download className="h-4 w-4 mr-2" /> Download PDF
        </Button>
        <Button onClick={handleShareLink} variant="outline">
          <Share2 className="h-4 w-4 mr-2" /> Share Link
        </Button>
        <Button variant="outline">
          <Calendar className="h-4 w-4 mr-2" /> Add to Calendar
        </Button>
      </div>

      {/* Day-by-day itinerary */}
      <div className="space-y-4">
        {itinerary.map((day, index) => (
          <DayCard
            key={day.day}
            day={day}
            isExpanded={expandedDay === index}
            onToggle={() => setExpandedDay(expandedDay === index ? null : index)}
          />
        ))}
      </div>

      {/* Budget breakdown */}
      {budgetBreakdown && (
        <BudgetBreakdown breakdown={budgetBreakdown} />
      )}
    </div>
  );
}
```

---

## Testing Strategy

| Test | Type | What It Validates |
|------|------|-------------------|
| Login flow renders and submits | E2E (Playwright) | Auth works end-to-end |
| Chat sends message and shows response | E2E | Trip planning starts |
| WebSocket receives agent updates | Integration | Real-time updates render |
| Approval card approve/reject | Component | Correct API called |
| Itinerary renders all days | Component | Day cards display properly |
| PDF download works | E2E | File downloads successfully |
| Mobile responsive layout | Visual | Sidebar collapses, chat fills screen |

---

## Definition of Done — Phase 7

- [ ] Login/register pages with form validation
- [ ] Dashboard layout with sidebar navigation
- [ ] Chat interface sends trip requests
- [ ] Agent progress indicators update in real-time via WebSocket
- [ ] Approval cards render and handle approve/reject
- [ ] Trip list page shows all user trips
- [ ] Trip detail page shows full itinerary
- [ ] PDF download button works
- [ ] Notification bell shows unread count
- [ ] Voice button records and sends audio
- [ ] Settings page updates user preferences
- [ ] Admin dashboard (users, analytics, system health)
- [ ] Mobile responsive design
- [ ] Shadcn/ui components styled consistently

---

*Phase 7 is the user's window into the system. Every backend feature from Phases 1-6 becomes visible and interactive here.*
