"use client";
import { ChatInterface } from "@/components/chat/ChatInterface";
import { ArrowLeft, Mic, Sparkles } from "lucide-react";
import Link from "next/link";

export default function NewTripPage() {
  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto w-full gap-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground text-sm mb-3 transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back to Dashboard
          </Link>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-primary" />
            Plan a New Trip
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Describe your dream destination — our AI agents will handle the rest.
          </p>
        </div>
        <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full glass border border-white/10 text-xs text-muted-foreground">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          Agents ready
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 min-h-[500px]">
        <ChatInterface />
      </div>
    </div>
  );
}
