"use client";
import { useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft, Map, Calendar, DollarSign, Users, Plane,
  Hotel, Utensils, Compass, Clock, ChevronDown, ChevronUp,
  CheckCircle, Download, Share2, ExternalLink, Sparkles,
  AlertCircle, Loader2, TrendingUp, Star
} from "lucide-react";
import { api } from "@/lib/api";

interface TripDetail {
  id: string;
  status: string;
  request: {
    origin?: string;
    destination?: string;
    days?: number;
    budget_inr?: number;
    travelers?: number;
    start_date?: string | null;
    raw_input?: string;
  };
  result?: {
    itinerary?: any[];
    budget_breakdown?: {
      transport_inr: number;
      accommodation_inr: number;
      food_inr: number;
      activities_inr: number;
      misc_inr: number;
      total_inr: number;
    };
    summary?: string;
    hotel_options?: any[];
    transport_options?: any[];
  } | null;
  planning_duration_ms?: number;
  created_at: string;
}

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: any }> = {
  planning: { label: "Planning", color: "text-amber-400", bg: "bg-amber-400/10 border-amber-400/20", icon: Loader2 },
  pending: { label: "Pending", color: "text-muted-foreground", bg: "bg-white/5 border-white/10", icon: Clock },
  awaiting_approval: { label: "Awaiting Approval", color: "text-orange-400", bg: "bg-orange-400/10 border-orange-400/20", icon: AlertCircle },
  completed: { label: "Completed", color: "text-emerald-400", bg: "bg-emerald-400/10 border-emerald-400/20", icon: CheckCircle },
  failed: { label: "Failed", color: "text-rose-400", bg: "bg-rose-400/10 border-rose-400/20", icon: AlertCircle },
  cancelled: { label: "Cancelled", color: "text-muted-foreground", bg: "bg-white/5 border-white/10", icon: AlertCircle },
};

const BUDGET_COLORS = [
  "from-violet-500 to-indigo-500",
  "from-cyan-500 to-blue-500",
  "from-emerald-500 to-teal-500",
  "from-amber-500 to-orange-500",
  "from-pink-500 to-rose-500",
];

