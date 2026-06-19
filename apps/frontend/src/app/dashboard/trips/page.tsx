"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Plus, Map, Calendar, ArrowRight, Compass,
  Search, Clock, IndianRupee, Plane, CheckCircle2,
  AlertTriangle, Loader2, Ban, HelpCircle
} from "lucide-react";
import { api } from "@/lib/api";

interface TripSummary {
  id: string;
  title: string;
  destination: string;
  origin: string;
  days: number;
  budget_inr: number;
  start_date: string;
  status: string;
  created_at: string;
}

const STATUS_MAP: Record<string, {
  label: string;
  cls: string;
  icon: React.ElementType;
  iconCls: string;
}> = {
  planning:          { label: "Planning",   cls: "status-planning",   icon: Loader2,       iconCls: "animate-spin" },
  pending:           { label: "Pending",    cls: "status-pending",    icon: Clock,         iconCls: "" },
  completed:         { label: "Completed",  cls: "status-completed",  icon: CheckCircle2,  iconCls: "" },
  awaiting_approval: { label: "Needs Approval", cls: "status-awaiting", icon: AlertTriangle, iconCls: "animate-pulse" },
  failed:            { label: "Failed",     cls: "status-failed",     icon: AlertTriangle, iconCls: "" },
  cancelled:         { label: "Cancelled",  cls: "status-pending",    icon: Ban,           iconCls: "" },
};

const CARD_GRADIENTS = [
  { from: "from-violet-600/80", to: "to-indigo-700/80", orb: "bg-violet-500" },
  { from: "from-cyan-600/80",   to: "to-blue-700/80",   orb: "bg-cyan-400" },
  { from: "from-emerald-600/80",to: "to-teal-700/80",   orb: "bg-emerald-400" },
  { from: "from-amber-600/80",  to: "to-orange-700/80", orb: "bg-amber-400" },
  { from: "from-rose-600/80",   to: "to-pink-700/80",   orb: "bg-rose-400" },
  { from: "from-fuchsia-600/80",to: "to-purple-700/80", orb: "bg-fuchsia-400" },
];

// Indian state/city to emoji mapping for cards
const DEST_EMOJI: Record<string, string> = {
  goa: "🏖️", manali: "🏔️", delhi: "🏛️", mumbai: "🌃", jaipur: "🏯",
  kerala: "🌴", ladakh: "❄️", rishikesh: "🌊", agra: "🕌", bangalore: "🌆",
  kolkata: "🎭", chennai: "🌊", hyderabad: "💎", varanasi: "🪔", ooty: "🌿",
  darjeeling: "🍵", shimla: "⛷️", udaipur: "🏰", mysore: "🐘", coorg: "☕",
};

const getDestEmoji = (dest: string) => {
  if (!dest) return "✈️";
  const lower = dest.toLowerCase();
  for (const [key, emoji] of Object.entries(DEST_EMOJI)) {
    if (lower.includes(key)) return emoji;
  }
  return "🗺️";
};

