"use client";
import { useState, useRef, useEffect } from "react";
import { MessageSquare, X, Send, Bot, User, Sparkles, ChevronDown } from "lucide-react";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

const FAQS = [
  "How do I plan a trip?",
  "What is multi-agent planning?",
  "How does voice mode work?",
  "Can I edit my itinerary?",
];

const BOT_RESPONSES: Record<string, string> = {
  "how do i plan a trip": "Planning a trip with PariKrama is simple! Just go to **Dashboard → New Trip** and describe your dream vacation in plain language. Our AI agents will instantly start building a complete day-by-day itinerary for you! 🗺️",
  "what is multi-agent planning": "PariKrama uses a swarm of specialized AI agents that work simultaneously:\n\n🔍 **Research Agent** — finds top destinations & attractions\n✈️ **Logistics Agent** — handles flights & transport\n💰 **Budget Agent** — optimizes costs\n🏨 **Accommodation Agent** — picks the best stays\n\nThey all collaborate to build your perfect trip in seconds!",
  "how does voice mode work": "Voice mode lets you talk naturally to your AI travel advisor! 🎙️\n\nSimply click the microphone icon in the chat, speak your preferences, and our real-time voice pipeline transcribes and responds instantly. It's like having a personal travel agent on call 24/7!",
  "can i edit my itinerary": "Absolutely! PariKrama puts you in full control. You can:\n\n✏️ Edit any activity or accommodation\n🔄 Swap destinations or experiences\n✅ Approve or reject agent suggestions\n📅 Rearrange the day-by-day schedule\n\nThe AI learns from your preferences to improve future recommendations!",
};

const findResponse = (query: string): string => {
  const q = query.toLowerCase().trim();
  for (const [key, response] of Object.entries(BOT_RESPONSES)) {
    if (q.includes(key) || key.split(" ").some(w => q.includes(w))) {
      return response;
    }
  }
  return `Great question! 🤔 I'm PariKrama's AI assistant. Here's what I can help you with:\n\n• How to plan your first trip\n• Understanding multi-agent AI planning\n• Using voice mode features\n• Editing and customizing itineraries\n\nTry clicking one of the quick questions below, or describe what you need!`;
};

const formatMessage = (text: string) => {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>');
};

