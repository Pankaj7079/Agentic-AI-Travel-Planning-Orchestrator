"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PlaneTakeoff, ArrowRight, Eye, EyeOff, Mail, Lock, User } from "lucide-react";
import { useAuthStore } from "@/stores/authStore";

const getBaseUrl = () => {
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
};

export default function RegisterPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();
  const { setAuth } = useAuthStore();

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    // Basic client-side validation
    if (name.trim().length < 2) {
      setError("Full name must be at least 2 characters.");
      setLoading(false);
      return;
    }

    try {
      const BASE_URL = getBaseUrl();

      let regResponse: Response;
      try {
        regResponse = await fetch(`${BASE_URL}/api/v1/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, name: name.trim() }),
        });
      } catch (networkErr: any) {
        throw new Error(
          "Cannot connect to the server. Please make sure the backend is running on port 8000 and try again."
        );
      }

      if (!regResponse.ok) {
        const errorData = await regResponse.json().catch(() => ({}));
        const detail = errorData.detail;
        if (Array.isArray(detail)) {
          throw new Error(detail.map((d: any) => d.msg).join(", "));
        }
        if (regResponse.status === 409) {
          throw new Error("An account with this email already exists. Please sign in instead.");
        }
        if (regResponse.status === 422) {
          throw new Error(typeof detail === "string" ? detail : "Please check your details: valid email, name (2+ chars), password (8+ chars).");
        }
        throw new Error(typeof detail === "string" ? detail : `Registration failed (${regResponse.status}). Please try again.`);
      }

      const regData = await regResponse.json();

      // Auto-login after registration
      let loginResponse: Response;
      try {
        loginResponse = await fetch(`${BASE_URL}/api/v1/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
      } catch {
        // Registration succeeded but auto-login failed — redirect to login
        setError("Account created! Please sign in to continue.");
        setLoading(false);
        router.push("/login");
        return;
      }

      if (!loginResponse.ok) {
        setError("Account created! Please sign in to continue.");
        setLoading(false);
        router.push("/login");
        return;
      }

      const loginData = await loginResponse.json();
      const accessToken = loginData.tokens?.access_token ?? loginData.access_token;
      const refreshToken = loginData.tokens?.refresh_token ?? loginData.refresh_token;
      const user = regData.user ?? {
        id: "new", email, name: name.trim(), role: "user" as const
      };
      setAuth(user, accessToken, refreshToken);
      router.push("/dashboard");

    } catch (err: any) {
      setError(err.message || "An unexpected error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[100dvh]">
      {/* Left art panel */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden flex-col items-center justify-center p-12">
        <div className="absolute inset-0 bg-gradient-to-br from-violet-900/80 via-indigo-900/60 to-background" />
        <div className="absolute inset-0 hero-grid opacity-30" />
        {/* Floating orbs */}
        <div className="absolute w-80 h-80 rounded-full bg-violet-600/25 blur-3xl animate-float top-10 left-10" />
        <div className="absolute w-60 h-60 rounded-full bg-cyan-500/15 blur-3xl animate-float-delayed bottom-10 right-10" />

        <div className="relative z-10 text-center space-y-6">
          <div className="flex justify-center">
            <div className="p-4 rounded-2xl bg-primary/20 backdrop-blur glow-primary">
              <PlaneTakeoff className="h-12 w-12 text-primary" />
            </div>
          </div>
          <h2 className="text-4xl font-extrabold tracking-tight">
            Start your journey<br />
            <span className="gradient-text">with PariKrama</span>
          </h2>
          <p className="text-muted-foreground text-lg max-w-sm mx-auto leading-relaxed">
            Join 50,000+ travelers who plan smarter with AI-powered itineraries.
          </p>

          <div className="grid grid-cols-2 gap-4 mt-8">
            {[
              { v: "50K+", l: "Travelers" },
              { v: "120+", l: "Countries" },
              { v: "2min", l: "Avg Plan Time" },
              { v: "99.8%", l: "Satisfaction" },
            ].map(s => (
              <div key={s.l} className="glass rounded-xl p-4 border border-white/5 text-center">
                <div className="text-2xl font-bold gradient-text">{s.v}</div>
                <div className="text-xs text-muted-foreground mt-1">{s.l}</div>
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
            <h1 className="text-3xl font-bold tracking-tight">Create your account</h1>
            <p className="text-muted-foreground">Enter your details to get started for free.</p>
          </div>

          {error && (
            <div className="p-4 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleRegister} className="space-y-5">
            {/* Name */}
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="name">Full Name</label>
              <div className="relative">
                <User className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <input
                  id="name"
                  type="text"
                  placeholder="Pankaj Singh"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  required
                  className="w-full pl-10 pr-4 py-3 rounded-xl bg-secondary/50 border border-border/50 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all"
                />
              </div>
            </div>

            {/* Email */}
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

            {/* Password */}
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="password">Password</label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="Minimum 8 characters"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  minLength={8}
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
                <>Create Account <ArrowRight className="h-4 w-4" /></>
              )}
            </button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link href="/login" className="text-primary hover:underline font-medium">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
