"use client";
import { useState, useRef, useEffect } from "react";
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
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [agentStatuses, setAgentStatuses] = useState<AgentStatus[]>([]);
  const [pendingApproval, setPendingApproval] = useState<any | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // Initialize WebSocket connection
  useWebSocket();

  // Listen for real-time agent updates
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

    window.addEventListener("agent-update", handleAgentUpdate);
    window.addEventListener("approval-request", handleApproval);

    return () => {
      window.removeEventListener("agent-update", handleAgentUpdate);
      window.removeEventListener("approval-request", handleApproval);
    };
  }, []);

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

    try {
      const payload = tripId ? { trip_id: tripId, raw_input: userMessage.content } : { raw_input: userMessage.content };
      await api.post("/api/v1/trips", payload);

      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          content: `Trip planning processing...`,
          timestamp: new Date(),
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "system",
          content: "Failed to send request. Please try again.",
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
      await api.post(`/api/v1/approvals/${pendingApproval.approval_id}/${endpoint}`);
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
