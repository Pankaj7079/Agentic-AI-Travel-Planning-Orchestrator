"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  MessageSquare, X, Send, Bot, User, Sparkles,
  ChevronDown, Map, Compass, Plane, Zap,
  RotateCcw, Copy, Check, Minimize2, Globe,
  Wallet, Calendar, Hotel, Search, ArrowRight,
  Train, Star, Info, ExternalLink
} from "lucide-react";

/* ─── Types ─────────────────────────────────────────────────── */
interface Msg {
  id: string;
  role: "user" | "assistant";
  content: string;
  ts: Date;
  typing?: boolean;
  searchedWeb?: boolean;
}

/* ─── Markdown renderer (bold, lists, links, code) ─────────── */
function renderMarkdown(text: string): string {
  return text
    // Bold
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    // Italic
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 rounded bg-white/10 text-primary text-xs font-mono">$1</code>')
    // Unordered list items (- or •)
    .replace(/^[\s]*[-•]\s+(.+)$/gm, '<div class="flex gap-2 my-0.5"><span class="text-primary mt-0.5">•</span><span>$1</span></div>')
    // Numbered list items
    .replace(/^[\s]*(\d+[\.\)]\s+)(.+)$/gm, '<div class="flex gap-2 my-0.5"><span class="text-primary font-medium min-w-[1.2em]">$1</span><span>$2</span></div>')
    // Links
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="text-primary underline hover:text-primary/80 transition-colors inline-flex items-center gap-0.5">$1<svg class="h-3 w-3 inline" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></a></a>')
    // Line breaks
    .replace(/\n/g, "<br/>");
}

/* ─── Suggestion categories ─────────────────────────────────── */
interface SuggestionGroup {
  label: string;
  icon: any;
  color: string;
  items: { q: string; label: string }[];
}

const SUGGESTION_GROUPS: SuggestionGroup[] = [
  {
    label: "Plan a Trip",
    icon: Compass,
    color: "text-violet-400",
    items: [
      { q: "Plan a 5-day trip to Manali from Delhi under ₹15,000", label: "🏔️ Manali trip" },
      { q: "3 days in Goa from Mumbai, budget ₹10,000", label: "🌊 Goa getaway" },
      { q: "Weekend trip to Jaipur from Delhi, ₹8,000", label: "🏯 Jaipur weekend" },
      { q: "Kerala backwater trip for 4 days, ₹20,000", label: "🌴 Kerala tour" },
    ],
  },
  {
    label: "Travel Tips",
    icon: Info,
    color: "text-cyan-400",
    items: [
      { q: "What is the best time to visit Ladakh?", label: "❄️ Ladakh timing" },
      { q: "How to travel cheap in India?", label: "💰 Budget hacks" },
      { q: "Best Indian trains for scenic routes?", label: "🚂 Scenic trains" },
      { q: "What to pack for a Himalayan trek?", label: "🎒 Packing tips" },
    ],
  },
  {
    label: "How PariKrama Works",
    icon: Zap,
    color: "text-amber-400",
    items: [
      { q: "How does the multi-agent AI work?", label: "🤖 Multi-agent AI" },
      { q: "Can I edit my itinerary after planning?", label: "✏️ Edit itinerary" },
      { q: "What is the approval flow?", label: "✅ Approval flow" },
      { q: "How to download trip as PDF?", label: "📄 PDF export" },
    ],
  },
];

/* ─── Quick action buttons ──────────────────────────────────── */
const QUICK_ACTIONS = [
  { icon: Plane, label: "Plan New Trip", action: "plan", href: "/dashboard" },
  { icon: Map, label: "View Dashboard", action: "dashboard", href: "/dashboard" },
];

