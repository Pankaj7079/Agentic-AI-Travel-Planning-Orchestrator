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
  title: string
  destination: string
  status: string
  itinerary: any
  budget: number
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
  // We assume the backend stores itinerary in `trip.itinerary.days`
  const itineraryDays: DayPlan[] = trip.itinerary?.days?.map((d: any, idx: number) => ({
    day: d.day_number || idx + 1,
    title: d.theme || d.title || `Day ${idx + 1}`,
    activities: d.activities?.map((a: any) => ({
      time: a.time || "TBD",
      activity: a.title || a.description,
      location: a.location || "TBD",
      cost_inr: a.cost || 0
    })) || [],
    meals: d.meals?.map((m: any) => ({
      time: m.time || "Meal",
      suggestion: m.suggestion || m.description,
      estimated_cost_inr: m.cost || 0
    })) || [],
    tips: d.tips || []
  })) || []

  // Create a mock budget breakdown if the backend just provides a total
  // Or map the actual budget breakdown if available
  const budgetBreakdown = trip.itinerary?.budget_breakdown || [
    { category: "Flights/Transport", amount: trip.budget * 0.4, percentage: 40 },
    { category: "Accommodation", amount: trip.budget * 0.3, percentage: 30 },
    { category: "Food & Dining", amount: trip.budget * 0.15, percentage: 15 },
    { category: "Activities", amount: trip.budget * 0.1, percentage: 10 },
    { category: "Miscellaneous", amount: trip.budget * 0.05, percentage: 5 },
  ]

  return (
    <div className="flex flex-col gap-6 w-full max-w-5xl mx-auto pb-8">
      <div className="flex items-center justify-between">
        <Button variant="ghost" onClick={() => router.push("/dashboard/trips")} className="pl-0 gap-2">
          <ArrowLeft className="h-4 w-4" /> Back to Trips
        </Button>
        {trip.status !== "completed" && (
          <Button variant="outline" className="gap-2">
            <Edit className="h-4 w-4" /> Continue Planning
          </Button>
        )}
      </div>

      <ItineraryView 
        tripId={id}
        itinerary={itineraryDays}
        budgetBreakdown={budgetBreakdown}
        totalCost={trip.budget || 0}
        summary={`A ${itineraryDays.length}-day trip to ${trip.destination || 'your selected destination'}.`}
      />
    </div>
  )
}
