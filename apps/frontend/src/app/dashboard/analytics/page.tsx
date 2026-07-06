"use client";
import { useEffect, useState } from "react";
import {
  BarChart3, TrendingUp, Map, Calendar, DollarSign, Users,
  Loader2, AlertCircle, Sparkles, Plane, Clock
} from "lucide-react";
import { api } from "@/lib/api";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend
} from "recharts";

interface Trip {
  id: string;
  status: string;
  request: { destination?: string; origin?: string; days?: number; budget_inr?: number };
  result?: { budget_breakdown?: { total_inr: number } };
  created_at: string;
  planning_duration_ms?: number;
}

interface UserStats {
  total_trips: number;
  completed_trips: number;
  total_spent: number;
  avg_budget: number;
}

const COLORS = ["#8b5cf6", "#06b6d4", "#10b981", "#f59e0b", "#ef4444", "#ec4899", "#6366f1"];

export default function AnalyticsPage() {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [stats, setStats] = useState<UserStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [tripsRes, statsRes] = await Promise.all([
          api.get<{ items: Trip[] }>("/api/v1/trips?limit=50"),
          api.get<UserStats>("/api/v1/users/me/stats").catch(() => null),
        ]);
        setTrips(tripsRes.items || []);
        setStats(statsRes);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px] gap-3">
        <Loader2 className="h-5 w-5 animate-spin text-primary" />
        <span className="text-muted-foreground">Loading analytics...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-center">
        <AlertCircle className="h-8 w-8 text-rose-400 mb-3" />
        <p className="text-muted-foreground">{error}</p>
      </div>
    );
  }

  const totalTrips = stats?.total_trips || trips.length;
  const completedTrips = stats?.completed_trips || trips.filter(t => t.status === "completed").length;
  const totalSpent = stats?.total_spent || trips.reduce((sum, t) => sum + (t.result?.budget_breakdown?.total_inr || t.request?.budget_inr || 0), 0);
  const avgBudget = stats?.avg_budget || (totalTrips > 0 ? Math.round(totalSpent / totalTrips) : 0);

  // Status distribution
  const statusCounts: Record<string, number> = {};
  trips.forEach(t => { statusCounts[t.status] = (statusCounts[t.status] || 0) + 1; });
  const statusData = Object.entries(statusCounts).map(([name, value]) => ({ name, value }));

  // Destination popularity
  const destCounts: Record<string, number> = {};
  trips.forEach(t => {
    const dest = t.request?.destination || "Unknown";
    destCounts[dest] = (destCounts[dest] || 0) + 1;
  });
  const destData = Object.entries(destCounts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 7);

  // Budget over time
  const budgetOverTime = trips
    .filter(t => t.request?.budget_inr)
    .map((t, i) => ({
      trip: `Trip ${i + 1}`,
      budget: t.request.budget_inr || 0,
      destination: t.request.destination || "Unknown",
    }))
    .slice(-10);

  // Monthly trend (group by month)
  const monthlyCounts: Record<string, number> = {};
  trips.forEach(t => {
    const d = new Date(t.created_at);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    monthlyCounts[key] = (monthlyCounts[key] || 0) + 1;
  });
  const monthlyData = Object.entries(monthlyCounts)
    .map(([month, count]) => ({ month, trips: count }))
    .sort((a, b) => a.month.localeCompare(b.month))
    .slice(-6);

  return (
    <div className="max-w-6xl mx-auto space-y-6 anim-slide-up">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <BarChart3 className="h-6 w-6 text-primary" /> Analytics
        </h1>
        <p className="text-sm text-muted-foreground mt-1">Your travel planning insights</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Total Trips", value: totalTrips, icon: Map, color: "text-violet-400", bg: "bg-violet-500/10" },
          { label: "Completed", value: completedTrips, icon: Sparkles, color: "text-emerald-400", bg: "bg-emerald-500/10" },
          { label: "Total Spent", value: `₹${totalSpent.toLocaleString("en-IN")}`, icon: DollarSign, color: "text-cyan-400", bg: "bg-cyan-500/10" },
          { label: "Avg Budget", value: `₹${avgBudget.toLocaleString("en-IN")}`, icon: TrendingUp, color: "text-amber-400", bg: "bg-amber-500/10" },
        ].map(stat => (
          <div key={stat.label} className="glass rounded-2xl border border-white/5 p-5">
            <div className={`w-10 h-10 rounded-xl ${stat.bg} flex items-center justify-center mb-3`}>
              <stat.icon className={`h-5 w-5 ${stat.color}`} />
            </div>
            <p className="text-2xl font-bold">{stat.value}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{stat.label}</p>
          </div>
        ))}
      </div>

      {/* Charts Grid */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Top Destinations */}
        <div className="glass rounded-2xl border border-white/5 p-5">
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <Map className="h-4 w-4 text-primary" /> Popular Destinations
          </h3>
          {destData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={destData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <Tooltip
                  contentStyle={{ background: "rgba(0,0,0,0.8)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "12px", fontSize: 12 }}
                />
                <Bar dataKey="count" fill="#8b5cf6" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-10">No trip data yet</p>
          )}
        </div>

        {/* Status Distribution */}
        <div className="glass rounded-2xl border border-white/5 p-5">
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <Calendar className="h-4 w-4 text-cyan-400" /> Trip Status
          </h3>
          {statusData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={statusData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={90}
                  dataKey="value"
                  label={({ name, value }) => `${name}: ${value}`}
                >
                  {statusData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: "rgba(0,0,0,0.8)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "12px", fontSize: 12 }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-10">No data available</p>
          )}
        </div>

        {/* Budget Over Time */}
        <div className="glass rounded-2xl border border-white/5 p-5">
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <DollarSign className="h-4 w-4 text-emerald-400" /> Budget per Trip
          </h3>
          {budgetOverTime.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={budgetOverTime}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="destination" tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <Tooltip
                  contentStyle={{ background: "rgba(0,0,0,0.8)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "12px", fontSize: 12 }}
                  formatter={(val: number) => [`₹${val.toLocaleString("en-IN")}`, "Budget"]}
                />
                <Bar dataKey="budget" fill="#06b6d4" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-10">No budget data yet</p>
          )}
        </div>

        {/* Monthly Trend */}
        <div className="glass rounded-2xl border border-white/5 p-5">
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-amber-400" /> Monthly Activity
          </h3>
          {monthlyData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <Tooltip
                  contentStyle={{ background: "rgba(0,0,0,0.8)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "12px", fontSize: 12 }}
                />
                <Line type="monotone" dataKey="trips" stroke="#f59e0b" strokeWidth={2} dot={{ fill: "#f59e0b", r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-10">Not enough data yet</p>
          )}
        </div>
      </div>

      {/* Recent Trips Table */}
      {trips.length > 0 && (
        <div className="glass rounded-2xl border border-white/5 overflow-hidden">
          <div className="p-5 border-b border-white/5">
            <h3 className="font-semibold flex items-center gap-2">
              <Plane className="h-4 w-4 text-violet-400" /> Recent Trips
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/5 text-muted-foreground text-xs">
                  <th className="text-left px-5 py-3 font-medium">Destination</th>
                  <th className="text-left px-5 py-3 font-medium">Origin</th>
                  <th className="text-left px-5 py-3 font-medium">Days</th>
                  <th className="text-left px-5 py-3 font-medium">Budget</th>
                  <th className="text-left px-5 py-3 font-medium">Status</th>
                  <th className="text-left px-5 py-3 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {trips.slice(0, 10).map(trip => (
                  <tr key={trip.id} className="border-b border-white/5 hover:bg-white/2 transition-colors">
                    <td className="px-5 py-3 font-medium">{trip.request?.destination || "—"}</td>
                    <td className="px-5 py-3 text-muted-foreground">{trip.request?.origin || "—"}</td>
                    <td className="px-5 py-3">{trip.request?.days || "—"}</td>
                    <td className="px-5 py-3">₹{(trip.request?.budget_inr || 0).toLocaleString("en-IN")}</td>
                    <td className="px-5 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                        trip.status === "completed" ? "bg-emerald-500/15 text-emerald-400" :
                        trip.status === "planning" ? "bg-amber-500/15 text-amber-400" :
                        trip.status === "failed" ? "bg-rose-500/15 text-rose-400" :
                        "bg-white/10 text-muted-foreground"
                      }`}>
                        {trip.status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-muted-foreground text-xs">
                      {new Date(trip.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