/* ─── Main Component ────────────────────────────────────────── */
export function PariKramaChatbot() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "👋 Hey there! I'm **Krama**, your AI travel companion!\n\n" +
        "I know everything about Indian travel — from hidden gems in Meghalaya to the best dhabas on the Delhi-Manali highway. I can also help you navigate PariKrama's features.\n\n" +
        "What would you like to explore? Pick a topic below or just type your question!",
      ts: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [hasNotif, setHasNotif] = useState(true);
  const [activeGroup, setActiveGroup] = useState<number | null>(null);
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

  const send = useCallback(
    async (text: string) => {
      const q = text.trim();
      if (!q || loading) return;
      setInput("");
      setActiveGroup(null);
      setLoading(true);

      const userMsg: Msg = { id: `u-${Date.now()}`, role: "user", content: q, ts: new Date() };
      setMsgs((prev) => [...prev, userMsg]);

      const tid = `t-${Date.now()}`;
      setMsgs((prev) => [...prev, { id: tid, role: "assistant", content: "", ts: new Date(), typing: true }]);

      await new Promise((r) => setTimeout(r, 400 + Math.random() * 400));

      let answer = "";
      let searchedWeb = false;

      try {
        const BASE =
          typeof window !== "undefined"
            ? `${window.location.protocol}//${window.location.hostname}:8000`
            : "http://localhost:8000";

        const authToken = (() => {
          try {
            return JSON.parse(localStorage.getItem("auth-storage") || "{}").state?.token || "";
          } catch {
            return "";
          }
        })();

        // Build chat history for context
        const history = msgs
          .filter((m) => !m.typing)
          .slice(-6)
          .map((m) => ({ role: m.role, content: m.content }));

        const res = await fetch(`${BASE}/api/v1/chat/assistant`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
          },
          body: JSON.stringify({
            message: q,
            context: "parikrama_assistant",
            history,
          }),
          signal: AbortSignal.timeout(15000),
        });

        if (res.ok) {
          const data = await res.json();
          answer = data.response || data.content || data.message;
          searchedWeb = data.searched_web || false;
        }
      } catch {
        // Fallback
      }

      if (!answer) {
        answer =
          "I'm having trouble connecting to my knowledge base right now 🤔\n\n" +
          "Here's what I can help with:\n" +
          "• **Trip planning** — describe your dream trip\n" +
          "• **Travel tips** — best time, budget, food, transport\n" +
          "• **PariKrama features** — how to use the platform\n\n" +
          "Try again in a moment, or explore the suggestions below!";
      }

      setMsgs((prev) =>
        prev.map((m) =>
          m.id === tid ? { ...m, content: answer, typing: false, searchedWeb } : m
        )
      );
      setLoading(false);
    },
    [loading, msgs]
  );

  const copyMsg = (id: string, content: string) => {
    navigator.clipboard.writeText(content.replace(/<[^>]+>/g, ""));
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  const clearChat = () => {
    setMsgs([
      {
        id: "welcome-reset",
        role: "assistant",
        content:
          "👋 Fresh start! I'm **Krama**, ready to help with anything travel-related. Where would you like to go?",
        ts: new Date(),
      },
    ]);
  };

  const handleQuickAction = (action: string, href: string) => {
    router.push(href);
    setOpen(false);
  };

  return (
    <>
      {/* ── FAB BUTTON ─────────────────────────────────────────── */}
      {!open && (
        <button
          onClick={() => {
            setOpen(true);
            setMinimized(false);
          }}
          className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center shadow-2xl glow-primary-sm animate-glow-pulse hover:scale-110 transition-all group"
          aria-label="Open Krama AI assistant"
        >
          <MessageSquare className="h-6 w-6 text-white group-hover:scale-110 transition-transform" />
          <span className="absolute inset-0 rounded-full bg-primary/40 animate-[ripple_2.2s_ease-out_infinite]" />
          {hasNotif && (
            <span className="absolute -top-1 -right-1 flex h-4 w-4">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-4 w-4 rounded-full bg-emerald-400 items-center justify-center text-[8px] font-bold text-black">
                1
              </span>
            </span>
          )}
        </button>
      )}

      {/* ── CHAT WINDOW ────────────────────────────────────────── */}
      {open && (
        <div
          className={`
            fixed bottom-6 right-6 z-50 flex flex-col
            w-[400px] max-w-[calc(100vw-2rem)] rounded-2xl overflow-hidden
            glass-strong border border-white/10
            shadow-[0_32px_80px_rgba(0,0,0,0.6),0_0_40px_rgba(147,97,253,0.08)]
            transition-all duration-300 anim-scale-in
            ${minimized ? "h-[60px]" : "h-[600px] max-h-[calc(100vh-4rem)]"}
          `}
        >
          {/* ── HEADER ── */}
          <div className="flex-shrink-0 flex items-center gap-3 px-4 py-3 bg-gradient-to-r from-violet-600/15 via-indigo-500/8 to-transparent border-b border-white/5">
            <div className="relative flex-shrink-0">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 via-indigo-500 to-blue-500 flex items-center justify-center shadow-lg glow-primary-sm">
                <Bot className="h-5 w-5 text-white" />
              </div>
              <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-400 rounded-full border-2 border-background animate-pulse" />
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className="font-semibold text-sm leading-none">Krama AI</p>
                <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-primary/15 text-primary border border-primary/20 leading-none">
                  BETA
                </span>
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <p className="text-[11px] text-emerald-400 font-medium">
                  Online · Gemini + Web Search
                </p>
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
                {minimized ? <Sparkles className="h-3.5 w-3.5" /> : <Minimize2 className="h-3.5 w-3.5" />}
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
                    <div
                      className={`
                      flex-shrink-0 w-7 h-7 rounded-xl flex items-center justify-center text-white
                      ${
                        msg.role === "assistant"
                          ? "bg-gradient-to-br from-violet-500 to-indigo-600"
                          : "bg-gradient-to-br from-cyan-500 to-blue-600"
                      }
                    `}
                    >
                      {msg.role === "assistant" ? <Bot className="h-3.5 w-3.5" /> : <User className="h-3.5 w-3.5" />}
                    </div>

                    <div className="flex flex-col gap-1 max-w-[82%]">
                      <div
                        className={`
                        group relative px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed
                        ${
                          msg.role === "assistant"
                            ? "glass border border-white/6 rounded-tl-sm"
                            : "bg-primary/75 text-white rounded-tr-sm"
                        }
                        ${msg.typing ? "animate-pulse" : ""}
                      `}
                      >
                        {msg.typing ? (
                          <span className="flex items-center gap-1 py-0.5">
                            <span className="typing-dot w-2 h-2 rounded-full bg-primary/70" />
                            <span className="typing-dot w-2 h-2 rounded-full bg-primary/70" />
                            <span className="typing-dot w-2 h-2 rounded-full bg-primary/70" />
                          </span>
                        ) : (
                          <>
                            <div
                              dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
                              className="whitespace-pre-wrap"
                            />
                            {msg.searchedWeb && (
                              <div className="flex items-center gap-1 mt-2 pt-2 border-t border-white/5">
                                <Globe className="h-3 w-3 text-cyan-400" />
                                <span className="text-[10px] text-cyan-400 font-medium">
                                  Searched the web for current info
                                </span>
                              </div>
                            )}
                            {msg.role === "assistant" && (
                              <button
                                onClick={() => copyMsg(msg.id, msg.content)}
                                className="absolute -top-1 -right-1 opacity-0 group-hover:opacity-100 p-1 rounded-lg bg-secondary/80 border border-white/5 text-muted-foreground hover:text-foreground transition-all"
                                title="Copy"
                              >
                                {copied === msg.id ? (
                                  <Check className="h-3 w-3 text-emerald-400" />
                                ) : (
                                  <Copy className="h-3 w-3" />
                                )}
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

              {/* ── SUGGESTION PANELS ── */}
              <div className="px-3 pb-2 space-y-2">
                {/* Quick Action Buttons */}
                <div className="flex gap-2">
                  {QUICK_ACTIONS.map((action) => (
                    <button
                      key={action.action}
                      onClick={() => handleQuickAction(action.action, action.href)}
                      className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-[11px] font-medium rounded-xl glass border border-white/8 hover:border-primary/30 hover:text-primary hover:bg-primary/5 transition-all"
                    >
                      <action.icon className="h-3 w-3" />
                      {action.label}
                    </button>
                  ))}
                </div>

                {/* Category Tabs */}
                <div className="flex gap-1">
                  {SUGGESTION_GROUPS.map((group, idx) => (
                    <button
                      key={group.label}
                      onClick={() => setActiveGroup(activeGroup === idx ? null : idx)}
                      className={`flex items-center gap-1 px-2.5 py-1.5 text-[10px] font-medium rounded-lg transition-all ${
                        activeGroup === idx
                          ? "bg-primary/15 text-primary border border-primary/20"
                          : "bg-white/5 text-muted-foreground border border-white/5 hover:border-white/10"
                      }`}
                    >
                      <group.icon className={`h-3 w-3 ${group.color}`} />
                      <span className="hidden sm:block">{group.label}</span>
                    </button>
                  ))}
                </div>

                {/* Expanded Suggestion Items */}
                {activeGroup !== null && (
                  <div className="flex flex-wrap gap-1.5">
                    {SUGGESTION_GROUPS[activeGroup].items.map((item) => (
                      <button
                        key={item.q}
                        onClick={() => send(item.q)}
                        disabled={loading}
                        className="flex items-center gap-1 px-2.5 py-1.5 text-[10px] font-medium rounded-lg glass border border-white/8 hover:border-primary/30 hover:text-primary transition-all whitespace-nowrap disabled:opacity-40"
                      >
                        {item.label}
                        <ArrowRight className="h-2.5 w-2.5 opacity-50" />
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* ── INPUT ── */}
              <div className="flex-shrink-0 border-t border-white/5 p-3">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    send(input);
                  }}
                  className="flex items-center gap-2"
                >
                  <input
                    ref={inputRef}
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Ask Krama anything — trips, tips, budget..."
                    disabled={loading}
                    className="flex-1 px-4 py-2.5 rounded-xl bg-secondary/40 border border-white/6 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/30 transition-all disabled:opacity-50"
                  />
                  <button
                    type="submit"
                    disabled={!input.trim() || loading}
                    className="flex-shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center text-white hover:from-violet-500 hover:to-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-all hover:scale-105 glow-primary-sm"
                  >
                    {loading ? (
                      <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                    ) : (
                      <Send className="h-3.5 w-3.5" />
                    )}
                  </button>
                </form>
                <p className="text-center text-[10px] text-muted-foreground mt-2 opacity-60">
                  Krama AI · Gemini + Web Search · PariKrama
                </p>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
