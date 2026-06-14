"use client";
import Link from "next/link";
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
  ArrowRight, PlaneTakeoff, Compass, Map, Zap, Shield,
  Star, Globe, ChevronRight, MessageSquare, Mic, Brain
} from "lucide-react";

const STATS = [
  { value: "50K+", label: "Trips Planned" },
  { value: "99.8%", label: "Satisfaction Rate" },
  { value: "15+", label: "AI Agents" },
  { value: "120+", label: "Countries" },
];

const FEATURES = [
  {
    icon: Brain,
    title: "Multi-Agent Intelligence",
    description: "A swarm of specialized AI agents — research, logistics, budget — collaborate simultaneously to craft your perfect trip.",
    gradient: "from-violet-500 to-indigo-500",
    glow: "rgba(139,92,246,0.3)",
  },
  {
    icon: Mic,
    title: "Full-Duplex Voice",
    description: "Talk naturally to your AI travel advisor. Real-time voice pipeline with WebSocket streaming for instant responses.",
    gradient: "from-cyan-500 to-blue-500",
    glow: "rgba(34,211,238,0.3)",
  },
  {
    icon: Shield,
    title: "Human-in-the-Loop",
    description: "You're always in control. AI agents pause for your approval on key decisions — flights, hotels, experiences.",
    gradient: "from-emerald-500 to-teal-500",
    glow: "rgba(16,185,129,0.3)",
  },
  {
    icon: Zap,
    title: "Instant Itineraries",
    description: "From a single prompt to a complete day-by-day itinerary in seconds. Budget breakdowns, maps, and tips included.",
    gradient: "from-amber-500 to-orange-500",
    glow: "rgba(245,158,11,0.3)",
  },
  {
    icon: Globe,
    title: "RAG Knowledge Base",
    description: "Powered by a vast travel knowledge base. Our agents retrieve real-time destination data for accurate planning.",
    gradient: "from-pink-500 to-rose-500",
    glow: "rgba(236,72,153,0.3)",
  },
  {
    icon: MessageSquare,
    title: "AI Chat Assistant",
    description: "Built-in chatbot to guide you through PariKrama. Ask anything, get instant help, every step of the way.",
    gradient: "from-purple-500 to-violet-500",
    glow: "rgba(167,139,250,0.3)",
  },
];

const TESTIMONIALS = [
  { name: "Aarav S.", role: "Adventure Traveler", text: "PariKrama planned my entire Patagonia trip in under 5 minutes. The AI agents are unbelievably smart.", stars: 5 },
  { name: "Priya M.", role: "Business Executive", text: "I had 48 hours in Tokyo. PariKrama built a perfect schedule with every restaurant pre-booked. Magical.", stars: 5 },
  { name: "Rohan K.", role: "Backpacker", text: "Finally, an AI that understands budget travel. My SE Asia itinerary was spot-on and saved me hours of research.", stars: 5 },
];

const FloatingOrb = ({ className, style }: { className?: string; style?: React.CSSProperties }) => (
  <div className={`absolute rounded-full blur-3xl opacity-20 pointer-events-none ${className}`} style={style} />
);