export default function TripDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter();
  const { id } = use(params);
  const [trip, setTrip] = useState<TripDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedDay, setExpandedDay] = useState<number | null>(0);

  useEffect(() => {
    async function loadTrip() {
      try {
        const data = await api.get<TripDetail>(`/api/v1/trips/${id}`);
        setTrip(data);
      } catch (err: any) {
        setError(err.message || "Failed to load trip");
      } finally {
        setLoading(false);
      }
    }
    loadTrip();
  }, [id]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[500px] gap-4">
        <div className="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center animate-pulse">
          <Sparkles className="h-8 w-8 text-primary/60" />
        </div>
        <p className="text-muted-foreground">Loading your trip...</p>
      </div>
    );
  }

  if (error || !trip) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[500px] text-center">
        <div className="w-16 h-16 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center mb-4">
          <AlertCircle className="h-8 w-8 text-rose-400" />
        </div>
        <h2 className="text-2xl font-bold mb-2">Trip Not Found</h2>
        <p className="text-muted-foreground mb-6">{error || "The trip you are looking for does not exist."}</p>
        <button
          onClick={() => router.push("/dashboard/trips")}
          className="px-5 py-2.5 rounded-xl bg-primary text-white font-semibold hover:bg-primary/90 transition-all"
        >
          Return to Trips
        </button>
      </div>
    );
  }

  const statusCfg = STATUS_CONFIG[trip.status] ?? STATUS_CONFIG.pending;
  const StatusIcon = statusCfg.icon;
  const destination = trip.request?.destination || trip.result?.itinerary?.[0]?.location || "Your Destination";
  const origin = trip.request?.origin || "Your Origin";
  const days = trip.request?.days || trip.result?.itinerary?.length || 0;
  const budget = trip.request?.budget_inr || trip.result?.budget_breakdown?.total_inr || 0;
  const travelers = trip.request?.travelers || 1;
  const itinerary = trip.result?.itinerary || [];
  const breakdown = trip.result?.budget_breakdown;
  const summary = trip.result?.summary || "";
  const hotels = trip.result?.hotel_options || [];
  const transports = trip.result?.transport_options || [];

  const budgetCategories = breakdown ? [
    { label: "Transport", amount: breakdown.transport_inr, color: BUDGET_COLORS[0] },
    { label: "Accommodation", amount: breakdown.accommodation_inr, color: BUDGET_COLORS[1] },
    { label: "Food & Dining", amount: breakdown.food_inr, color: BUDGET_COLORS[2] },
    { label: "Activities", amount: breakdown.activities_inr, color: BUDGET_COLORS[3] },
    { label: "Miscellaneous", amount: breakdown.misc_inr, color: BUDGET_COLORS[4] },
  ] : [];

  const totalBudget = breakdown?.total_inr || budget;

  return (
    <div className="flex flex-col gap-6 w-full max-w-5xl mx-auto pb-10 anim-slide-up">
      {/* Back Button */}
      <button
        onClick={() => router.push("/dashboard/trips")}
        className="flex items-center gap-2 text-muted-foreground hover:text-foreground text-sm transition-colors w-fit"
      >
        <ArrowLeft className="h-4 w-4" /> Back to Trips
      </button>

      {/* Hero Card */}
      <div className="relative overflow-hidden rounded-2xl border border-white/10">
        <div className="absolute inset-0 bg-gradient-to-br from-violet-600/30 via-indigo-600/20 to-transparent" />
        <div className="absolute inset-0 hero-grid opacity-30" />
        <div className="relative z-10 p-6 sm:p-8">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div className="flex-1">
              <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${statusCfg.bg} ${statusCfg.color} mb-4`}>
                <StatusIcon className={`h-3 w-3 ${trip.status === "planning" ? "animate-spin" : ""}`} />
                {statusCfg.label}
              </span>
              <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-2">
                {destination === "TBD" ? "Trip in Planning" : `${origin} → ${destination}`}
              </h1>
              {summary && (
                <p className="text-muted-foreground text-sm leading-relaxed max-w-2xl mt-3">{summary}</p>
              )}
            </div>
            {trip.status !== "completed" && (
              <button
                onClick={() => router.push(`/dashboard/trips/new?tripId=${trip.id}`)}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl glass border border-white/10 hover:border-primary/30 text-sm font-medium transition-all"
              >
                <Compass className="h-4 w-4 text-primary" /> Continue Planning
              </button>
            )}
          </div>

          {/* Stats Row */}
          <div className="flex flex-wrap gap-4 mt-6">
            {days > 0 && (
              <div className="flex items-center gap-2 text-sm">
                <Calendar className="h-4 w-4 text-primary/70" />
                <span className="font-medium">{days} Days</span>
              </div>
            )}
            {travelers > 0 && (
              <div className="flex items-center gap-2 text-sm">
                <Users className="h-4 w-4 text-cyan-400/70" />
                <span className="font-medium">{travelers} {travelers === 1 ? "Traveler" : "Travelers"}</span>
              </div>
            )}
            {budget > 0 && (
              <div className="flex items-center gap-2 text-sm">
                <DollarSign className="h-4 w-4 text-emerald-400/70" />
                <span className="font-medium">₹{budget.toLocaleString("en-IN")} Budget</span>
              </div>
            )}
            {origin && origin !== "TBD" && (
              <div className="flex items-center gap-2 text-sm">
                <Plane className="h-4 w-4 text-violet-400/70" />
                <span className="font-medium">From {origin}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Not yet completed */}
      {trip.status !== "completed" && (
        <div className="glass rounded-2xl border border-white/5 p-8 text-center">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mx-auto mb-4 animate-float">
            <Sparkles className="h-8 w-8 text-primary/60" />
          </div>
          <h2 className="text-xl font-bold mb-2">
            {trip.status === "planning" ? "Agents are working..." :
             trip.status === "awaiting_approval" ? "Your Approval Is Needed" :
             trip.status === "pending" ? "Trip is queued" :
             "Planning incomplete"}
          </h2>
          <p className="text-muted-foreground text-sm mb-6 max-w-sm mx-auto">
            {trip.status === "planning"
              ? "Our AI agents are currently researching your destination, finding the best hotels and transport options."
              : trip.status === "awaiting_approval"
              ? "The agents found some great options but need your approval before finalizing the itinerary."
              : "This trip has not been fully planned yet. Go back to the trip planner to continue."}
          </p>
          <button
            onClick={() => router.push(`/dashboard/trips/new?tripId=${trip.id}`)}
            className="px-5 py-2.5 rounded-xl bg-primary text-white font-semibold hover:bg-primary/90 glow-primary-sm transition-all hover:scale-105"
          >
            {trip.status === "awaiting_approval" ? "Review & Approve" : "Continue Planning"}
          </button>
        </div>
      )}

      {/* COMPLETED: Full itinerary + budget */}
      {trip.status === "completed" && (
        <>
          {/* Budget Breakdown */}
          {budgetCategories.length > 0 && (
            <div className="glass rounded-2xl border border-white/5 overflow-hidden">
              <div className="p-5 border-b border-white/5">
                <h2 className="font-semibold flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-primary" /> Budget Breakdown
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">Total: ₹{totalBudget.toLocaleString("en-IN")}</p>
              </div>
              {/* Progress bars */}
              <div className="p-5 space-y-4">
                {budgetCategories.map((cat, i) => {
                  const pct = totalBudget > 0 ? Math.round((cat.amount / totalBudget) * 100) : 0;
                  return (
                    <div key={cat.label}>
                      <div className="flex items-center justify-between text-sm mb-1.5">
                        <span className="font-medium">{cat.label}</span>
                        <span className="text-muted-foreground">₹{cat.amount.toLocaleString("en-IN")} ({pct}%)</span>
                      </div>
                      <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                        <div
                          className={`h-full rounded-full bg-gradient-to-r ${cat.color} transition-all duration-1000`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Hotels */}
          {hotels.length > 0 && (
            <div className="glass rounded-2xl border border-white/5 overflow-hidden">
              <div className="p-5 border-b border-white/5">
                <h2 className="font-semibold flex items-center gap-2">
                  <Hotel className="h-4 w-4 text-cyan-400" /> Hotel Options
                </h2>
              </div>
              <div className="p-5 grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {hotels.slice(0, 3).map((hotel: any, i: number) => (
                  <div key={i} className="glass rounded-xl border border-white/5 p-4 hover:border-white/10 transition-all">
                    <div className="flex items-start justify-between mb-2">
                      <p className="font-semibold text-sm leading-tight">{hotel.name || "Hotel Option"}</p>
                      {hotel.rating && (
                        <div className="flex items-center gap-0.5 text-amber-400 flex-shrink-0">
                          <Star className="h-3 w-3 fill-current" />
                          <span className="text-xs">{hotel.rating}</span>
                        </div>
                      )}
                    </div>
                    {hotel.location && <p className="text-xs text-muted-foreground mb-2">{hotel.location}</p>}
                    {hotel.price_per_night_inr && (
                      <p className="text-primary text-sm font-semibold">₹{hotel.price_per_night_inr.toLocaleString("en-IN")}/night</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Day-by-Day Itinerary */}
          {itinerary.length > 0 && (
            <div className="glass rounded-2xl border border-white/5 overflow-hidden">
              <div className="p-5 border-b border-white/5">
                <h2 className="font-semibold flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-violet-400" /> Day-by-Day Itinerary
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">{itinerary.length} days planned</p>
              </div>
              <div className="divide-y divide-white/5">
                {itinerary.map((day: any, idx: number) => (
                  <div key={idx} className="transition-all">
                    {/* Day header */}
                    <button
                      onClick={() => setExpandedDay(expandedDay === idx ? null : idx)}
                      className="w-full flex items-center gap-4 p-5 hover:bg-white/2 transition-colors text-left"
                    >
                      <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500/20 to-indigo-500/20 border border-violet-500/20 flex items-center justify-center">
                        <span className="text-primary font-bold text-sm">{day.day || idx + 1}</span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold">{day.title || `Day ${idx + 1}`}</p>
                        {day.activities?.length > 0 && (
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {day.activities.length} activities
                            {day.meals?.length > 0 && ` · ${day.meals.length} meals`}
                          </p>
                        )}
                      </div>
                      {expandedDay === idx ? (
                        <ChevronUp className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                      )}
                    </button>

                    {/* Day expanded content */}
                    {expandedDay === idx && (
                      <div className="px-5 pb-5 space-y-4">
                        {/* Activities */}
                        {day.activities?.length > 0 && (
                          <div className="space-y-2">
                            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Activities</p>
                            {day.activities.map((act: any, ai: number) => (
                              <div key={ai} className="flex items-start gap-3 p-3 glass rounded-xl border border-white/5">
                                <div className="flex-shrink-0 p-1.5 rounded-lg bg-violet-500/10">
                                  <Compass className="h-3.5 w-3.5 text-violet-400" />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-medium">{act.activity || act.description}</p>
                                  {act.location && (
                                    <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                                      <Map className="h-3 w-3" /> {act.location}
                                    </p>
                                  )}
                                </div>
                                {act.cost_inr > 0 && (
                                  <span className="text-xs text-emerald-400 font-medium flex-shrink-0">
                                    ₹{act.cost_inr.toLocaleString("en-IN")}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Meals */}
                        {day.meals?.length > 0 && (
                          <div className="space-y-2">
                            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Meals</p>
                            {day.meals.map((meal: any, mi: number) => (
                              <div key={mi} className="flex items-start gap-3 p-3 glass rounded-xl border border-white/5">
                                <div className="flex-shrink-0 p-1.5 rounded-lg bg-amber-500/10">
                                  <Utensils className="h-3.5 w-3.5 text-amber-400" />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-medium">{meal.suggestion || meal.description}</p>
                                  {meal.time && (
                                    <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                                      <Clock className="h-3 w-3" /> {meal.time}
                                    </p>
                                  )}
                                </div>
                                {meal.estimated_cost_inr > 0 && (
                                  <span className="text-xs text-amber-400 font-medium flex-shrink-0">
                                    ₹{meal.estimated_cost_inr.toLocaleString("en-IN")}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Tips */}
                        {day.tips?.length > 0 && (
                          <div className="p-3 rounded-xl bg-primary/5 border border-primary/10">
                            <p className="text-xs font-semibold text-primary mb-1.5">💡 Tips for the day</p>
                            <ul className="space-y-1">
                              {day.tips.map((tip: string, ti: number) => (
                                <li key={ti} className="text-xs text-muted-foreground">• {tip}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* No itinerary available yet */}
          {itinerary.length === 0 && trip.status === "completed" && (
            <div className="glass rounded-2xl border border-white/5 p-8 text-center">
              <p className="text-muted-foreground">Itinerary details are not available for this trip.</p>
            </div>
          )}

          {/* Export actions */}
          <div className="flex flex-wrap gap-3">
            <button
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl glass border border-white/10 hover:border-primary/20 text-sm font-medium transition-all"
              onClick={async () => {
                try {
                  const res = await api.request<any>(`/api/v1/trips/${id}/export/pdf`, { headers: { Accept: "application/pdf" } });
                  const url = URL.createObjectURL(res);
                  const a = document.createElement("a"); a.href = url; a.download = `trip-${id.slice(0,8)}.pdf`; a.click();
                } catch { alert("PDF export not available yet."); }
              }}
            >
              <Download className="h-4 w-4" /> Download PDF
            </button>
            <button
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl glass border border-white/10 hover:border-primary/20 text-sm font-medium transition-all"
              onClick={async () => {
                await navigator.clipboard.writeText(window.location.href);
                alert("Link copied to clipboard!");
              }}
            >
              <Share2 className="h-4 w-4" /> Share Link
            </button>
          </div>
        </>
      )}
    </div>
  );
}
