"use client";
import { useState } from "react"
import { DayCard, DayPlan } from "./DayCard"
import { BudgetBreakdown } from "./BudgetBreakdown"
import { Button } from "@/components/ui/button"
import { Download, Share2, Calendar } from "lucide-react"
import { api } from "@/lib/api"

interface Props {
  tripId: string
  itinerary: DayPlan[]
  budgetBreakdown?: {
    category: string
    amount: number
    percentage: number
  }[]
  totalCost?: number
  summary: string
}

export function ItineraryView({ tripId, itinerary, budgetBreakdown, totalCost, summary }: Props) {
  const [expandedDay, setExpandedDay] = useState<number | null>(0)
  const [isExporting, setIsExporting] = useState(false)

  const handleDownloadPDF = async () => {
    try {
      setIsExporting(true)
      const blob = await api.request<Blob>(`/api/v1/trips/${tripId}/export/pdf`, {
        headers: { Accept: "application/pdf" },
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `trip-${tripId.slice(0, 8)}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      console.error("Failed to download PDF", error)
      alert("Failed to generate PDF. Please try again later.")
    } finally {
      setIsExporting(false)
    }
  }

  const handleShareLink = async () => {
    try {
      const { share_url } = await api.post<{ share_url: string }>(`/api/v1/trips/${tripId}/share`)
      await navigator.clipboard.writeText(share_url)
      alert("Share link copied to clipboard!")
    } catch (error) {
      console.error("Failed to generate share link", error)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Summary */}
      <div className="bg-gradient-to-r from-indigo-500 to-purple-600 rounded-2xl p-6 text-white shadow-lg">
        <h2 className="text-2xl font-bold mb-2">Your Trip Itinerary</h2>
        <p className="text-indigo-100">{summary}</p>
      </div>

      {/* Action buttons */}
      <div className="flex flex-wrap gap-3">
        <Button onClick={handleDownloadPDF} variant="outline" disabled={isExporting} className="shadow-sm">
          <Download className="h-4 w-4 mr-2" /> 
          {isExporting ? "Generating PDF..." : "Download PDF"}
        </Button>
        <Button onClick={handleShareLink} variant="outline" className="shadow-sm">
          <Share2 className="h-4 w-4 mr-2" /> Share Link
        </Button>
        <Button variant="outline" className="shadow-sm">
          <Calendar className="h-4 w-4 mr-2" /> Add to Calendar
        </Button>
      </div>

      {/* Budget breakdown */}
      {budgetBreakdown && totalCost && (
        <BudgetBreakdown breakdown={budgetBreakdown} total={totalCost} />
      )}

      {/* Day-by-day itinerary */}
      <div className="space-y-4">
        {itinerary.map((day, index) => (
          <DayCard
            key={day.day}
            day={day}
            isExpanded={expandedDay === index}
            onToggle={() => setExpandedDay(expandedDay === index ? null : index)}
          />
        ))}
      </div>
    </div>
  )
}