export function PariKramaChatbot() {
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "👋 Hi! I'm **Krama**, your PariKrama AI assistant!\n\nI can help you understand how to use PariKrama, plan trips, or answer any travel questions. What would you like to know?",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open && !minimized) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, open, minimized]);

  useEffect(() => {
    if (open && !minimized) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open, minimized]);

  const sendMessage = async (content: string) => {
    if (!content.trim()) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: content.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setIsTyping(true);

    // Simulate natural typing delay
    await new Promise(r => setTimeout(r, 800 + Math.random() * 800));

    const response = findResponse(content);
    const botMsg: Message = {
      id: (Date.now() + 1).toString(),
      role: "assistant",
      content: response,
      timestamp: new Date(),
    };

    setIsTyping(false);
    setMessages(prev => [...prev, botMsg]);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  return (
    <>
      {/* ── FLOATING BUTTON ── */}
      {!open && (
        <button
          onClick={() => { setOpen(true); setMinimized(false); }}
          className="fixed bottom-6 right-6 z-50 flex items-center justify-center w-14 h-14 rounded-full bg-primary glow-primary animate-glow-pulse hover:scale-110 transition-transform shadow-2xl group"
          aria-label="Open AI Chatbot"
        >
          <MessageSquare className="h-6 w-6 text-white" />
          {/* Ripple */}
          <span className="absolute w-full h-full rounded-full bg-primary/40 animate-[ripple_2s_ease-out_infinite]" />
        </button>
      )}

      {/* ── CHAT WINDOW ── */}
      {open && (
        <div className={`
          fixed bottom-6 right-6 z-50 w-[380px] flex flex-col rounded-2xl overflow-hidden
          glass-strong border border-white/10 shadow-2xl
          transition-all duration-300 anim-scale-in
          ${minimized ? "h-14" : "h-[520px]"}
        `}>
          {/* Header */}
          <div className="flex items-center gap-3 p-4 bg-gradient-to-r from-primary/20 to-indigo-500/10 border-b border-white/5">
            <div className="relative">
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center">
                <Bot className="h-5 w-5 text-white" />
              </div>
              <span className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-emerald-400 rounded-full border-2 border-background animate-pulse" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-sm">Krama AI</p>
              <div className="flex items-center gap-1 text-xs text-emerald-400">
                <Sparkles className="h-3 w-3" /> Online · Powered by Gemini
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setMinimized(!minimized)}
                className="p-1.5 rounded-lg hover:bg-white/10 text-muted-foreground hover:text-foreground transition-colors"
              >
                <ChevronDown className={`h-4 w-4 transition-transform ${minimized ? "rotate-180" : ""}`} />
              </button>
              <button
                onClick={() => setOpen(false)}
                className="p-1.5 rounded-lg hover:bg-white/10 text-muted-foreground hover:text-foreground transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {!minimized && (
            <>
              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.map(msg => (
                  <div
                    key={msg.id}
                    className={`flex gap-2.5 msg-enter ${msg.role === "user" ? "flex-row-reverse" : ""}`}
                  >
                    {/* Avatar */}
                    <div className={`
                      flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold
                      ${msg.role === "assistant"
                        ? "bg-gradient-to-br from-violet-500 to-indigo-600"
                        : "bg-gradient-to-br from-cyan-500 to-blue-600"
                      }
                    `}>
                      {msg.role === "assistant" ? <Bot className="h-3.5 w-3.5" /> : <User className="h-3.5 w-3.5" />}
                    </div>

                    {/* Bubble */}
                    <div className={`
                      max-w-[78%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed
                      ${msg.role === "assistant"
                        ? "glass border border-white/5 rounded-tl-sm"
                        : "bg-primary/80 text-white rounded-tr-sm"
                      }
                    `}>
                      <div
                        dangerouslySetInnerHTML={{ __html: formatMessage(msg.content) }}
                        className="whitespace-pre-wrap"
                      />
                      <p className="text-[10px] mt-1.5 opacity-50">
                        {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </p>
                    </div>
                  </div>
                ))}

                {/* Typing indicator */}
                {isTyping && (
                  <div className="flex gap-2.5">
                    <div className="w-7 h-7 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center">
                      <Bot className="h-3.5 w-3.5 text-white" />
                    </div>
                    <div className="glass border border-white/5 rounded-2xl rounded-tl-sm px-4 py-3 flex gap-1 items-center">
                      <span className="typing-dot w-2 h-2 rounded-full bg-primary/60" />
                      <span className="typing-dot w-2 h-2 rounded-full bg-primary/60" />
                      <span className="typing-dot w-2 h-2 rounded-full bg-primary/60" />
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Quick questions */}
              <div className="px-4 pb-2 flex gap-2 overflow-x-auto no-scrollbar">
                {FAQS.map(faq => (
                  <button
                    key={faq}
                    onClick={() => sendMessage(faq)}
                    className="flex-shrink-0 px-3 py-1.5 text-xs rounded-full glass border border-white/10 hover:border-primary/30 hover:text-primary transition-all whitespace-nowrap"
                  >
                    {faq}
                  </button>
                ))}
              </div>

              {/* Input */}
              <form onSubmit={handleSubmit} className="flex gap-2 p-3 border-t border-white/5">
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  placeholder="Ask Krama anything..."
                  className="flex-1 px-3.5 py-2.5 rounded-xl bg-secondary/50 border border-border/50 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all"
                />
                <button
                  type="submit"
                  disabled={!input.trim() || isTyping}
                  className="p-2.5 rounded-xl bg-primary text-white hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all hover:scale-105 glow-primary-sm"
                >
                  <Send className="h-4 w-4" />
                </button>
              </form>
            </>
          )}
        </div>
      )}
    </>
  );
}