export default function TripsPage() {
  const [trips, setTrips] = useState<TripSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  useEffect(() => {
    async function load() {
      try {
        const data = await api.get<any>("/api/v1/trips?page_size=50");
        const items = (data?.items || []).map((t: any) => ({
          id: t.id,
          title: t.request?.destination
            ? `${getDestEmoji(t.request.destination)} ${t.request.destination}`
            : "Untitled Trip",
          destination: t.request?.destination || "TBD",
          origin: t.request?.origin || "",
          days: t.request?.days || 0,
          budget_inr: t.request?.budget_inr || 0,
          start_date: t.request?.start_date || "",
          status: t.status,
          created_at: t.created_at,
        }));
        setTrips(items);
      } catch (err) {
        console.error("Failed to load trips", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const filtered = trips.filter(t => {
    const matchSearch = !search ||
      t.title.toLowerCase().includes(search.toLowerCase()) ||
      t.destination.toLowerCase().includes(search.toLowerCase()) ||
      t.origin.toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === "all" || t.status === statusFilter;
    return matchSearch && matchStatus;
  });

  const STATUS_FILTERS = ["all", "planning", "completed", "pending", "awaiting_approval", "failed"];

  return (
    <div className="flex flex-col gap-7 w-full max-w-6xl mx-auto pb-10">

      {/* ── PAGE HEADER ── */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">My Trips</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {loading ? "Loading your adventures..." : `${trips.length} trip${trips.length !== 1 ? "s" : ""} planned · ${trips.filter(t => t.status === "completed").length} completed`}
          </p>
        </div>
        <Link
          href="/dashboard/trips/new"
          className="btn-gradient inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-white text-sm font-semibold w-fit shadow-lg"
        >
          <Plus className="h-4 w-4" /> Plan New Trip
        </Link>
      </div>

      {/* ── SEARCH + FILTER ── */}
      {trips.length > 0 && (
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search destinations, cities..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-secondary/40 border border-white/6 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/30 transition-all"
            />
          </div>
          {/* Status filter pills */}
          <div className="flex gap-2 overflow-x-auto no-scrollbar">
            {STATUS_FILTERS.map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`flex-shrink-0 px-3 py-2 rounded-xl text-xs font-semibold capitalize transition-all ${
                  statusFilter === s
                    ? "bg-primary/20 text-primary border border-primary/30"
                    : "glass border border-white/6 text-muted-foreground hover:text-foreground hover:border-white/12"
                }`}
              >
                {s === "all" ? "All" : s === "awaiting_approval" ? "Approval" : s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── SKELETON ── */}
      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <div key={i} className="glass-card rounded-2xl overflow-hidden">
              <div className="h-40 animate-shimmer bg-white/3" />
              <div className="p-4 space-y-3">
                <div className="h-4 animate-shimmer bg-white/5 rounded-lg w-3/4" />
                <div className="h-3 animate-shimmer bg-white/5 rounded-lg w-1/2" />
                <div className="h-3 animate-shimmer bg-white/5 rounded-lg w-2/3" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── EMPTY STATE ── */}
      {!loading && filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center anim-fade-in">
          <div className="relative w-24 h-24 mb-6">
            <div className="w-24 h-24 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center animate-float">
              <Map className="h-11 w-11 text-primary/60" />
            </div>
            <div className="absolute -bottom-1 -right-1 w-8 h-8 rounded-xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center">
              <span className="text-lg">{search ? "🔍" : "✨"}</span>
            </div>
          </div>
          <h2 className="text-2xl font-bold mb-2">
            {search ? "No trips found" : "Start your first adventure!"}
          </h2>
          <p className="text-muted-foreground max-w-sm mb-8 leading-relaxed text-sm">
            {search
              ? `No trips match "${search}". Try a different city or destination.`
              : "You haven't planned any trips yet. Let our AI agents craft your perfect itinerary — it takes just 60 seconds!"}
          </p>
          {!search && (
            <Link
              href="/dashboard/trips/new"
              className="btn-gradient inline-flex items-center gap-2 px-6 py-3 rounded-xl text-white font-semibold shadow-lg"
            >
              <Compass className="h-4 w-4" /> Plan My First Trip
            </Link>
          )}
        </div>
      )}

      {/* ── TRIP GRID ── */}
      {!loading && filtered.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map((trip, idx) => {
            const grad = CARD_GRADIENTS[idx % CARD_GRADIENTS.length];
            const statusCfg = STATUS_MAP[trip.status] ?? STATUS_MAP.pending;
            const StatusIcon = statusCfg.icon;

            return (
              <Link
                key={trip.id}
                href={`/dashboard/trips/${trip.id}`}
                className="group glass-card rounded-2xl overflow-hidden flex flex-col hover:-translate-y-1.5 hover:shadow-2xl transition-all duration-300 border-white/5 hover:border-white/10"
              >
                {/* Card hero */}
                <div className={`relative h-40 bg-gradient-to-br ${grad.from} ${grad.to} p-5 flex flex-col justify-between overflow-hidden`}>
                  {/* Mesh grid */}
                  <div className="absolute inset-0 hero-grid opacity-30" />

                  {/* Orb blob */}
                  <div className={`absolute -bottom-6 -right-6 w-28 h-28 rounded-full ${grad.orb} opacity-15 blur-2xl`} />

                  {/* Status */}
                  <div className="relative z-10 flex items-center justify-between">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold ${statusCfg.cls}`}>
                      <StatusIcon className={`h-3 w-3 ${statusCfg.iconCls}`} />
                      {statusCfg.label}
                    </span>
                    {trip.days > 0 && (
                      <span className="px-2.5 py-1 rounded-full bg-black/30 text-white text-[11px] font-semibold backdrop-blur-sm">
                        {trip.days}D
                      </span>
                    )}
                  </div>

                  {/* Title */}
                  <div className="relative z-10">
                    <h3 className="font-bold text-xl text-white leading-tight drop-shadow-sm line-clamp-2">
                      {trip.title || trip.destination}
                    </h3>
                    {trip.origin && (
                      <p className="text-white/70 text-xs mt-0.5 flex items-center gap-1">
                        <Plane className="h-3 w-3" />
                        {trip.origin} → {trip.destination}
                      </p>
                    )}
                  </div>
                </div>

                {/* Card body */}
                <div className="flex-1 p-4 flex flex-col gap-3">
                  <div className="grid grid-cols-2 gap-2">
                    {trip.budget_inr > 0 && (
                      <div className="flex items-center gap-2 p-2.5 rounded-xl glass border border-white/5">
                        <IndianRupee className="h-3.5 w-3.5 text-emerald-400 flex-shrink-0" />
                        <div>
                          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Budget</p>
                          <p className="text-xs font-semibold text-emerald-400">
                            ₹{trip.budget_inr >= 1000 ? `${(trip.budget_inr / 1000).toFixed(1)}K` : trip.budget_inr}
                          </p>
                        </div>
                      </div>
                    )}
                    {trip.start_date ? (
                      <div className="flex items-center gap-2 p-2.5 rounded-xl glass border border-white/5">
                        <Calendar className="h-3.5 w-3.5 text-blue-400 flex-shrink-0" />
                        <div>
                          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Date</p>
                          <p className="text-xs font-semibold">
                            {new Date(trip.start_date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                          </p>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 p-2.5 rounded-xl glass border border-white/5">
                        <Clock className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                        <div>
                          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Created</p>
                          <p className="text-xs font-semibold">
                            {new Date(trip.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* CTA */}
                  <div className="mt-auto flex items-center justify-between text-sm font-medium text-muted-foreground group-hover:text-primary transition-colors pt-1">
                    <span>{trip.status === "completed" ? "View Itinerary" : trip.status === "planning" ? "Live Planning..." : "View Details"}</span>
                    <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
