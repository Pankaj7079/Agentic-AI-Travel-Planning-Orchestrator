import { Badge } from "@/components/ui/badge"
import { Loader2, CheckCircle2, XCircle, Clock } from "lucide-react"
import { cn } from "@/lib/utils"

export interface AgentStatus {
  name: string
  status: "queued" | "running" | "completed" | "failed"
  message: string
}

export function AgentProgress({ agents }: { agents: AgentStatus[] }) {
  if (!agents || agents.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2 p-3 bg-muted/50 border-b">
      {agents.map((agent) => {
        let icon
        let variant: "default" | "secondary" | "destructive" | "outline" = "secondary"
        
        switch (agent.status) {
          case "running":
            icon = <Loader2 className="w-3 h-3 mr-1 animate-spin" />
            variant = "default"
            break
          case "completed":
            icon = <CheckCircle2 className="w-3 h-3 mr-1 text-green-500" />
            variant = "outline"
            break
          case "failed":
            icon = <XCircle className="w-3 h-3 mr-1" />
            variant = "destructive"
            break
          default:
            icon = <Clock className="w-3 h-3 mr-1 opacity-50" />
            variant = "secondary"
        }

        return (
          <Badge 
            key={agent.name} 
            variant={variant}
            className={cn("flex items-center text-xs py-1", 
              agent.status === "completed" ? "bg-green-500/10 text-green-700 border-green-200" : ""
            )}
          >
            {icon}
            {agent.name}
          </Badge>
        )
      })}
    </div>
  )
}
