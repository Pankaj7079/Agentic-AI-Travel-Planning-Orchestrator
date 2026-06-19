"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import {
  MessageSquare, X, Send, Bot, User, Sparkles,
  ChevronDown, Map, Compass, Plane, Zap,
  ArrowRight, RotateCcw, Copy, Check, Minimize2
} from "lucide-react";

/* ─── Types ─────────────────────────────────────────────────── */
interface Msg {
  id: string;
  role: "user" | "assistant";
  content: string;
  ts: Date;
  typing?: boolean;
}

/* ─── Knowledge base for offline FAQ fallback ───────────────── */
const KB: Record<string, string> = {
  "plan trip": "To plan a trip with PariKrama, click **New Trip** in the sidebar or dashboard and describe your dream vacation in natural language. Our multi-agent AI will build a full itinerary in 30–90 seconds! 🗺️",
  "multi agent": "PariKrama uses 5 specialized AI agents working in parallel:\n\n🔍 **Research Agent** — destination intel & attractions\n🏨 **Booking Agent** — hotels & transport options\n💰 **Budget Optimizer** — cost breakdown & savings\n📋 **Orchestrator** — understands your request\n🗓️ **Itinerary Finalizer** — day-by-day plan\n\nThey all collaborate on LangGraph to deliver your perfect trip!",
  "voice": "Voice mode lets you speak naturally to your AI travel advisor 🎙️. Click the microphone icon in the chat panel and describe your preferences in any language. PariKrama supports English, Hindi, and Hinglish!",
  "budget": "PariKrama creates a detailed budget breakdown including transport, accommodation, food, activities, and miscellaneous costs — all in ₹ INR. You can set a budget upfront and the agents will optimize within it.",
  "edit itinerary": "You have full control! After planning is complete, you can:\n✏️ Edit any day's activities\n🔄 Swap hotels or transport\n✅ Approve or reject agent suggestions\n📅 Rearrange the schedule\n\nClick **View Trip** on any completed trip to explore and edit.",
  "approval": "PariKrama uses a Human-in-the-Loop (HITL) approach. When an agent makes a significant decision (like booking a hotel that consumes >50% of your budget), it pauses and asks for your **approval** before proceeding. This keeps you in full control! ✅",
  "how long": "Planning typically takes **30–90 seconds** for the full multi-agent pipeline. You'll see live progress updates as each agent completes its task. For complex itineraries (15+ days), it may take up to 2 minutes.",
  "register login": "To get started, click **Sign Up** on the homepage to create a free account. Once registered, you can immediately start planning trips from the dashboard.",
  "pdf export": "Once your trip is complete, open the trip detail page and click **Download PDF** to export a beautifully formatted itinerary you can save or share! 📄",
  "support help": "I'm here to help! You can ask me about planning trips, understanding features, or getting the most out of PariKrama. If you run into technical issues, try refreshing the page or checking that you're logged in.",
};

const findAnswer = (q: string): string | null => {
  const lower = q.toLowerCase();
  for (const [key, val] of Object.entries(KB)) {
    if (key.split(" ").some(k => lower.includes(k))) return val;
  }
  return null;
};

/* ─── Format markdown-ish text ─────────────────────────────── */
const fmt = (text: string) =>
  text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br/>");

/* ─── Quick suggestion chips ───────────────────────────────── */
const CHIPS = [
  { icon: Compass, label: "How to plan a trip?" },
  { icon: Zap, label: "What is multi-agent AI?" },
  { icon: Map, label: "Can I edit my itinerary?" },
  { icon: Plane, label: "How long does planning take?" },
];

