import { useState, useRef, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Mic, Square } from "lucide-react"
import { cn } from "@/lib/utils"

interface VoiceButtonProps {
  onTranscript: (text: string) => void
}

export function VoiceButton({ onTranscript }: VoiceButtonProps) {
  const [isRecording, setIsRecording] = useState(false)
  const recognitionRef = useRef<any>(null)

  useEffect(() => {
    // Setup Web Speech API as a fallback if LiveKit is not used
    if (typeof window !== "undefined" && ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)) {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      recognitionRef.current = new SpeechRecognition()
      recognitionRef.current.continuous = false
      recognitionRef.current.interimResults = false

      recognitionRef.current.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript
        if (transcript) {
          onTranscript(transcript)
        }
        setIsRecording(false)
      }

      recognitionRef.current.onerror = () => {
        setIsRecording(false)
      }

      recognitionRef.current.onend = () => {
        setIsRecording(false)
      }
    }
  }, [onTranscript])

  const toggleRecording = () => {
    if (isRecording) {
      recognitionRef.current?.stop()
      setIsRecording(false)
    } else {
      if (recognitionRef.current) {
        recognitionRef.current.start()
        setIsRecording(true)
      } else {
        alert("Speech recognition is not supported in this browser.")
      }
    }
  }

  return (
    <Button
      variant={isRecording ? "destructive" : "secondary"}
      size="icon"
      className={cn("rounded-full transition-all duration-300", isRecording ? "animate-pulse shadow-[0_0_15px_rgba(239,68,68,0.6)]" : "")}
      onClick={toggleRecording}
      type="button"
    >
      {isRecording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
    </Button>
  )
}
