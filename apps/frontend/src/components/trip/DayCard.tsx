import { ChevronDown, ChevronUp, MapPin, Clock, Utensils, Info } from "lucide-react"
import { Card, CardHeader, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export interface DayPlan {
  day: number
  title: string
  activities: { time: string; activity: string; location: string; cost_inr: number }[]
  meals: { time: string; suggestion: string; estimated_cost_inr: number }[]
  tips: string[]
}

interface DayCardProps {
  day: DayPlan
  isExpanded: boolean
  onToggle: () => void
}

export function DayCard({ day, isExpanded, onToggle }: DayCardProps) {
  return (
    <Card className="overflow-hidden transition-all duration-200">
      <CardHeader 
        className="p-4 bg-muted/30 cursor-pointer flex flex-row items-center justify-between"
        onClick={onToggle}
      >
        <div className="flex items-center gap-4">
          <div className="bg-primary text-primary-foreground font-bold h-10 w-10 rounded-full flex items-center justify-center shrink-0">
            D{day.day}
          </div>
          <div>
            <h3 className="font-semibold text-lg leading-tight">{day.title}</h3>
            <p className="text-sm text-muted-foreground flex items-center gap-1 mt-0.5">
              <MapPin className="h-3 w-3" /> {day.activities.length} locations • {day.meals.length} meals
            </p>
          </div>
        </div>
        <Button variant="ghost" size="icon" className="shrink-0">
          {isExpanded ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
        </Button>
      </CardHeader>

      {isExpanded && (
        <CardContent className="p-0 border-t">
          <div className="p-4 space-y-6">
            
            {/* Activities Section */}
            <div>
              <h4 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center">
                <Clock className="w-4 h-4 mr-2" /> Itinerary
              </h4>
              <div className="space-y-4 relative before:absolute before:inset-0 before:ml-2 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-border before:to-transparent">
                {day.activities.map((act, i) => (
                  <div key={i} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                    {/* Marker */}
                    <div className="flex items-center justify-center w-5 h-5 rounded-full border-2 border-primary bg-background shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow" />
                    
                    {/* Content */}
                    <div className="w-[calc(100%-2rem)] md:w-[calc(50%-1.5rem)] p-3 rounded-lg border bg-card shadow-sm hover:shadow-md transition-shadow">
                      <div className="flex items-center justify-between mb-1">
                        <Badge variant="outline" className="font-mono text-xs">{act.time}</Badge>
                        {act.cost_inr > 0 && <span className="text-xs font-medium text-green-600">₹{act.cost_inr}</span>}
                      </div>
                      <h5 className="font-semibold text-sm mb-1">{act.activity}</h5>
                      <p className="text-xs text-muted-foreground flex items-start gap-1">
                        <MapPin className="w-3 h-3 mt-0.5 shrink-0" /> {act.location}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Meals Section */}
            {day.meals.length > 0 && (
              <div className="bg-orange-50/50 dark:bg-orange-950/10 rounded-lg p-4 border border-orange-100 dark:border-orange-900/30">
                <h4 className="text-sm font-semibold uppercase tracking-wider text-orange-600/80 dark:text-orange-400/80 mb-3 flex items-center">
                  <Utensils className="w-4 h-4 mr-2" /> Dining Suggestions
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {day.meals.map((meal, i) => (
                    <div key={i} className="bg-background rounded border p-2 text-sm flex justify-between items-center shadow-sm">
                      <div>
                        <span className="text-xs font-semibold text-muted-foreground block">{meal.time}</span>
                        <span>{meal.suggestion}</span>
                      </div>
                      <Badge variant="secondary" className="font-mono bg-orange-100 text-orange-700 hover:bg-orange-100 dark:bg-orange-900 dark:text-orange-300">
                        ₹{meal.estimated_cost_inr}
                      </Badge>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Tips Section */}
            {day.tips.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center">
                  <Info className="w-4 h-4 mr-2" /> Daily Tips
                </h4>
                <ul className="text-sm space-y-1 text-muted-foreground bg-muted/30 p-3 rounded-lg">
                  {day.tips.map((tip, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="text-primary">•</span> {tip}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            
          </div>
        </CardContent>
      )}
    </Card>
  )
}
