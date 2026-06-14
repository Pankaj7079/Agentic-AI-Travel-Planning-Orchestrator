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
    const getWsUrl = () => {
      if (typeof window !== "undefined") {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        return `${protocol}//${window.location.hostname}:8000`;
      }
      return process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
    };

    const wsUrl = getWsUrl();
    const ws = new WebSocket(`${wsUrl}/ws/${user.id}?token=${accessToken}`);

    ws.onopen = () => {
      console.log("WebSocket connected");
    };

    ws.onmessage = (event) => {
      try {
        const data: WebSocketMessage = JSON.parse(event.data);
        
        switch (data.type) {
          case "agent_update":
            window.dispatchEvent(new CustomEvent("agent-update", { detail: data }));
            break;
          case "approval_request":
            window.dispatchEvent(new CustomEvent("approval-request", { detail: data }));
            break;
          case "trip_completed":
            window.dispatchEvent(new CustomEvent("trip-completed", { detail: data }));
            break;
          case "notification":
            addNotification(data as any);
            incrementUnread();
            break;
          default:
            console.log("Unknown WS message", data);
        }
      } catch (err) {
        console.error("Failed to parse WS message", err);
      }
    };

    ws.onclose = () => {
      console.log("WebSocket disconnected");
    };

    // Use socketRef to store it, but type it as WebSocket instead of Socket.io
    (socketRef as any).current = ws;

    return () => {
      ws.close();
    };
  }, [accessToken, user, addNotification, incrementUnread]);

  const sendMessage = useCallback((data: any) => {
    const ws = (socketRef as any).current as WebSocket | null;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data));
    }
  }, []);

  return { sendMessage, isConnected: ((socketRef as any).current as WebSocket)?.readyState === WebSocket.OPEN };
}
