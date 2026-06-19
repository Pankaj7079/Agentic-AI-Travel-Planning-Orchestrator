"use client";
import { useState } from "react";
import {
  ChevronDown, ChevronUp, MapPin, Clock,
  Utensils, Lightbulb, IndianRupee, Sun, Sunset, Moon
} from "lucide-react";

export interface DayActivity {
  time: string;
  activity: string;
  location: string;
  cost_inr: number;
}

export interface DayMeal {
  time: string;
  suggestion: string;
  estimated_cost_inr: number;
}

export interface DayPlan {
  day: number;
  title: string;
  activities: DayActivity[];
  meals: DayMeal[];
  tips: string[];
}

interface DayCardProps {
  day: DayPlan;
  isExpanded: boolean;
  onToggle: () => void;
}

// Map time of day to a color accent
const getTimeStyle = (time: string) => {
  const t = time.toLowerCase();
  if (t.includes("am") || t.includes("morning") || t.includes("6:") || t.includes("7:") || t.includes("8:") || t.includes("9:") || t.includes("10:") || t.includes("11:")) {
    return { icon: Sun, color: "text-amber-400", bg: "bg-amber-400/10 border-amber-400/20" };
  }
  if (t.includes("pm") && (t.includes("12:") || t.includes("1:") || t.includes("2:") || t.includes("3:") || t.includes("4:") || t.includes("5:"))) {
    return { icon: Sunset, color: "text-orange-400", bg: "bg-orange-400/10 border-orange-400/20" };
  }
  return { icon: Moon, color: "text-indigo-400", bg: "bg-indigo-400/10 border-indigo-400/20" };
};

// Sequential day accent colors
const DAY_ACCENTS = [
  { from: "from-violet-500", to: "to-indigo-500", light: "text-violet-400", badge: "bg-violet-500/15 text-violet-300 border-violet-500/25" },
  { from: "from-cyan-500", to: "to-blue-500", light: "text-cyan-400", badge: "bg-cyan-500/15 text-cyan-300 border-cyan-500/25" },
  { from: "from-emerald-500", to: "to-teal-500", light: "text-emerald-400", badge: "bg-emerald-500/15 text-emerald-300 border-emerald-500/25" },
  { from: "from-amber-500", to: "to-orange-500", light: "text-amber-400", badge: "bg-amber-500/15 text-amber-300 border-amber-500/25" },
  { from: "from-rose-500", to: "to-pink-500", light: "text-rose-400", badge: "bg-rose-500/15 text-rose-300 border-rose-500/25" },
];