export default function Home() {
  const [mounted, setMounted] = useState(false);
  const [activeTestimonial, setActiveTestimonial] = useState(0);

  useEffect(() => {
    setMounted(true);
    const interval = setInterval(() => {
      setActiveTestimonial(prev => (prev + 1) % TESTIMONIALS.length);
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col min-h-[100dvh] overflow-x-hidden">
      {/* ── HEADER ── */}
      <header className="fixed top-0 left-0 right-0 z-50 h-16 flex items-center px-6 glass border-b border-white/5">
        <Link className="flex items-center gap-2.5 group" href="/">
          <div className="p-1.5 rounded-lg bg-primary/20 group-hover:bg-primary/30 transition-colors">
            <PlaneTakeoff className="h-5 w-5 text-primary" />
          </div>
          <span className="font-bold text-lg tracking-tight">PariKrama</span>
        </Link>
        <nav className="ml-auto flex items-center gap-2">
          <Link
            href="/login"
            className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors rounded-lg hover:bg-white/5"
          >
            Sign In
          </Link>
          <Button asChild size="sm" className="rounded-full px-5 glow-primary-sm transition-all hover:scale-105">
            <Link href="/register">
              Get Started <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
            </Link>
          </Button>
        </nav>
      </header>

      <main className="flex-1 pt-16">
        {/* ── HERO ── */}
        <section className="relative min-h-[95vh] flex items-center justify-center hero-grid overflow-hidden">
          {/* Orbs */}
          <FloatingOrb className="w-[600px] h-[600px] bg-violet-600 animate-float -top-32 -left-48" />
          <FloatingOrb className="w-[400px] h-[400px] bg-cyan-500 animate-float-delayed bottom-0 right-0" />
          <FloatingOrb className="w-[300px] h-[300px] bg-pink-600 animate-float-slow top-1/2 left-1/2" />

          <div className="relative z-10 container px-6 mx-auto">
            <div className="flex flex-col items-center text-center space-y-8 max-w-4xl mx-auto">
              {/* Badge */}
              {mounted && (
                <div className="anim-slide-up inline-flex items-center gap-2 px-4 py-1.5 rounded-full glass border border-primary/20 text-sm font-medium text-primary">
                  <span className="flex h-2 w-2 rounded-full bg-primary animate-pulse" />
                  Powered by Google Gemini 2.5 & Multi-Agent LangGraph
                </div>
              )}

              {/* Headline */}
              {mounted && (
                <div className="anim-slide-up space-y-4" style={{ animationDelay: "0.1s" }}>
                  <h1 className="text-5xl sm:text-6xl md:text-7xl lg:text-8xl font-extrabold tracking-tighter leading-[0.95]">
                    Your AI Travel{" "}
                    <span className="gradient-text glow-text block">
                      Orchestrator
                    </span>
                  </h1>
                  <p className="mx-auto max-w-2xl text-lg md:text-xl text-muted-foreground leading-relaxed">
                    Describe your dream vacation in plain language. A team of specialized AI agents 
                    instantly build a complete, personalized itinerary — with your approval at every step.
                  </p>
                </div>
              )}

              {/* CTAs */}
              {mounted && (
                <div className="anim-slide-up flex flex-col sm:flex-row items-center gap-4" style={{ animationDelay: "0.2s" }}>
                  <Button asChild size="lg" className="rounded-full h-13 px-8 text-base font-semibold glow-primary animate-glow-pulse hover:scale-105 transition-transform">
                    <Link href="/dashboard">
                      Start Planning Free <ArrowRight className="ml-2 h-4 w-4" />
                    </Link>
                  </Button>
                  <Button asChild variant="ghost" size="lg" className="rounded-full h-13 px-8 text-base glass hover:bg-white/10 border border-white/10">
                    <Link href="/login">
                      <Compass className="mr-2 h-4 w-4" /> Explore Demo
                    </Link>
                  </Button>
                </div>
              )}

              {/* Stats row */}
              {mounted && (
                <div className="anim-slide-up w-full grid grid-cols-2 sm:grid-cols-4 gap-4 mt-8" style={{ animationDelay: "0.3s" }}>
                  {STATS.map((stat) => (
                    <div key={stat.label} className="flex flex-col items-center gap-1 p-4 glass rounded-2xl border border-white/5">
                      <span className="text-2xl font-bold gradient-text">{stat.value}</span>
                      <span className="text-xs text-muted-foreground">{stat.label}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Scroll indicator */}
          <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 opacity-50">
            <span className="text-xs text-muted-foreground">Scroll to explore</span>
            <div className="w-px h-10 bg-gradient-to-b from-primary to-transparent animate-pulse" />
          </div>
        </section>

        {/* ── FEATURES ── */}
        <section className="py-24 md:py-32 relative">
          <div className="container px-6 mx-auto">
            <div className="text-center mb-16 space-y-4">
              <p className="text-primary font-semibold tracking-widest text-sm uppercase">Features</p>
              <h2 className="text-3xl md:text-5xl font-bold tracking-tight">
                Everything you need to plan the{" "}
                <span className="gradient-text">perfect trip</span>
              </h2>
              <p className="text-muted-foreground max-w-xl mx-auto text-lg">
                PariKrama combines advanced AI orchestration with an intuitive interface.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {FEATURES.map((f, i) => (
                <div
                  key={f.title}
                  className="group relative p-6 glass rounded-2xl border border-white/5 hover:border-white/10 transition-all duration-300 hover:-translate-y-1 cursor-default"
                  style={{ animationDelay: `${i * 0.1}s` }}
                >
                  {/* Glow on hover */}
                  <div className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"
                    style={{ boxShadow: `0 0 40px ${f.glow}` }} />

                  <div className={`relative w-12 h-12 rounded-xl bg-gradient-to-br ${f.gradient} p-2.5 mb-4 shadow-lg`}>
                    <f.icon className="w-full h-full text-white" />
                  </div>
                  <h3 className="text-lg font-semibold mb-2">{f.title}</h3>
                  <p className="text-muted-foreground text-sm leading-relaxed">{f.description}</p>

                  <div className="mt-4 flex items-center gap-1 text-primary text-sm font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                    Learn more <ChevronRight className="h-3.5 w-3.5" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── TESTIMONIALS ── */}
        <section className="py-24 relative overflow-hidden">
          <FloatingOrb className="w-[500px] h-[500px] bg-violet-700 -right-48 top-1/2 -translate-y-1/2" />
          <div className="container px-6 mx-auto relative z-10">
            <div className="text-center mb-12">
              <p className="text-primary font-semibold tracking-widest text-sm uppercase mb-3">Testimonials</p>
              <h2 className="text-3xl md:text-5xl font-bold tracking-tight">
                Loved by <span className="gradient-text">travelers worldwide</span>
              </h2>
            </div>

            <div className="max-w-2xl mx-auto">
              <div className="relative glass-strong rounded-3xl p-8 border border-white/10">
                <div className="flex gap-1 mb-4">
                  {Array.from({ length: TESTIMONIALS[activeTestimonial].stars }).map((_, i) => (
                    <Star key={i} className="h-4 w-4 fill-amber-400 text-amber-400" />
                  ))}
                </div>
                <p className="text-lg font-medium leading-relaxed mb-6">
                  &ldquo;{TESTIMONIALS[activeTestimonial].text}&rdquo;
                </p>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-500 to-indigo-500 flex items-center justify-center text-white font-bold text-sm">
                    {TESTIMONIALS[activeTestimonial].name[0]}
                  </div>
                  <div>
                    <p className="font-semibold text-sm">{TESTIMONIALS[activeTestimonial].name}</p>
                    <p className="text-xs text-muted-foreground">{TESTIMONIALS[activeTestimonial].role}</p>
                  </div>
                </div>

                {/* Dots */}
                <div className="flex gap-2 mt-6 justify-center">
                  {TESTIMONIALS.map((_, i) => (
                    <button
                      key={i}
                      onClick={() => setActiveTestimonial(i)}
                      className={`h-1.5 rounded-full transition-all ${i === activeTestimonial ? "w-6 bg-primary" : "w-1.5 bg-white/20"}`}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── CTA BANNER ── */}
        <section className="py-24">
          <div className="container px-6 mx-auto">
            <div className="relative glass-strong rounded-3xl p-12 text-center border border-white/10 overflow-hidden gradient-border">
              <FloatingOrb className="w-80 h-80 bg-violet-600 -top-20 -left-20" style={{ opacity: 0.12 }} />
              <FloatingOrb className="w-80 h-80 bg-cyan-500 -bottom-20 -right-20" style={{ opacity: 0.08 }} />
              <div className="relative z-10 space-y-6">
                <h2 className="text-3xl md:text-5xl font-bold tracking-tight">
                  Ready to travel smarter?
                </h2>
                <p className="text-muted-foreground text-lg max-w-xl mx-auto">
                  Join thousands of travelers using PariKrama to plan unforgettable journeys with AI.
                </p>
                <Button asChild size="lg" className="rounded-full h-13 px-10 text-base font-semibold glow-primary hover:scale-105 transition-transform">
                  <Link href="/register">
                    Create Free Account <ArrowRight className="ml-2 h-4 w-4" />
                  </Link>
                </Button>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* ── FOOTER ── */}
      <footer className="border-t border-white/5 py-8 glass">
        <div className="container px-6 mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <PlaneTakeoff className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold">PariKrama</span>
          </div>
          <p className="text-xs text-muted-foreground">
            © {new Date().getFullYear()} PariKrama. Built with ❤️ for travelers.
          </p>
          <nav className="flex gap-4">
            <Link href="#" className="text-xs text-muted-foreground hover:text-foreground transition-colors">Privacy</Link>
            <Link href="#" className="text-xs text-muted-foreground hover:text-foreground transition-colors">Terms</Link>
            <Link href="#" className="text-xs text-muted-foreground hover:text-foreground transition-colors">Contact</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
