"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Map, Calendar, ArrowRight, Compass, Search, Filter } from "lucide-react";
import { api } from "@/lib/api";

interface TripSummary {
  id: string;
  title: string;
  destination: string;
  start_date: string;
  end_date: string;
  status: string;
  created_at: string;
}

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  planning: { label: "Planning", color: "text-amber-400", bg: "bg-amber-400/10 border-amber-400/20" },
  active: { label: "Active", color: "text-emerald-400", bg: "bg-emerald-400/10 border-emerald-400/20" },
  completed: { label: "Completed", color: "text-blue-400", bg: "bg-blue-400/10 border-blue-400/20" },
  draft: { label: "Draft", color: "text-muted-foreground", bg: "bg-white/5 border-white/10" },
};

const GRADIENTS = [
  "from-violet-600 to-indigo-600",
  "from-cyan-600 to-blue-600",
  "from-emerald-600 to-teal-600",
  "from-amber-600 to-orange-600",
  "from-pink-600 to-rose-600",
];

export default function TripsPage() {
  const [trips, setTrips] = useState<TripSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    async function loadTrips() {
      try {
        const data = await api.get<TripSummary[]>("/api/v1/trips");
        setTrips(data || []);
      } catch (err) {
        console.error("Failed to load trips", err);
      } finally {
        setLoading(false);
      }
    }
    loadTrips();
  }, []);

  const filtered = trips.filter(t =>
    !search ||
    t.title?.toLowerCase().includes(search.toLowerCase()) ||
    t.destination?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col gap-6 w-full max-w-6xl mx-auto pb-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">My Trips</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {loading ? "Loading..." : `${trips.length} trip${trips.length !== 1 ? "s" : ""} planned`}
          </p>
        </div>
        <Link
          href="/dashboard/trips/new"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 glow-primary-sm transition-all hover:scale-105 w-fit"
        >
          <Plus className="h-4 w-4" /> New Trip
        </Link>
      </div>

      {/* Search bar */}
      {trips.length > 0 && (
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search trips..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-secondary/50 border border-border/50 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
            />
          </div>
          <button className="flex items-center gap-2 px-4 py-2.5 rounded-xl glass border border-white/10 hover:border-white/20 text-sm text-muted-foreground hover:text-foreground transition-all">
            <Filter className="h-4 w-4" /> Filter
          </button>
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map(i => (
            <div key={i} className="glass rounded-2xl border border-white/5 overflow-hidden animate-pulse">
              <div className="h-36 bg-white/5" />
              <div className="p-4 space-y-3">
                <div className="h-4 bg-white/5 rounded-lg w-3/4" />
                <div className="h-3 bg-white/5 rounded-lg w-1/2" />
              </div>
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-24 h-24 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-6 animate-float">
            <Map className="h-12 w-12 text-primary/60" />
          </div>
          <h2 className="text-2xl font-bold mb-2">
            {search ? "No trips found" : "Start your first adventure"}
          </h2>
          <p className="text-muted-foreground max-w-sm mb-8 leading-relaxed">
            {search
              ? `No trips match "${search}". Try a different search.`
              : "You haven't planned any trips yet. Let our AI agents craft your perfect itinerary in seconds."
            }
          </p>
          {!search && (
            <Link
              href="/dashboard/trips/new"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-primary text-primary-foreground font-semibold hover:bg-primary/90 glow-primary-sm transition-all hover:scale-105"
            >
              <Compass className="h-4 w-4" /> Plan My First Trip
            </Link>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map((trip, idx) => {
            const statusCfg = STATUS_CONFIG[trip.status] ?? STATUS_CONFIG.draft;
            const gradient = GRADIENTS[idx % GRADIENTS.length];
            return (
              <div
                key={trip.id}
                className="group glass rounded-2xl border border-white/5 hover:border-white/10 overflow-hidden flex flex-col transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl"
              >
                {/* Header gradient */}
                <div className={`h-36 bg-gradient-to-br ${gradient} p-5 flex flex-col justify-between relative overflow-hidden`}>
                  <div className="absolute inset-0 opacity-20 hero-grid" />
                  <span className={`self-start px-2.5 py-1 rounded-full text-xs font-semibold border ${statusCfg.bg} ${statusCfg.color} relative z-10`}>
                    {statusCfg.label}
                  </span>
                  <div className="relative z-10">
                    <h3 className="font-bold text-xl text-white leading-tight truncate">
                      {trip.title || trip.destination || "Untitled Trip"}
                    </h3>
                  </div>
                </div>

                {/* Body */}
                <div className="p-4 flex-1 space-y-2">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Map className="h-3.5 w-3.5 flex-shrink-0 text-primary/60" />
                    <span className="truncate">{trip.destination || "Destination TBD"}</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Calendar className="h-3.5 w-3.5 flex-shrink-0" />
                    <span>
                      {trip.start_date
                        ? new Date(trip.start_date).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })
                        : "Dates not set"}
                    </span>
                  </div>
                </div>

                {/* Footer */}
                <div className="px-4 pb-4">
                  <Link
                    href={`/dashboard/trips/${trip.id}`}
                    className="flex items-center justify-between w-full px-3 py-2.5 rounded-xl glass border border-white/5 hover:border-primary/20 hover:text-primary text-sm font-medium transition-all group/btn"
                  >
                    View Details
                    <ArrowRight className="h-4 w-4 group-hover/btn:translate-x-1 transition-transform" />
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