export function DayCard({ day, isExpanded, onToggle }: DayCardProps) {
  const accent = DAY_ACCENTS[(day.day - 1) % DAY_ACCENTS.length];
  const totalActivitiesCost = day.activities.reduce((s, a) => s + (a.cost_inr || 0), 0);
  const totalMealsCost = day.meals.reduce((s, m) => s + (m.estimated_cost_inr || 0), 0);
  const dayTotal = totalActivitiesCost + totalMealsCost;

  return (
    <div className={`glass-card rounded-2xl overflow-hidden transition-all duration-300 ${isExpanded ? "shadow-lg" : ""}`}>
      {/* ── HEADER ── */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-4 p-4 hover:bg-white/3 transition-colors text-left group"
      >
        {/* Day badge */}
        <div className={`
          flex-shrink-0 w-11 h-11 rounded-xl bg-gradient-to-br ${accent.from} ${accent.to}
          flex flex-col items-center justify-center shadow-md
        `}>
          <span className="text-white text-[10px] font-semibold leading-none opacity-80">DAY</span>
          <span className="text-white text-lg font-bold leading-none">{day.day}</span>
        </div>

        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-base leading-tight truncate pr-2">{day.title}</h3>
          <div className="flex items-center gap-3 mt-1 flex-wrap">
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" /> {day.activities.length} stops
            </span>
            {day.meals.length > 0 && (
              <span className="flex items-center gap-1 text-xs text-muted-foreground">
                <Utensils className="h-3 w-3" /> {day.meals.length} meals
              </span>
            )}
            {dayTotal > 0 && (
              <span className="flex items-center gap-1 text-xs font-medium text-emerald-400">
                <IndianRupee className="h-3 w-3" />₹{dayTotal.toLocaleString("en-IN")} est.
              </span>
            )}
          </div>
        </div>

        <div className={`flex-shrink-0 p-1.5 rounded-lg glass border border-white/5 ${accent.light} transition-transform ${isExpanded ? "rotate-180" : ""} group-hover:border-white/10`}>
          <ChevronDown className="h-4 w-4" />
        </div>
      </button>

      {/* ── EXPANDED CONTENT ── */}
      {isExpanded && (
        <div className="border-t border-white/5 p-4 space-y-6 anim-slide-up">

          {/* Activities Timeline */}
          {day.activities.length > 0 && (
            <div>
              <h4 className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-muted-foreground mb-4">
                <Clock className="h-3.5 w-3.5" /> Day Itinerary
              </h4>
              <div className="space-y-3 pl-2">
                {day.activities.map((act, i) => {
                  const ts = getTimeStyle(act.time);
                  return (
                    <div key={i} className="relative flex gap-3">
                      {/* Timeline line */}
                      {i < day.activities.length - 1 && (
                        <div className="absolute left-3.5 top-8 bottom-0 w-px bg-gradient-to-b from-white/10 to-transparent" />
                      )}

                      {/* Time icon */}
                      <div className={`flex-shrink-0 w-7 h-7 rounded-lg border ${ts.bg} flex items-center justify-center mt-0.5`}>
                        <ts.icon className={`h-3.5 w-3.5 ${ts.color}`} />
                      </div>

                      {/* Content */}
                      <div className="flex-1 glass rounded-xl border border-white/5 p-3 hover:border-white/10 transition-colors">
                        <div className="flex items-start justify-between gap-2 flex-wrap">
                          <div>
                            <span className={`text-[11px] font-mono font-semibold ${ts.color}`}>{act.time}</span>
                            <h5 className="font-semibold text-sm mt-0.5 leading-snug">{act.activity}</h5>
                            <p className="flex items-center gap-1 text-xs text-muted-foreground mt-1">
                              <MapPin className="h-3 w-3 flex-shrink-0" />
                              {act.location}
                            </p>
                          </div>
                          {act.cost_inr > 0 && (
                            <span className="flex-shrink-0 px-2 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-semibold">
                              ₹{act.cost_inr.toLocaleString("en-IN")}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Meals */}
          {day.meals.length > 0 && (
            <div>
              <h4 className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-muted-foreground mb-3">
                <Utensils className="h-3.5 w-3.5" /> Dining Suggestions
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {day.meals.map((meal, i) => (
                  <div key={i} className="flex items-center justify-between gap-3 glass rounded-xl border border-white/5 p-3">
                    <div>
                      <span className="text-[11px] font-semibold text-amber-400 uppercase tracking-wide block">{meal.time}</span>
                      <span className="text-sm font-medium">{meal.suggestion}</span>
                    </div>
                    {meal.estimated_cost_inr > 0 && (
                      <span className="flex-shrink-0 px-2 py-1 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-semibold whitespace-nowrap">
                        ₹{meal.estimated_cost_inr.toLocaleString("en-IN")}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tips */}
          {day.tips.length > 0 && (
            <div>
              <h4 className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-muted-foreground mb-3">
                <Lightbulb className="h-3.5 w-3.5" /> Pro Tips
              </h4>
              <ul className="space-y-2">
                {day.tips.map((tip, i) => (
                  <li key={i} className="flex gap-2.5 text-sm text-muted-foreground">
                    <span className="flex-shrink-0 w-5 h-5 rounded-full bg-primary/15 border border-primary/20 flex items-center justify-center text-primary text-[10px] font-bold mt-0.5">
                      {i + 1}
                    </span>
                    {tip}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Day total */}
          {dayTotal > 0 && (
            <div className="flex items-center justify-between pt-3 border-t border-white/5">
              <span className="text-xs text-muted-foreground">Estimated day spend</span>
              <span className="font-bold text-emerald-400">₹{dayTotal.toLocaleString("en-IN")}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
