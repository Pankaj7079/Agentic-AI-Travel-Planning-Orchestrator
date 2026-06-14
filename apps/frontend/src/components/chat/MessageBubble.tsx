import { cn } from "@/lib/utils"

export interface Message {
  id: string
  role: "user" | "agent" | "system"
  content: string
  agent?: string
  timestamp: Date
}

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user"
  const isSystem = message.role === "system"

  if (isSystem) {
    return (
      <div className="flex justify-center my-4">
        <span className="text-xs text-muted-foreground bg-muted px-3 py-1 rounded-full">
          {message.content}
        </span>
      </div>
    )
  }

  return (
    <div className={cn("flex w-full mb-4", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-3 shadow-sm",
          isUser
            ? "bg-primary text-primary-foreground rounded-br-sm"
            : "bg-muted text-foreground rounded-bl-sm"
        )}
      >
        {!isUser && message.agent && (
          <div className="text-xs font-semibold text-primary mb-1">
            {message.agent}
          </div>
        )}
        <div className="text-sm whitespace-pre-wrap">{message.content}</div>
        <div
          className={cn(
            "text-[10px] mt-1 text-right",
            isUser ? "text-primary-foreground/70" : "text-muted-foreground"
          )}
        >
          {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  )
}