/* ─── Main Component ────────────────────────────────────────── */
export function PariKramaChatbot() {
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "👋 Hi! I'm **Krama**, your PariKrama AI assistant!\n\nI can help you understand how PariKrama works, guide you through trip planning, or answer any travel questions. What would you like to know?",
      ts: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [hasNotif, setHasNotif] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open && !minimized) {
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  }, [msgs, open, minimized]);

  useEffect(() => {
    if (open && !minimized) {
      setHasNotif(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open, minimized]);

  const send = useCallback(async (text: string) => {
    const q = text.trim();
    if (!q || loading) return;
    setInput("");
    setLoading(true);

    const userMsg: Msg = { id: `u-${Date.now()}`, role: "user", content: q, ts: new Date() };
    setMsgs(prev => [...prev, userMsg]);

    // typing placeholder
    const tid = `t-${Date.now()}`;
    setMsgs(prev => [...prev, { id: tid, role: "assistant", content: "", ts: new Date(), typing: true }]);

    // natural typing delay
    await new Promise(r => setTimeout(r, 600 + Math.random() * 600));

    // Try local KB first (instant, always works)
    const local = findAnswer(q);
    let answer = local;

    // If no local match, try backend LLM endpoint
    if (!local) {
      try {
        const BASE = typeof window !== "undefined"
          ? `${window.location.protocol}//${window.location.hostname}:8000`
          : "http://localhost:8000";

        const authToken = (() => {
          try { return JSON.parse(localStorage.getItem("auth-storage") || "{}").state?.token || ""; }
          catch { return ""; }
        })();

        const res = await fetch(`${BASE}/api/v1/chat/assistant`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
          },
          body: JSON.stringify({ message: q, context: "parikrama_assistant" }),
          signal: AbortSignal.timeout(12000),
        });

        if (res.ok) {
          const data = await res.json();
          answer = data.response || data.content || data.message;
        }
      } catch {
        // Fallback to generic response
      }
    }

    // Final fallback
    if (!answer) {
      answer = `Great question! 🤔 I can help you with:\n\n• **Planning your first trip** — just ask\n• **Understanding multi-agent AI** — it's fascinating!\n• **Editing your itinerary** — full control\n• **Budget planning** — AI-optimized costs\n• **Approval flow** — you're always in charge\n\nTry tapping one of the quick questions below, or describe what you need in more detail!`;
    }

    setMsgs(prev =>
      prev.map(m => m.id === tid ? { ...m, content: answer!, typing: false } : m)
    );
    setLoading(false);
  }, [loading]);

  const copyMsg = (id: string, content: string) => {
    navigator.clipboard.writeText(content.replace(/<[^>]+>/g, ""));
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  const clearChat = () => {
    setMsgs([{
      id: "welcome-reset",
      role: "assistant",
      content: "👋 Chat cleared! I'm Krama, ready to help with any travel or PariKrama questions.",
      ts: new Date(),
    }]);
  };

  return (
    <>
      {/* ── FAB BUTTON ─────────────────────────────────────────── */}
      {!open && (
        <button
          onClick={() => { setOpen(true); setMinimized(false); }}
          className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-primary flex items-center justify-center shadow-2xl glow-primary-sm animate-glow-pulse hover:scale-110 transition-all group"
          aria-label="Open AI assistant"
        >
          <MessageSquare className="h-6 w-6 text-white group-hover:scale-110 transition-transform" />
          <span className="absolute inset-0 rounded-full bg-primary/40 animate-[ripple_2.2s_ease-out_infinite]" />
          {hasNotif && (
            <span className="absolute -top-1 -right-1 flex h-4 w-4">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-4 w-4 rounded-full bg-emerald-400 items-center justify-center text-[8px] font-bold text-black">1</span>
            </span>
          )}
        </button>
      )}

      {/* ── CHAT WINDOW ────────────────────────────────────────── */}
      {open && (
        <div
          className={`
            fixed bottom-6 right-6 z-50 flex flex-col
            w-[390px] rounded-2xl overflow-hidden
            glass-strong border border-white/10
            shadow-[0_32px_80px_rgba(0,0,0,0.6),0_0_40px_rgba(147,97,253,0.08)]
            transition-all duration-300 anim-scale-in
            ${minimized ? "h-[60px]" : "h-[580px]"}
          `}
        >
          {/* ── HEADER ── */}
          <div className="flex-shrink-0 flex items-center gap-3 px-4 py-3 bg-gradient-to-r from-primary/15 via-indigo-500/8 to-transparent border-b border-white/5">
            {/* Avatar */}
            <div className="relative flex-shrink-0">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 via-indigo-500 to-blue-500 flex items-center justify-center shadow-lg glow-primary-sm">
                <Bot className="h-5 w-5 text-white" />
              </div>
              <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-400 rounded-full border-2 border-background animate-pulse" />
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className="font-semibold text-sm leading-none">Krama AI</p>
                <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-primary/15 text-primary border border-primary/20 leading-none">BETA</span>
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <p className="text-[11px] text-emerald-400 font-medium">Online · Powered by Gemini</p>
              </div>
            </div>

            <div className="flex items-center gap-1 flex-shrink-0">
              <button
                onClick={clearChat}
                title="Clear chat"
                className="p-1.5 rounded-lg hover:bg-white/8 text-muted-foreground hover:text-foreground transition-colors"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setMinimized(!minimized)}
                title={minimized ? "Expand" : "Minimize"}
                className="p-1.5 rounded-lg hover:bg-white/8 text-muted-foreground hover:text-foreground transition-colors"
              >
                {minimized
                  ? <Sparkles className="h-3.5 w-3.5" />
                  : <Minimize2 className="h-3.5 w-3.5" />}
              </button>
              <button
                onClick={() => setOpen(false)}
                className="p-1.5 rounded-lg hover:bg-white/8 text-muted-foreground hover:text-foreground transition-colors"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {!minimized && (
            <>
              {/* ── MESSAGES ── */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4 no-scrollbar">
                {msgs.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex gap-2.5 msg-enter ${msg.role === "user" ? "flex-row-reverse" : ""}`}
                  >
                    {/* Avatar */}
                    <div className={`
                      flex-shrink-0 w-7 h-7 rounded-xl flex items-center justify-center text-white
                      ${msg.role === "assistant"
                        ? "bg-gradient-to-br from-violet-500 to-indigo-600"
                        : "bg-gradient-to-br from-cyan-500 to-blue-600"}
                    `}>
                      {msg.role === "assistant"
                        ? <Bot className="h-3.5 w-3.5" />
                        : <User className="h-3.5 w-3.5" />}
                    </div>

                    {/* Bubble */}
                    <div className="flex flex-col gap-1 max-w-[80%]">
                      <div className={`
                        group relative px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed
                        ${msg.role === "assistant"
                          ? "glass border border-white/6 rounded-tl-sm"
                          : "bg-primary/75 text-white rounded-tr-sm"}
                        ${msg.typing ? "animate-pulse" : ""}
                      `}>
                        {msg.typing ? (
                          <span className="flex items-center gap-1 py-0.5">
                            <span className="typing-dot w-2 h-2 rounded-full bg-primary/70" />
                            <span className="typing-dot w-2 h-2 rounded-full bg-primary/70" />
                            <span className="typing-dot w-2 h-2 rounded-full bg-primary/70" />
                          </span>
                        ) : (
                          <>
                            <div
                              dangerouslySetInnerHTML={{ __html: fmt(msg.content) }}
                              className="whitespace-pre-wrap"
                            />
                            {msg.role === "assistant" && (
                              <button
                                onClick={() => copyMsg(msg.id, msg.content)}
                                className="absolute -top-1 -right-1 opacity-0 group-hover:opacity-100 p-1 rounded-lg bg-secondary/80 border border-white/5 text-muted-foreground hover:text-foreground transition-all"
                                title="Copy"
                              >
                                {copied === msg.id
                                  ? <Check className="h-3 w-3 text-emerald-400" />
                                  : <Copy className="h-3 w-3" />}
                              </button>
                            )}
                          </>
                        )}
                      </div>
                      <p className={`text-[10px] text-muted-foreground px-1 ${msg.role === "user" ? "text-right" : ""}`}>
                        {msg.ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </p>
                    </div>
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>

              {/* ── QUICK CHIPS ── */}
              <div className="px-3 pb-2 flex gap-2 overflow-x-auto no-scrollbar">
                {CHIPS.map(chip => (
                  <button
                    key={chip.label}
                    onClick={() => send(chip.label)}
                    disabled={loading}
                    className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-full glass border border-white/8 hover:border-primary/30 hover:text-primary transition-all whitespace-nowrap disabled:opacity-40"
                  >
                    <chip.icon className="h-3 w-3" />
                    {chip.label}
                  </button>
                ))}
              </div>

              {/* ── INPUT ── */}
              <div className="flex-shrink-0 border-t border-white/5 p-3">
                <form
                  onSubmit={(e) => { e.preventDefault(); send(input); }}
                  className="flex items-center gap-2"
                >
                  <input
                    ref={inputRef}
                    type="text"
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    placeholder="Ask Krama anything..."
                    disabled={loading}
                    className="flex-1 px-4 py-2.5 rounded-xl bg-secondary/40 border border-white/6 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/30 transition-all disabled:opacity-50"
                  />
                  <button
                    type="submit"
                    disabled={!input.trim() || loading}
                    className="flex-shrink-0 w-9 h-9 rounded-xl bg-primary flex items-center justify-center text-white hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all hover:scale-105 glow-primary-sm"
                  >
                    {loading
                      ? <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                      : <Send className="h-3.5 w-3.5" />}
                  </button>
                </form>
                <p className="text-center text-[10px] text-muted-foreground mt-2 opacity-60">
                  Krama AI · Powered by Google Gemini
                </p>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
