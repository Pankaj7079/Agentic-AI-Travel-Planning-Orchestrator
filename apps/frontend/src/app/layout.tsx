import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { PariKramaChatbot } from "@/components/ui/PariKramaChatbot";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "PariKrama | Agentic AI Travel Orchestrator",
  description: "Plan your perfect trip with an intelligent AI travel advisor. Multi-agent itinerary planning with voice, budget analysis, and human-in-the-loop approvals.",
  keywords: ["AI travel planner", "itinerary builder", "agentic AI", "trip planning", "PariKrama"],
  openGraph: {
    title: "PariKrama — AI Travel Orchestrator",
    description: "Plan your perfect trip with intelligent multi-agent AI.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} h-full`}>
      <body className="min-h-full flex flex-col">
        {children}
        <PariKramaChatbot />
      </body>
    </html>
  );
}
