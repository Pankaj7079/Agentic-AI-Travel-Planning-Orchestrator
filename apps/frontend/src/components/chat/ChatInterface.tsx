"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import {
  Send, Sparkles, Map, Compass, Bot, User, AlertCircle,
  CheckCircle, Clock, Loader2, Plane, Hotel, DollarSign,
  Calendar, RotateCcw, ChevronRight, ChevronDown, ChevronUp,
  Star, Train, Bus, Plane as PlaneIcon, Wallet, Info
} from "lucide-react";

interface Message {
  id: string;
  role: "user" | "assistant" | "system" | "agent";
  content: string;
  timestamp: Date;
  agent?: string;
  isError?: boolean;
}

interface AgentStatus {
  name: string;
  label: string;
  description: string;
  status: "pending" | "running" | "completed" | "failed";
  icon: any;
  details: string;
}

interface HotelOption {
  name: string;
  location: string;
  price_per_night_inr: number;
  total_cost_inr: number;
  rating: number;
  type?: string;
  amenities: string[];
}

interface TransportOption {
  type?: string;
  operator: string;
  origin: string;
  destination: string;
  price_inr: number;
  duration_hours: number;
  departure_time: string;
  class: string;
}

const AGENT_DEFS: AgentStatus[] = [
  { name: "orchestrator", label: "Parsing Request", description: "Understanding your travel preferences", status: "pending", icon: Compass, details: "" },
  { name: "research", label: "Researching Destination", description: "Gathering weather, places & travel info", status: "pending", icon: Map, details: "" },
  { name: "booking", label: "Finding Options", description: "Searching hotels & transport options", status: "pending", icon: Hotel, details: "" },
  { name: "budget_optimizer", label: "Optimizing Budget", description: "Calculating cost breakdown", status: "pending", icon: DollarSign, details: "" },
  { name: "itinerary_finalizer", label: "Crafting Itinerary", description: "Creating your day-by-day plan", status: "pending", icon: Calendar, details: "" },
];

const WELCOME_SUGGESTIONS = [
  "Plan a trip to Manali from Delhi under ₹15,000",
  "Budget trip to Goa for 3 days from Mumbai",
  "Explore Rajasthan for a week, couple trip, ₹40,000",
  "Quick weekend trip to Coorg from Bangalore",
];

function extractTripHints(text: string): {
  origin: string; destination: string; days: number; budget_inr: number;
} {
  const t = text.toLowerCase();
  const daysMatch = t.match(/(\d+)[\s-]?(day|days|din|d\b)/);
  const days = daysMatch ? Math.min(30, Math.max(1, parseInt(daysMatch[1]))) : 7;

  let budget = 15000;
  const budgetMatch = t.match(/(?:rs\.?|₹|inr)?\s*(\d[\d,]*)\s*(?:k|000|hazar|lakh)?/i);
  if (budgetMatch) {
    let raw = parseInt(budgetMatch[1].replace(/,/g, ""));
    if (t.includes("lakh") && raw < 100) raw *= 100000;
    else if ((t.includes("k") || t.includes("hazar")) && raw < 1000) raw *= 1000;
    if (raw >= 500) budget = raw;
  }

  const fromToMatch =
    t.match(/from\s+([a-z\s]+?)\s+to\s+([a-z\s]+?)(?:\s|$|,|under|with|for)/) ||
    t.match(/([a-z\s]+?)\s+(?:to|se)\s+([a-z\s]+?)(?:\s|$|,|under|with|for)/);

  let origin = "Delhi";
  let destination = "Manali";

  if (fromToMatch) {
    origin = fromToMatch[1].trim();
    destination = fromToMatch[2].trim();
  } else {
    const toFromMatch = t.match(/trip\s+to\s+([a-z\s]+?)(?:\s+from\s+([a-z\s]+?))?(?:\s|$|,|under|with)/);
    if (toFromMatch) {
      destination = toFromMatch[1].trim();
      if (toFromMatch[2]) origin = toFromMatch[2].trim();
    }
  }

  const cap = (s: string) =>
    s.split(" ").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");

  return {
    origin: cap(origin.slice(0, 50)),
    destination: cap(destination.slice(0, 50)),
    days,
    budget_inr: budget,
  };
}

