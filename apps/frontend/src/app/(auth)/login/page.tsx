"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PlaneTakeoff, ArrowRight, Eye, EyeOff, Mail, Lock, Compass, Map, Brain } from "lucide-react";
import { useAuthStore } from "@/stores/authStore";

const getBaseUrl = () => {
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
};

const FEATURES = [
  { icon: Brain, text: "Multi-agent AI planning" },
  { icon: Compass, text: "Voice-enabled trip assistant" },
  { icon: Map, text: "Real-time itinerary builder" },
];

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();
  const { setAuth } = useAuthStore();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const BASE_URL = getBaseUrl();
      const response = await fetch(`${BASE_URL}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        const detail = errData.detail;
        if (Array.isArray(detail)) {
          throw new Error(detail.map((d: any) => d.msg).join(", "));
        }
        throw new Error(typeof detail === "string" ? detail : "Invalid email or password");
      }

      const data = await response.json();
      const accessToken = data.tokens?.access_token ?? data.access_token;
      const refreshToken = data.tokens?.refresh_token ?? data.refresh_token;

      // Fetch user profile
      let user = data.user;
      if (!user) {
        const profileRes = await fetch(`${BASE_URL}/api/v1/auth/me`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        user = profileRes.ok
          ? await profileRes.json()
          : { id: "1", email, name: "Traveler", role: "user" };
      }

      setAuth(user, accessToken, refreshToken);
      router.push("/dashboard");

    } catch (err: any) {
      setError(err.message || "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[100dvh]">
      {/* Left art panel */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden flex-col items-center justify-center p-12">
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-900/80 via-violet-900/60 to-background" />
        <div className="absolute inset-0 hero-grid opacity-30" />
        <div className="absolute w-80 h-80 rounded-full bg-indigo-600/25 blur-3xl animate-float top-10 right-10" />
        <div className="absolute w-60 h-60 rounded-full bg-pink-500/15 blur-3xl animate-float-delayed bottom-10 left-10" />

        <div className="relative z-10 text-center space-y-8">
          <div className="flex justify-center">
            <div className="p-4 rounded-2xl bg-primary/20 backdrop-blur glow-primary">
              <PlaneTakeoff className="h-12 w-12 text-primary" />
            </div>
          </div>
          <div>
            <h2 className="text-4xl font-extrabold tracking-tight mb-3">
              Welcome back to<br />
              <span className="gradient-text">PariKrama</span>
            </h2>
            <p className="text-muted-foreground text-lg">
              Your intelligent travel orchestrator awaits.
            </p>
          </div>

          <div className="space-y-3 mt-6">
            {FEATURES.map(f => (
              <div key={f.text} className="flex items-center gap-3 glass rounded-xl px-4 py-3 border border-white/5">
                <div className="p-1.5 rounded-lg bg-primary/20">
                  <f.icon className="h-4 w-4 text-primary" />
                </div>
                <span className="text-sm font-medium">{f.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right form panel */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-md space-y-8">
          {/* Logo (mobile) */}
          <Link href="/" className="flex lg:hidden items-center gap-2 justify-center mb-4">
            <PlaneTakeoff className="h-6 w-6 text-primary" />
            <span className="text-xl font-bold">PariKrama</span>
          </Link>

          <div className="space-y-2">
            <h1 className="text-3xl font-bold tracking-tight">Sign in</h1>
            <p className="text-muted-foreground">Welcome back — let&apos;s plan your next adventure.</p>
          </div>

          {error && (
            <div className="p-4 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-5">
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="email">Email</label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  required
                  className="w-full pl-10 pr-4 py-3 rounded-xl bg-secondary/50 border border-border/50 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all"
                />
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium" htmlFor="password">Password</label>
                <Link href="#" className="text-xs text-primary hover:underline">Forgot password?</Link>
              </div>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="Your password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  className="w-full pl-10 pr-12 py-3 rounded-xl bg-secondary/50 border border-border/50 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:bg-primary/90 glow-primary-sm hover:glow-primary transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:scale-[1.02]"
            >
              {loading ? (
                <span className="flex gap-1">
                  <span className="typing-dot h-2 w-2 rounded-full bg-white/80" />
                  <span className="typing-dot h-2 w-2 rounded-full bg-white/80" />
                  <span className="typing-dot h-2 w-2 rounded-full bg-white/80" />
                </span>
              ) : (
                <>Sign In <ArrowRight className="h-4 w-4" /></>
              )}
            </button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            Don&apos;t have an account?{" "}
            <Link href="/register" className="text-primary hover:underline font-medium">
              Sign up for free
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
