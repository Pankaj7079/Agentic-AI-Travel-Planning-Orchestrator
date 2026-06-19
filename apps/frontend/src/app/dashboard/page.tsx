"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { useAuthStore } from "@/stores/authStore";
import { api } from "@/lib/api";
import {
  ArrowRight, Map, Compass, Zap, TrendingUp,
  Clock, CheckCircle2, AlertTriangle, Plus,
  Plane, Sparkles, Activity, IndianRupee
} from "lucide-react";

export default function DashboardHome() {
  const { user } = useAuthStore();
  const [stats, setStats] = useState<any>(null);
  const [activeCount, setActiveCount] = useState<number>(0);
  const [approvalsCount, setApprovalsCount] = useState<number>(0);
  const [recentTrips, setRecentTrips] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [statsData, planningTrips, approvalsData, recentData] = await Promise.all([
          api.get<any>("/api/v1/users/me/stats").catch(() => ({ total_trips: 0, completed_trips: 0, total_cost_usd: 0 })),
          api.get<any>("/api/v1/trips?status=planning&page_size=5").catch(() => ({ total: 0 })),
          api.get<any>("/api/v1/approvals").catch(() => []),
          api.get<any>("/api/v1/trips?page_size=5").catch(() => ({ items: [] })),
        ]);
        setStats(statsData);
        setActiveCount(planningTrips?.total ?? 0);
        setApprovalsCount(Array.isArray(approvalsData) ? approvalsData.length : (approvalsData?.total ?? 0));
        setRecentTrips(recentData?.items || []);
      } catch (e) {
        console.error("Dashboard load error", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const greeting = () => {
    const h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
  };

  const fmtInr = (usd: number) => {
    const inr = usd * 83;
    if (inr >= 100000) return `₹${(inr / 100000).toFixed(1)}L`;
    if (inr >= 1000) return `₹${(inr / 1000).toFixed(1)}K`;
    return `₹${inr.toFixed(0)}`;
  };

  const STATS = [
    {
      icon: Plane,
      label: "Total Trips",
      value: loading ? "—" : String(stats?.total_trips ?? 0),
      sub: `${stats?.completed_trips ?? 0} completed`,
      gradient: "from-violet-500 to-indigo-500",
      glow: "rgba(139,92,246,0.28)",
    },
    {
      icon: Activity,
      label: "Active Agents",
      value: loading ? "—" : String(activeCount),
      sub: "Currently planning",
      gradient: "from-cyan-500 to-blue-500",
      glow: "rgba(34,211,238,0.28)",
    },
    {
      icon: AlertTriangle,
      label: "Approvals",
      value: loading ? "—" : String(approvalsCount),
      sub: "Action needed",
      gradient: "from-amber-500 to-orange-500",
      glow: "rgba(245,158,11,0.28)",
    },
    {
      icon: IndianRupee,
      label: "Total Budget",
      value: loading ? "—" : fmtInr(stats?.total_cost_usd ?? 0),
      sub: "Estimated spend",
      gradient: "from-emerald-500 to-teal-500",
      glow: "rgba(16,185,129,0.28)",
    },
  ];

  const getFeedItems = () => {
    if (!recentTrips.length) {
      return [{
        icon: Sparkles,
        iconCls: "text-primary",
        title: "Welcome to PariKrama!",
        sub: "Start your first trip and watch AI agents plan in real-time.",
        href: "/dashboard/trips/new",
        badge: null,
      }];
    }
    return recentTrips.map(trip => {
      const dest = trip.request?.destination || "your destination";
      const date = new Date(trip.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
      if (trip.status === "completed") return {
        icon: CheckCircle2, iconCls: "text-emerald-400",
        title: `Itinerary ready for ${dest}`,
        sub: `Completed · ${date}`, href: `/dashboard/trips/${trip.id}`, badge: null,
      };
      if (trip.status === "planning") return {
        icon: Compass, iconCls: "text-cyan-400 animate-spin",
        title: `Planning trip to ${dest}`,
        sub: `AI agents running... · ${date}`, href: `/dashboard/trips/new?tripId=${trip.id}`, badge: "Live",
      };
      if (trip.status === "awaiting_approval") return {
        icon: AlertTriangle, iconCls: "text-amber-400",
        title: `Approval required for ${dest}`,
        sub: `HITL decision pending · ${date}`, href: `/dashboard/trips/new?tripId=${trip.id}`, badge: "Action",
      };
      if (trip.status === "failed") return {
        icon: AlertTriangle, iconCls: "text-rose-400",
        title: `Planning failed for ${dest}`,
        sub: `Retry recommended · ${date}`, href: `/dashboard/trips/new`, badge: null,
      };
      return {
        icon: Clock, iconCls: "text-muted-foreground",
        title: `Trip to ${dest} is queued`,
        sub: `Pending · ${date}`, href: `/dashboard/trips/${trip.id}`, badge: null,
      };
    });
  };

  return (
    <div className="flex flex-col gap-8 max-w-6xl mx-auto w-full pb-10">

      {/* ── HERO GREETING ── */}
      <div className="relative rounded-2xl overflow-hidden p-6 glass-card border border-white/6">
        <div className="absolute inset-0 hero-grid opacity-60" />
        <div className="absolute top-0 right-0 w-64 h-64 rounded-full bg-primary/8 blur-3xl pointer-events-none" />
        <div className="relative z-10 flex items-center justify-between gap-4 flex-wrap">
          <div>
            <p className="text-muted-foreground text-sm mb-1 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              {greeting()},
            </p>
            <h1 className="text-3xl font-bold tracking-tight">
              {user?.name ?? "Traveler"} <span className="gradient-text">👋</span>
            </h1>
            <p className="text-muted-foreground mt-1.5 text-sm">
              {recentTrips.length
                ? `You have ${recentTrips.length} trip${recentTrips.length > 1 ? "s" : ""}. Let's plan something amazing!`
                : "Ready to plan your next adventure? AI agents are standing by."}
            </p>
          </div>
          <Link
            href="/dashboard/trips/new"
            className="btn-gradient flex items-center gap-2 px-5 py-2.5 rounded-xl text-white text-sm font-semibold shadow-lg"
          >
            <Plus className="h-4 w-4" /> New Trip
          </Link>
        </div>
      </div>

      {/* ── STATS ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {STATS.map(s => (
          <div
            key={s.label}
            className="glass-card rounded-2xl p-5 border border-white/5 hover:border-white/10 transition-all duration-300 cursor-default group"
            onMouseEnter={e => (e.currentTarget.style.boxShadow = `0 0 32px ${s.glow}`)}
            onMouseLeave={e => (e.currentTarget.style.boxShadow = "")}
          >
            <div className="flex items-start justify-between mb-4">
              <div className={`p-2 rounded-xl bg-gradient-to-br ${s.gradient} shadow-lg group-hover:scale-110 transition-transform`}>
                <s.icon className="h-4 w-4 text-white" />
              </div>
              <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest text-right">{s.label}</p>
            </div>
            <p className={`text-3xl font-bold tracking-tight mb-1 ${loading ? "opacity-30" : ""}`}>{s.value}</p>
            <p className="text-xs text-muted-foreground">{s.sub}</p>
          </div>
        ))}
      </div>

      {/* ── MAIN GRID ── */}
      <div className="grid gap-6 lg:grid-cols-7">

        {/* Activity Feed */}
        <div className="lg:col-span-4 glass-card rounded-2xl border border-white/5 overflow-hidden">
          <div className="p-5 border-b border-white/5 flex items-center justify-between">
            <div>
              <h2 className="font-semibold">Recent Activity</h2>
              <p className="text-xs text-muted-foreground mt-0.5">Your AI agents, live</p>
            </div>
            <span className="flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 px-2.5 py-1 rounded-full font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Live
            </span>
          </div>
          <div className="divide-y divide-white/4">
            {getFeedItems().map((item, i) => (
              <Link
                key={i}
                href={item.href}
                className="flex items-start gap-3 p-4 hover:bg-white/3 transition-colors group"
              >
                <div className={`mt-0.5 flex-shrink-0 p-1.5 rounded-lg bg-white/5 ${item.iconCls}`}>
                  <item.icon className="h-3.5 w-3.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium leading-snug group-hover:text-primary transition-colors truncate">{item.title}</p>
                  <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1">
                    <Clock className="h-3 w-3" /> {item.sub}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {item.badge && (
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                      item.badge === "Live" ? "bg-cyan-400/15 text-cyan-400 border border-cyan-400/25" :
                      "bg-amber-400/15 text-amber-400 border border-amber-400/25"
                    }`}>{item.badge}</span>
                  )}
                  <ArrowRight className="h-3.5 w-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />
                </div>
              </Link>
            ))}
          </div>
        </div>

        {/* Right Column */}
        <div className="lg:col-span-3 flex flex-col gap-4">

          {/* Quick Actions */}
          <div className="glass-card rounded-2xl border border-white/5 p-5">
            <h2 className="font-semibold mb-0.5">Quick Actions</h2>
            <p className="text-xs text-muted-foreground mb-4">Jump right in</p>
            <div className="space-y-2.5">
              <Link
                href="/dashboard/trips/new"
                className="flex items-center gap-3 p-3.5 rounded-xl bg-primary/10 border border-primary/20 hover:bg-primary/15 hover:border-primary/35 transition-all group"
              >
                <div className="p-2 rounded-lg bg-primary/20 group-hover:bg-primary/30 transition-colors">
                  <Compass className="h-4 w-4 text-primary" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-semibold">Start a New Trip</p>
                  <p className="text-xs text-muted-foreground">Chat with AI to plan</p>
                </div>
                <ArrowRight className="h-4 w-4 text-primary/50 group-hover:translate-x-0.5 transition-transform" />
              </Link>
              <Link
                href="/dashboard/trips"
                className="flex items-center gap-3 p-3.5 rounded-xl glass border border-white/5 hover:border-white/12 transition-all group"
              >
                <div className="p-2 rounded-lg bg-white/5 group-hover:bg-white/8 transition-colors">
                  <Map className="h-4 w-4 text-muted-foreground group-hover:text-foreground transition-colors" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-semibold">View All Trips</p>
                  <p className="text-xs text-muted-foreground">Browse your itineraries</p>
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground/50 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            </div>
          </div>

          {/* Promo card — Krama AI */}
          <div className="relative glass-card rounded-2xl border border-primary/20 overflow-hidden p-5">
            <div className="absolute inset-0 bg-gradient-to-br from-primary/10 via-indigo-500/5 to-transparent pointer-events-none" />
            <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 rounded-full blur-2xl pointer-events-none" />
            <div className="relative z-10">
              <div className="flex items-center gap-2 mb-3">
                <div className="p-2 rounded-xl bg-primary/20 border border-primary/20">
                  <Zap className="h-4 w-4 text-primary" />
                </div>
                <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-primary/15 text-primary border border-primary/25">NEW</span>
              </div>
              <h3 className="font-bold mb-1">Ask Krama AI</h3>
              <p className="text-xs text-muted-foreground mb-4 leading-relaxed">
                Have questions about your trip? Chat with Krama — our AI assistant powered by Gemini, available 24/7.
              </p>
              <button
                onClick={() => {
                  const fab = document.querySelector("[aria-label='Open AI assistant']") as HTMLButtonElement;
                  fab?.click();
                }}
                className="inline-flex items-center gap-1.5 text-primary text-xs font-semibold hover:gap-2.5 transition-all"
              >
                Open Krama <ArrowRight className="h-3 w-3" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