export function ChatInterface({ tripId }: { tripId?: string }) {
  const router = useRouter();
  const [activeTripId, setActiveTripId] = useState<string | undefined>(tripId);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [agents, setAgents] = useState<AgentStatus[]>([...AGENT_DEFS]);
  const [showAgents, setShowAgents] = useState(false);
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);
  const [pendingApproval, setPendingApproval] = useState<any>(null);
  const [planningDone, setPlanningDone] = useState(false);
  const [hotelOptions, setHotelOptions] = useState<HotelOption[]>([]);
  const [transportOptions, setTransportOptions] = useState<TransportOption[]>([]);
  const [selectedHotel, setSelectedHotel] = useState<number | null>(null);
  const [selectedTransport, setSelectedTransport] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const pollIntervalRef = useRef<number>(3000);

  useEffect(() => {
    if (tripId) setActiveTripId(tripId);
  }, [tripId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pendingApproval, hotelOptions, transportOptions]);

  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, []);

  const addMessage = useCallback(
    (role: Message["role"], content: string, isError = false, agent?: string) => {
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role, content, timestamp: new Date(), isError, agent,
      }]);
    },
    []
  );

  const startPolling = useCallback((tid: string) => {
    if (pollingRef.current) clearInterval(pollingRef.current);
    pollIntervalRef.current = 3000;
    let elapsed = 0;

    const tick = async () => {
      elapsed += pollIntervalRef.current;
      if (elapsed > 90000) pollIntervalRef.current = 10000;
      else if (elapsed > 60000) pollIntervalRef.current = 8000;
      else if (elapsed > 30000) pollIntervalRef.current = 5000;

      try {
        const status = await api.get<any>(`/api/v1/trips/${tid}/status`);

        // Update agent progress with details
        if (status.current_agent) {
          setAgents(prev => prev.map(a => {
            const idx = AGENT_DEFS.findIndex(d => d.name === a.name);
            const currentIdx = AGENT_DEFS.findIndex(d => d.name === status.current_agent);
            if (idx < currentIdx) return { ...a, status: "completed" as const };
            if (idx === currentIdx) return { ...a, status: "running" as const, details: status.message || a.details };
            return a;
          }));
        }

        // Fetch trip details for hotel/transport options
        if (status.status === "completed" || status.has_result) {
          try {
            const tripDetail = await api.get<any>(`/api/v1/trips/${tid}`);
            if (tripDetail?.result) {
              const result = tripDetail.result;
              if (result.hotel_options?.length) setHotelOptions(result.hotel_options);
              if (result.transport_options?.length) setTransportOptions(result.transport_options);
            }
          } catch {}
        }

        if (status.status === "awaiting_approval") {
          if (pollingRef.current) clearInterval(pollingRef.current);
          pollingRef.current = null;
          setIsLoading(false);

          if (status.approval_id) {
            try {
              const approval = await api.get<any>(`/api/v1/approvals/${status.approval_id}`);
              setPendingApproval(approval);
              addMessage("assistant", `⚠️ **Approval needed!** ${approval.description || "The agents need your confirmation before proceeding."}`);
            } catch {
              const approvals = await api.get<any>("/api/v1/approvals").catch(() => []);
              const pending = Array.isArray(approvals) ? approvals.filter((a: any) => a.status === "pending") : [];
              if (pending.length > 0) {
                setPendingApproval(pending[0]);
                addMessage("assistant", `⚠️ **Approval needed!** ${pending[0].description || "Please review and approve to continue."}`);
              }
            }
          }
        } else if (status.is_complete) {
          if (pollingRef.current) clearInterval(pollingRef.current);
          pollingRef.current = null;

          if (status.status === "completed") {
            setAgents(prev => prev.map(a => ({ ...a, status: "completed" as const })));
            setPlanningDone(true);
            addMessage("assistant", `🎉 **Your trip plan is ready!** I've crafted a detailed day-by-day itinerary. You can view options below or click "View Full Itinerary" for the complete plan.`);
          } else if (status.status === "failed") {
            setAgents(prev => prev.map(a => ({ ...a, status: a.status === "running" ? "failed" as const : a.status })));
            const errorMsg = status.error || "Planning encountered an issue. Please try again with more details.";
            addMessage("assistant", `❌ ${errorMsg}`, true);
          } else if (status.status === "cancelled") {
            addMessage("system", "Trip planning was cancelled.");
          }
          setIsLoading(false);
        }

        if (pollingRef.current !== null) {
          pollingRef.current = setTimeout(tick, pollIntervalRef.current) as any;
        }
      } catch {
        if (pollingRef.current !== null) {
          pollingRef.current = setTimeout(tick, pollIntervalRef.current) as any;
        }
      }
    };

    pollingRef.current = setTimeout(tick, pollIntervalRef.current) as any;
  }, [addMessage]);

  const resetAgents = () => setAgents(AGENT_DEFS.map(a => ({ ...a, status: "pending", details: "" })));

  const handleSend = async (text?: string) => {
    const query = (text || input).trim();
    if (!query || isLoading) return;

    setInput("");
    setIsLoading(true);
    setShowAgents(true);
    setPlanningDone(false);
    setPendingApproval(null);
    setHotelOptions([]);
    setTransportOptions([]);
    setSelectedHotel(null);
    setSelectedTransport(null);
    resetAgents();
    addMessage("user", query);

    const hints = extractTripHints(query);

    let currentTripId = activeTripId;
    if (!currentTripId) {
      addMessage("system", "🚀 Initializing trip planning session...");
      try {
        const createRes = await api.post<any>("/api/v1/trips", {
          origin: hints.origin,
          destination: hints.destination,
          days: hints.days,
          budget_inr: hints.budget_inr,
          travelers: 1,
          preferences: {
            interests: [],
            food_preference: "any",
            accommodation_type: "any",
            transport_preference: "any",
            pace: "moderate",
            special_requirements: "",
            language: "en",
          },
        });
        if (!createRes?.id) throw new Error("No trip ID returned");
        currentTripId = createRes.id;
        setActiveTripId(createRes.id);
      } catch (err: any) {
        addMessage("assistant", `Failed to start planning: ${err.message}. Please make sure you are logged in.`, true);
        setIsLoading(false);
        return;
      }
    }

    setAgents(prev => prev.map((a, i) => i === 0 ? { ...a, status: "running" } : a));
    addMessage("system", "🤖 AI agents are analyzing your request...");

    try {
      await api.post<any>(`/api/v1/trips/${currentTripId}/plan`, { raw_input: query });
      addMessage("system", "🤖 AI agents are now working on your trip. Click each agent below to see what it's doing...");
      startPolling(currentTripId!);
    } catch (err: any) {
      addMessage("assistant", `⚠️ ${err.message || "Failed to start planning. Please check you are logged in and try again."}`, true);
      setIsLoading(false);
      setShowAgents(false);
    }
  };

  const handleApproval = async (approved: boolean) => {
    if (!pendingApproval) return;
    const endpoint = approved ? "approve" : "reject";
    try {
      await api.post(`/api/v1/approvals/${pendingApproval.id || pendingApproval.approval_id}/${endpoint}`, {
        modifications: null,
      });
      setPendingApproval(null);
      if (approved) {
        addMessage("system", "✅ Approval confirmed! Finalizing your itinerary...");
        setIsLoading(true);
        if (activeTripId) startPolling(activeTripId);
      } else {
        addMessage("assistant", "Understood, I've cancelled that option. Would you like me to find alternative options within a lower budget?");
      }
    } catch (err: any) {
      addMessage("assistant", `Failed to submit decision: ${err.message}`, true);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const startNew = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    setActiveTripId(undefined);
    setMessages([]);
    setAgents(AGENT_DEFS.map(a => ({ ...a, status: "pending", details: "" })));
    setShowAgents(false);
    setExpandedAgent(null);
    setPlanningDone(false);
    setPendingApproval(null);
    setHotelOptions([]);
    setTransportOptions([]);
    setSelectedHotel(null);
    setSelectedTransport(null);
    setIsLoading(false);
  };

  const formatContent = (text: string) =>
    text
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br/>");

  const getHotelIcon = (type?: string) => {
    if (!type) return "🏨";
    if (type.includes("hostel") || type.includes("budget")) return "🏠";
    if (type.includes("3_star") || type.includes("3star")) return "⭐";
    if (type.includes("4_star") || type.includes("4star") || type.includes("premium")) return "🌟";
    return "🏨";
  };

  const getTransportIcon = (type?: string) => {
    if (!type) return <Bus className="h-4 w-4" />;
    if (type === "bus") return <Bus className="h-4 w-4" />;
    if (type === "train") return <Train className="h-4 w-4" />;
    if (type === "flight") return <PlaneIcon className="h-4 w-4" />;
    return <Bus className="h-4 w-4" />;
  };

  return (
    <div className="flex flex-col h-full min-h-[600px] glass rounded-2xl border border-white/10 overflow-hidden">

      {/* ── Header ── */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-white/5 bg-gradient-to-r from-primary/10 to-indigo-500/5">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-lg">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            {isLoading && (
              <span className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 bg-emerald-400 rounded-full border-2 border-background animate-pulse" />
            )}
          </div>
          <div>
            <p className="font-semibold text-sm">PariKrama AI Travel Planner</p>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className={`w-1.5 h-1.5 rounded-full ${isLoading ? "bg-amber-400 animate-pulse" : "bg-emerald-400"}`} />
              {isLoading ? "Agents working..." : "Ready to plan your trip"}
            </div>
          </div>
        </div>
        {(messages.length > 0 || showAgents) && (
          <button
            onClick={startNew}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-white/5 transition-all"
          >
            <RotateCcw className="h-3.5 w-3.5" /> New Trip
          </button>
        )}
      </div>

      {/* ── Expandable Agent Progress ── */}
      {showAgents && (
        <div className="border-b border-white/5 bg-black/20">
          {/* Agent pills - horizontal scroll */}
          <div className="px-5 py-3 flex items-center gap-1 overflow-x-auto no-scrollbar">
            {agents.map((agent, idx) => {
              const Icon = agent.icon;
              const isExpanded = expandedAgent === agent.name;
              return (
                <div key={agent.name} className="flex items-center gap-1 flex-shrink-0">
                  <button
                    onClick={() => setExpandedAgent(isExpanded ? null : agent.name)}
                    className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer hover:opacity-80 ${
                      agent.status === "completed" ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20" :
                      agent.status === "running" ? "bg-primary/15 text-primary border border-primary/20 animate-pulse" :
                      agent.status === "failed" ? "bg-rose-500/15 text-rose-400 border border-rose-500/20" :
                      "bg-white/5 text-muted-foreground border border-white/5"
                    }`}
                  >
                    {agent.status === "running" ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : agent.status === "completed" ? (
                      <CheckCircle className="h-3 w-3" />
                    ) : agent.status === "failed" ? (
                      <AlertCircle className="h-3 w-3" />
                    ) : (
                      <Icon className="h-3 w-3" />
                    )}
                    <span className="hidden sm:block">{agent.label}</span>
                    {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                  </button>
                  {idx < agents.length - 1 && (
                    <ChevronRight className="h-3 w-3 text-muted-foreground/30 flex-shrink-0" />
                  )}
                </div>
              );
            })}
          </div>

          {/* Expanded agent details */}
          {expandedAgent && (
            <div className="px-5 pb-3 pt-1">
              {agents.filter(a => a.name === expandedAgent).map(agent => (
                <div key={agent.name} className="bg-white/5 rounded-xl p-4 border border-white/5 space-y-2">
                  <div className="flex items-center gap-2">
                    <agent.icon className="h-4 w-4 text-primary" />
                    <span className="font-medium text-sm">{agent.label}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      agent.status === "completed" ? "bg-emerald-500/15 text-emerald-400" :
                      agent.status === "running" ? "bg-primary/15 text-primary" :
                      agent.status === "failed" ? "bg-rose-500/15 text-rose-400" :
                      "bg-white/5 text-muted-foreground"
                    }`}>
                      {agent.status === "running" ? "In Progress" : agent.status === "completed" ? "Done" : agent.status === "failed" ? "Failed" : "Queued"}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">{agent.description}</p>
                  {agent.details && (
                    <div className="text-xs text-muted-foreground bg-black/20 rounded-lg p-2 mt-2">
                      <Info className="h-3 w-3 inline mr-1" />
                      {agent.details}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center py-12">
            <div className="w-20 h-20 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-6 animate-float">
              <Plane className="h-10 w-10 text-primary/60" />
            </div>
            <h2 className="text-xl font-bold mb-2">Where would you like to go?</h2>
            <p className="text-muted-foreground text-sm max-w-sm mb-8 leading-relaxed">
              Describe your dream trip in plain language — our AI agents will craft a complete, personalized itinerary for you.
            </p>
            <div className="grid grid-cols-1 gap-2 w-full max-w-md">
              {WELCOME_SUGGESTIONS.map(suggestion => (
                <button
                  key={suggestion}
                  onClick={() => handleSend(suggestion)}
                  className="text-left px-4 py-3 rounded-xl glass border border-white/5 hover:border-primary/30 hover:bg-primary/5 transition-all text-sm text-muted-foreground hover:text-foreground group"
                >
                  <span className="text-primary/60 group-hover:text-primary mr-2">→</span>
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map(msg => (
          <div
            key={msg.id}
            className={`flex gap-3 msg-enter ${msg.role === "user" ? "flex-row-reverse" : ""}`}
          >
            {(msg.role === "assistant" || msg.role === "agent") && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center">
                <Bot className="h-4 w-4 text-white" />
              </div>
            )}
            {msg.role === "user" && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center">
                <User className="h-4 w-4 text-white" />
              </div>
            )}
            {msg.role === "system" && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
                <Compass className="h-3.5 w-3.5 text-muted-foreground" />
              </div>
            )}

            <div className={`max-w-[80%] ${msg.role === "user" ? "items-end" : "items-start"} flex flex-col gap-1`}>
              <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-primary text-white rounded-tr-sm"
                  : msg.role === "system"
                  ? "bg-white/5 border border-white/5 text-muted-foreground rounded-tl-sm text-xs py-2"
                  : msg.isError
                  ? "bg-rose-500/10 border border-rose-500/20 text-rose-300 rounded-tl-sm"
                  : "glass border border-white/5 rounded-tl-sm"
              }`}>
                <div
                  dangerouslySetInnerHTML={{ __html: formatContent(msg.content) }}
                  className="whitespace-pre-wrap"
                />
              </div>
              <span className="text-[10px] text-muted-foreground px-1">
                {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
            </div>
          </div>
        ))}

        {/* Loading Indicator */}
        {isLoading && messages.length > 0 && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center">
              <Bot className="h-4 w-4 text-white" />
            </div>
            <div className="glass border border-white/5 rounded-2xl rounded-tl-sm px-4 py-3 flex gap-1.5 items-center">
              <span className="typing-dot w-2 h-2 rounded-full bg-primary/60" />
              <span className="typing-dot w-2 h-2 rounded-full bg-primary/60" />
              <span className="typing-dot w-2 h-2 rounded-full bg-primary/60" />
            </div>
          </div>
        )}

        {/* Hotel Options Selection */}
        {hotelOptions.length > 0 && planningDone && (
          <div className="glass border border-white/5 rounded-2xl p-5 space-y-4 msg-enter">
            <div className="flex items-center gap-2">
              <Hotel className="h-5 w-5 text-primary" />
              <h3 className="font-semibold text-sm">Select Your Hotel</h3>
            </div>
            <div className="grid grid-cols-1 gap-3">
              {hotelOptions.slice(0, 3).map((hotel, idx) => (
                <button
                  key={idx}
                  onClick={() => setSelectedHotel(idx)}
                  className={`text-left p-4 rounded-xl border transition-all ${
                    selectedHotel === idx
                      ? "bg-primary/10 border-primary/30 ring-1 ring-primary/20"
                      : "bg-white/5 border-white/5 hover:border-white/10"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{getHotelIcon(hotel.type)}</span>
                        <span className="font-medium text-sm">{hotel.name}</span>
                        {selectedHotel === idx && <CheckCircle className="h-4 w-4 text-primary" />}
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">{hotel.location}</p>
                      <div className="flex items-center gap-3 mt-2">
                        <span className="flex items-center gap-1 text-xs">
                          <Star className="h-3 w-3 text-amber-400" />
                          {hotel.rating}
                        </span>
                        <span className="text-xs text-muted-foreground capitalize">{(hotel.type || "Hotel").replace("_", " ")}</span>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-2">
                        {hotel.amenities?.slice(0, 4).map((a: string, i: number) => (
                          <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-muted-foreground">{a}</span>
                        ))}
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-bold text-sm">₹{hotel.price_per_night_inr.toLocaleString()}</p>
                      <p className="text-[10px] text-muted-foreground">per night</p>
                      <p className="text-xs text-muted-foreground mt-1">₹{hotel.total_cost_inr?.toLocaleString() || (hotel.price_per_night_inr * 7).toLocaleString()} total</p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Transport Options Selection */}
        {transportOptions.length > 0 && planningDone && (
          <div className="glass border border-white/5 rounded-2xl p-5 space-y-4 msg-enter">
            <div className="flex items-center gap-2">
              <Train className="h-5 w-5 text-primary" />
              <h3 className="font-semibold text-sm">Select Your Transport</h3>
            </div>
            <div className="grid grid-cols-1 gap-3">
              {transportOptions.slice(0, 3).map((transport, idx) => (
                <button
                  key={idx}
                  onClick={() => setSelectedTransport(idx)}
                  className={`text-left p-4 rounded-xl border transition-all ${
                    selectedTransport === idx
                      ? "bg-primary/10 border-primary/30 ring-1 ring-primary/20"
                      : "bg-white/5 border-white/5 hover:border-white/10"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        {getTransportIcon(transport.type)}
                         <span className="font-medium text-sm capitalize">{transport.type || "Transport"}</span>
                        <span className="text-xs text-muted-foreground">• {transport.operator}</span>
                        {selectedTransport === idx && <CheckCircle className="h-4 w-4 text-primary" />}
                      </div>
                      <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                        <span>🕐 {transport.duration_hours}h</span>
                        <span>📍 {transport.departure_time}</span>
                        <span className="capitalize">💺 {transport.class}</span>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-bold text-sm">₹{transport.price_inr.toLocaleString()}</p>
                      <p className="text-[10px] text-muted-foreground">one-way</p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Approval Card */}
        {pendingApproval && (
          <div className="glass border border-amber-500/20 rounded-2xl p-5 space-y-4 msg-enter">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-amber-500/10">
                <AlertCircle className="h-5 w-5 text-amber-400" />
              </div>
              <div>
                <p className="font-semibold text-amber-300">{pendingApproval.title || "Approval Required"}</p>
                <p className="text-sm text-muted-foreground mt-1">{pendingApproval.description}</p>
              </div>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => handleApproval(true)}
                className="flex-1 py-2.5 rounded-xl bg-emerald-500/15 border border-emerald-500/20 text-emerald-400 text-sm font-semibold hover:bg-emerald-500/25 transition-all"
              >
                ✓ Approve & Continue
              </button>
              <button
                onClick={() => handleApproval(false)}
                className="flex-1 py-2.5 rounded-xl glass border border-white/10 text-muted-foreground text-sm font-semibold hover:border-rose-500/30 hover:text-rose-400 transition-all"
              >
                ✗ Find Alternative
              </button>
            </div>
          </div>
        )}

        {/* View Itinerary CTA */}
        {planningDone && activeTripId && (
          <div className="flex justify-center msg-enter">
            <button
              onClick={() => router.push(`/dashboard/trips/${activeTripId}`)}
              className="flex items-center gap-2 px-6 py-3 rounded-xl bg-primary text-white font-semibold hover:bg-primary/90 glow-primary-sm hover:glow-primary transition-all hover:scale-105"
            >
              <Map className="h-4 w-4" /> View Full Itinerary
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* ── Input Area ── */}
      <div className="p-4 border-t border-white/5 bg-black/10">
        <div className="flex items-end gap-2">
          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder='Describe your trip... e.g. "5 days in Manali from Delhi under ₹15,000"'
              disabled={isLoading}
              rows={1}
              className="w-full px-4 py-3 pr-12 rounded-xl bg-secondary/50 border border-border/50 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all resize-none min-h-[46px] max-h-32 disabled:opacity-50"
              style={{ height: "auto" }}
              onInput={e => {
                const el = e.target as HTMLTextAreaElement;
                el.style.height = "auto";
                el.style.height = Math.min(el.scrollHeight, 128) + "px";
              }}
            />
          </div>
          <button
            onClick={() => handleSend()}
            disabled={isLoading || !input.trim()}
            className="flex-shrink-0 p-3 rounded-xl bg-primary text-white hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all hover:scale-105 glow-primary-sm"
          >
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <Send className="h-5 w-5" />
            )}
          </button>
        </div>
        <p className="text-[11px] text-muted-foreground mt-2 text-center">
          Press <kbd className="px-1 py-0.5 rounded bg-white/5 text-[10px] font-mono">Enter</kbd> to send · <kbd className="px-1 py-0.5 rounded bg-white/5 text-[10px] font-mono">Shift+Enter</kbd> for new line
        </p>
      </div>
    </div>
  );
}
