"use client";
import Link from "next/link";
import { useAuthStore } from "@/stores/authStore";
import {
  ArrowRight, Map, Compass, Zap, TrendingUp,
  Clock, CheckCircle, AlertTriangle, PlusCircle
} from "lucide-react";

const ACTIVITY = [
  { icon: CheckCircle, color: "text-emerald-400", text: "Research Agent completed destination analysis", sub: "Trip to Kyoto • 2 hours ago", status: "success" },
  { icon: AlertTriangle, color: "text-amber-400", text: "Logistics Agent needs flight approval", sub: "Trip to Kyoto • 5 hours ago", status: "warning" },
  { icon: CheckCircle, color: "text-emerald-400", text: "Budget Agent finalized cost breakdown", sub: "Trip to Goa • 1 day ago", status: "success" },
  { icon: Zap, color: "text-primary", text: "Trip finalized and saved", sub: "Trip to Rajasthan • 2 days ago", status: "info" },
];

export default function DashboardHome() {
  const { user } = useAuthStore();
  const greeting = () => {
    const h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
  };

  return (
    <div className="flex flex-col gap-8 max-w-6xl mx-auto w-full pb-8">
      {/* ── HEADER ── */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-muted-foreground text-sm mb-1">{greeting()},</p>
          <h1 className="text-3xl font-bold tracking-tight">
            {user?.name ?? "Traveler"} 👋
          </h1>
          <p className="text-muted-foreground mt-1">Here&apos;s what&apos;s happening with your trips.</p>
        </div>
        <Link
          href="/dashboard/trips/new"
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 glow-primary-sm hover:glow-primary transition-all hover:scale-105"
        >
          <PlusCircle className="h-4 w-4" /> New Trip
        </Link>
      </div>

      {/* ── STATS ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { icon: Map, label: "Total Trips", value: "12", change: "+2 this month", color: "from-violet-500 to-indigo-500", glow: "rgba(139,92,246,0.25)" },
          { icon: Compass, label: "Active Agents", value: "3", change: "Currently planning", color: "from-cyan-500 to-blue-500", glow: "rgba(34,211,238,0.25)" },
          { icon: AlertTriangle, label: "Approvals", value: "1", change: "Action required", color: "from-amber-500 to-orange-500", glow: "rgba(245,158,11,0.25)" },
          { icon: TrendingUp, label: "Total Budget", value: "₹24.5K", change: "Estimated costs", color: "from-emerald-500 to-teal-500", glow: "rgba(16,185,129,0.25)" },
        ].map(stat => (
          <div
            key={stat.label}
            className="glass rounded-2xl p-5 border border-white/5 hover:border-white/10 transition-all group cursor-default"
            style={{ transition: "box-shadow 0.3s" }}
            onMouseEnter={e => (e.currentTarget.style.boxShadow = `0 0 30px ${stat.glow}`)}
            onMouseLeave={e => (e.currentTarget.style.boxShadow = "")}
          >
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{stat.label}</p>
              <div className={`p-2 rounded-lg bg-gradient-to-br ${stat.color} shadow-md`}>
                <stat.icon className="h-3.5 w-3.5 text-white" />
              </div>
            </div>
            <p className="text-2xl font-bold mb-1">{stat.value}</p>
            <p className="text-xs text-muted-foreground">{stat.change}</p>
          </div>
        ))}
      </div>

      {/* ── MAIN GRID ── */}
      <div className="grid gap-6 lg:grid-cols-7">
        {/* Activity Feed */}
        <div className="lg:col-span-4 glass rounded-2xl border border-white/5 overflow-hidden">
          <div className="p-5 border-b border-white/5 flex items-center justify-between">
            <div>
              <h2 className="font-semibold text-base">Recent Activity</h2>
              <p className="text-xs text-muted-foreground mt-0.5">Your AI agents are hard at work</p>
            </div>
            <div className="flex items-center gap-1 text-xs text-emerald-400 bg-emerald-400/10 px-2.5 py-1 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Live
            </div>
          </div>
          <div className="p-5 space-y-4">
            {ACTIVITY.map((item, i) => (
              <div key={i} className="flex items-start gap-3 group">
                <div className={`mt-0.5 flex-shrink-0 ${item.color}`}>
                  <item.icon className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium leading-none mb-1">{item.text}</p>
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <Clock className="h-3 w-3" /> {item.sub}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="lg:col-span-3 flex flex-col gap-4">
          <div className="glass rounded-2xl border border-white/5 p-5">
            <h2 className="font-semibold text-base mb-1">Quick Actions</h2>
            <p className="text-xs text-muted-foreground mb-4">Jump right in</p>

            <div className="space-y-3">
              <Link
                href="/dashboard/trips/new"
                className="flex items-center gap-3 p-4 rounded-xl bg-primary/10 border border-primary/20 hover:bg-primary/20 hover:border-primary/40 transition-all group"
              >
                <div className="p-2 rounded-lg bg-primary/20 group-hover:bg-primary/30 transition-colors">
                  <Compass className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold">Start a New Trip</p>
                  <p className="text-xs text-muted-foreground">Chat with AI to plan</p>
                </div>
                <ArrowRight className="h-4 w-4 text-primary/60 group-hover:translate-x-1 transition-transform" />
              </Link>

              <Link
                href="/dashboard/trips"
                className="flex items-center gap-3 p-4 rounded-xl glass border border-white/5 hover:border-white/10 transition-all group"
              >
                <div className="p-2 rounded-lg bg-white/5 group-hover:bg-white/10 transition-colors">
                  <Map className="h-5 w-5 text-muted-foreground group-hover:text-foreground transition-colors" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold">View Itineraries</p>
                  <p className="text-xs text-muted-foreground">All your saved trips</p>
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:translate-x-1 transition-transform" />
              </Link>
            </div>
          </div>

          {/* Promo card */}
          <div className="relative glass rounded-2xl border border-primary/20 p-5 overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-br from-primary/10 to-transparent" />
            <div className="relative z-10">
              <div className="p-2.5 w-fit rounded-xl bg-primary/20 mb-3">
                <Zap className="h-5 w-5 text-primary" />
              </div>
              <h3 className="font-semibold mb-1">Try Voice Planning</h3>
              <p className="text-xs text-muted-foreground mb-3 leading-relaxed">
                Speak naturally to our AI. Describe your dream trip and watch it come to life.
              </p>
              <Link
                href="/dashboard/trips/new"
                className="inline-flex items-center gap-1.5 text-primary text-xs font-semibold hover:underline"
              >
                Try it now <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
