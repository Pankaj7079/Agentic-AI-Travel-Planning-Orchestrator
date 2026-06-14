"use client";
import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { MessageBubble, Message } from "./MessageBubble";
import { VoiceButton } from "./VoiceButton";
import { AgentProgress, AgentStatus } from "./AgentProgress";
import { ApprovalCard } from "./ApprovalCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Send } from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { api } from "@/lib/api";

export function ChatInterface({ tripId }: { tripId?: string }) {
  const router = useRouter();
  const [activeTripId, setActiveTripId] = useState<string | undefined>(tripId);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [agentStatuses, setAgentStatuses] = useState<AgentStatus[]>([]);
  const [pendingApproval, setPendingApproval] = useState<any | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // Sync prop tripId to state
  useEffect(() => {
    if (tripId) {
      setActiveTripId(tripId);
    }
  }, [tripId]);

  // Initialize WebSocket connection
  useWebSocket();

  // Listen for real-time agent updates and completion
  useEffect(() => {
    const handleAgentUpdate = (e: Event) => {
      const customEvent = e as CustomEvent;
      const data = customEvent.detail;
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

      // Add agent message to chat if present
      if (data.message && data.status === "running") {
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

    const handleApproval = (e: Event) => {
      const customEvent = e as CustomEvent;
      setPendingApproval(customEvent.detail.approval);
    };

    const handleTripCompleted = (e: Event) => {
      const customEvent = e as CustomEvent;
      const data = customEvent.detail;
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          content: `Itinerary generated successfully! Redirecting you to your final plan details...`,
          timestamp: new Date(),
        },
      ]);
      setTimeout(() => {
        router.push(`/dashboard/trips/${data.trip_id || activeTripId}`);
      }, 2000);
    };

    window.addEventListener("agent-update", handleAgentUpdate);
    window.addEventListener("approval-request", handleApproval);
    window.addEventListener("trip-completed", handleTripCompleted);

    return () => {
      window.removeEventListener("agent-update", handleAgentUpdate);
      window.removeEventListener("approval-request", handleApproval);
      window.removeEventListener("trip-completed", handleTripCompleted);
    };
  }, [activeTripId, router]);

  // Auto-scroll to bottom when messages update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pendingApproval]);

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
    setAgentStatuses([]); // Reset status bar for new planning runs

    try {
      let currentTripId = activeTripId;

      // 1. Create a trip skeleton if we don't have one active yet
      if (!currentTripId) {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "system",
            content: "Initializing trip planning session...",
            timestamp: new Date(),
          },
        ]);

        const createRes = await api.post<any>("/api/v1/trips", {
          origin: "Delhi",
          destination: "Manali", // Placeholders to satisfy backend validation
          days: 5,
          budget_inr: 15000,
          travelers: 1,
          preferences: {
            interests: [],
            food_preference: "any",
            accommodation_type: "any",
            transport_preference: "any",
            pace: "moderate",
            special_requirements: "",
            language: "en"
          }
        });

        if (createRes && createRes.id) {
          currentTripId = createRes.id;
          setActiveTripId(createRes.id);
        } else {
          throw new Error("Failed to initialize trip record on the server.");
        }
      }

      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          content: "AI travel agents are analyzing your request. Please wait...",
          timestamp: new Date(),
        },
      ]);

      // 2. Call the plan endpoint with raw natural language input
      const planRes = await api.post<any>(`/api/v1/trips/${currentTripId}/plan`, {
        raw_input: userMessage.content,
      });

      if (planRes.status === "awaiting_approval") {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "system",
            content: `Planning paused: approval required for booking. Check details above.`,
            timestamp: new Date(),
          },
        ]);
      }

    } catch (error: any) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          content: `Failed to plan trip: ${error.message || "Please try again."}`,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleVoiceTranscript = (transcript: string) => {
    setInput(transcript);
    // Ideally we would trigger handleSend here, but wrapping it in a setTimeout allows state to settle.
    setTimeout(() => {
      const enterEvent = new KeyboardEvent('keydown', { key: 'Enter' });
      document.getElementById('chat-input')?.dispatchEvent(enterEvent);
    }, 100);
  };

  const handleApprovalResponse = async (approved: boolean) => {
    if (!pendingApproval) return;
    const endpoint = approved ? "approve" : "reject";
    try {
      await api.post(`/api/v1/approvals/${pendingApproval.approval_id}/${endpoint}`, {
        modifications: null
      });
      setPendingApproval(null);
    } catch (error) {
      console.error("Failed to submit approval", error);
    }
  };

  return (
    <div className="flex flex-col h-full bg-background rounded-xl border overflow-hidden shadow-sm">
      {/* Agent Progress */}
      <AgentProgress agents={agentStatuses} />

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 bg-muted/20">
        <div className="max-w-3xl mx-auto flex flex-col justify-end min-h-full">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground opacity-50 my-10">
              <Send className="w-12 h-12 mb-4" />
              <p>Start planning your trip.</p>
              <p className="text-sm">"Plan a 5-day trip to Manali from Delhi under ₹15,000"</p>
            </div>
          )}
          
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {/* Approval Card */}
          {pendingApproval && (
            <ApprovalCard
              approval={pendingApproval}
              onApprove={() => handleApprovalResponse(true)}
              onReject={() => handleApprovalResponse(false)}
            />
          )}
          
          <div ref={messagesEndRef} className="h-4" />
        </div>
      </div>

      {/* Input Area */}
      <div className="p-4 bg-background border-t">
        <div className="max-w-3xl mx-auto flex items-center gap-2">
          <VoiceButton onTranscript={handleVoiceTranscript} />
          <Input
            id="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                handleSend()
              }
            }}
            placeholder="Type your request here..."
            className="flex-1 rounded-full px-4 focus-visible:ring-1"
            disabled={isLoading}
            autoComplete="off"
          />
          <Button 
            onClick={handleSend} 
            disabled={isLoading || !input.trim()} 
            size="icon" 
            className="rounded-full shrink-0 transition-transform active:scale-95"
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
