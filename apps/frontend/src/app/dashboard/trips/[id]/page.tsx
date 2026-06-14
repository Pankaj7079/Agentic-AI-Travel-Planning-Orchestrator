"use client";
import { useEffect, useState, use } from "react"
import { useRouter } from "next/navigation"
import { ArrowLeft, Edit } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ItineraryView } from "@/components/trip/ItineraryView"
import { api } from "@/lib/api"
import { DayPlan } from "@/components/trip/DayCard"

interface TripDetail {
  id: string
  status: string
  request: {
    origin: string
    destination: string
    days: number
    budget_inr: number
    travelers: number
    start_date?: string | null
  }
  result?: {
    itinerary?: any[]
    budget_breakdown?: {
      transport_inr: number
      accommodation_inr: number
      food_inr: number
      activities_inr: number
      misc_inr: number
      total_inr: number
    }
    summary?: string
  } | null
  total_cost_usd: number
}

// Ensure the page takes params correctly for Next.js app router
export default function TripDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter()
  // React 19 uses 'use()' to unwrap params
  const { id } = use(params)
  
  const [trip, setTrip] = useState<TripDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadTrip() {
      try {
        const data = await api.get<TripDetail>(`/api/v1/trips/${id}`)
        setTrip(data)
      } catch (err: any) {
        setError(err.message || "Failed to load trip")
      } finally {
        setLoading(false)
      }
    }
    loadTrip()
  }, [id])

  if (loading) {
    return (
      <div className="flex justify-center items-center h-full min-h-[500px]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  if (error || !trip) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[500px] text-center">
        <h2 className="text-2xl font-bold mb-2">Trip Not Found</h2>
        <p className="text-muted-foreground mb-6">{error || "The trip you are looking for does not exist."}</p>
        <Button onClick={() => router.push("/dashboard/trips")}>Return to Trips</Button>
      </div>
    )
  }

  // Map the backend itinerary JSON to the expected DayPlan format
  const itineraryDays: DayPlan[] = trip.result?.itinerary?.map((d: any, idx: number) => ({
    day: d.day || idx + 1,
    title: d.title || `Day ${idx + 1}`,
    activities: d.activities?.map((a: any) => ({
      time: a.time || "TBD",
      activity: a.activity || a.description || "TBD",
      location: a.location || "TBD",
      cost_inr: a.cost_inr || a.cost || 0
    })) || [],
    meals: d.meals?.map((m: any) => ({
      time: m.time || "Meal",
      suggestion: m.suggestion || m.description || "TBD",
      estimated_cost_inr: m.estimated_cost_inr || m.cost || 0
    })) || [],
    tips: d.tips || []
  })) || []

  // Map the actual budget breakdown if available
  const totalCost = trip.result?.budget_breakdown?.total_inr || trip.request?.budget_inr || 0;
  const breakdownData = trip.result?.budget_breakdown;
  const budgetBreakdown = breakdownData ? [
    { category: "Flights/Transport", amount: breakdownData.transport_inr, percentage: totalCost > 0 ? Math.round((breakdownData.transport_inr / totalCost) * 100) : 0 },
    { category: "Accommodation", amount: breakdownData.accommodation_inr, percentage: totalCost > 0 ? Math.round((breakdownData.accommodation_inr / totalCost) * 100) : 0 },
    { category: "Food & Dining", amount: breakdownData.food_inr, percentage: totalCost > 0 ? Math.round((breakdownData.food_inr / totalCost) * 100) : 0 },
    { category: "Activities", amount: breakdownData.activities_inr, percentage: totalCost > 0 ? Math.round((breakdownData.activities_inr / totalCost) * 100) : 0 },
    { category: "Miscellaneous", amount: breakdownData.misc_inr, percentage: totalCost > 0 ? Math.round((breakdownData.misc_inr / totalCost) * 100) : 0 },
  ] : [
    { category: "Flights/Transport", amount: totalCost * 0.4, percentage: 40 },
    { category: "Accommodation", amount: totalCost * 0.3, percentage: 30 },
    { category: "Food & Dining", amount: totalCost * 0.15, percentage: 15 },
    { category: "Activities", amount: totalCost * 0.1, percentage: 10 },
    { category: "Miscellaneous", amount: totalCost * 0.05, percentage: 5 },
  ]

  return (
    <div className="flex flex-col gap-6 w-full max-w-5xl mx-auto pb-8">
      <div className="flex items-center justify-between">
        <Button variant="ghost" onClick={() => router.push("/dashboard/trips")} className="pl-0 gap-2">
          <ArrowLeft className="h-4 w-4" /> Back to Trips
        </Button>
        {trip.status !== "completed" && (
          <Button variant="outline" className="gap-2" onClick={() => router.push(`/dashboard/trips/new?tripId=${trip.id}`)}>
            <Edit className="h-4 w-4" /> Continue Planning
          </Button>
        )}
      </div>

      <ItineraryView 
        tripId={id}
        itinerary={itineraryDays}
        budgetBreakdown={budgetBreakdown}
        totalCost={totalCost}
        summary={trip.result?.summary || `A ${itineraryDays.length || trip.request?.days || 3}-day trip to ${trip.request?.destination || 'your selected destination'}.`}
      />
    </div>
  )
}
