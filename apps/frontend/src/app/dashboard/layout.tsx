"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import {
  Compass, Map, Settings, Bell, User, LogOut,
  PlaneTakeoff, ChevronRight, BarChart3, X, Menu
} from "lucide-react";
import { useAuthStore } from "@/stores/authStore";
import { useNotificationStore } from "@/stores/notificationStore";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: Compass, exact: true },
  { href: "/dashboard/trips", label: "My Trips", icon: Map },
  { href: "/dashboard/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, isAuthenticated } = useAuthStore();
  const { unreadCount } = useNotificationStore();
  const [mobileOpen, setMobileOpen] = useState(false);

  // Auth guard — redirect to login if not authenticated
  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/login");
    }
  }, [isAuthenticated, router]);

  if (!isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex gap-2 items-center text-muted-foreground">
          <span className="typing-dot h-2 w-2 rounded-full bg-primary" />
          <span className="typing-dot h-2 w-2 rounded-full bg-primary" />
          <span className="typing-dot h-2 w-2 rounded-full bg-primary" />
        </div>
      </div>
    );
  }

  const isActive = (nav: typeof NAV[0]) => {
    if (nav.exact) return pathname === nav.href;
    return pathname.startsWith(nav.href);
  };

  const initials = user?.name
    ? user.name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2)
    : "U";

  return (
    <div className="flex min-h-screen">
      {/* ── SIDEBAR ── */}
      <aside className={`
        fixed inset-y-0 left-0 z-40 flex flex-col w-64 glass border-r border-white/5
        transition-transform duration-300
        ${mobileOpen ? "translate-x-0" : "-translate-x-full"}
        lg:translate-x-0
      `}>
        {/* Logo */}
        <div className="flex h-16 items-center gap-2.5 px-5 border-b border-white/5">
          <div className="p-1.5 rounded-lg bg-primary/20">
            <PlaneTakeoff className="h-5 w-5 text-primary" />
          </div>
          <span className="font-bold text-lg tracking-tight">PariKrama</span>
          <button
            onClick={() => setMobileOpen(false)}
            className="ml-auto lg:hidden text-muted-foreground hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* User card */}
        <div className="px-4 py-4 border-b border-white/5">
          <div className="flex items-center gap-3 p-3 glass rounded-xl border border-white/5">
            <div className="relative flex-shrink-0">
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white text-sm font-bold">
                {initials}
              </div>
              <span className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-emerald-400 rounded-full border-2 border-background" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold truncate">{user?.name ?? "Traveler"}</p>
              <p className="text-xs text-muted-foreground truncate">{user?.email ?? ""}</p>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-auto py-4 px-3 space-y-1">
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest px-3 mb-3">
            Navigation
          </p>
          {NAV.map(nav => {
            const active = isActive(nav);
            return (
              <Link
                key={nav.href}
                href={nav.href}
                onClick={() => setMobileOpen(false)}
                className={`
                  flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all group
                  ${active
                    ? "bg-primary/15 text-primary border border-primary/20"
                    : "text-muted-foreground hover:text-foreground hover:bg-white/5 border border-transparent"
                  }
                `}
              >
                <nav.icon className={`h-4 w-4 flex-shrink-0 ${active ? "text-primary" : ""}`} />
                <span className="flex-1">{nav.label}</span>
                {active && <ChevronRight className="h-3.5 w-3.5 text-primary/60" />}
              </Link>
            );
          })}
        </nav>

        {/* Logout */}
        <div className="p-4 border-t border-white/5">
          <button
            onClick={() => logout()}
            className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-white/5 transition-all"
          >
            <LogOut className="h-4 w-4" />
            Sign Out
          </button>
        </div>
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* ── MAIN CONTENT ── */}
      <div className="flex-1 flex flex-col lg:pl-64 min-h-screen">
        {/* Top bar */}
        <header className="sticky top-0 z-20 flex h-16 items-center gap-4 glass border-b border-white/5 px-6">
          <button
            onClick={() => setMobileOpen(true)}
            className="lg:hidden text-muted-foreground hover:text-foreground p-2 rounded-lg hover:bg-white/5 transition-colors"
          >
            <Menu className="h-5 w-5" />
          </button>

          {/* Breadcrumb */}
          <div className="hidden sm:flex items-center gap-2 text-sm text-muted-foreground">
            <span className="text-foreground font-medium capitalize">
              {pathname.split("/").pop() || "dashboard"}
            </span>
          </div>

          <div className="ml-auto flex items-center gap-2">
            {/* Notifications */}
            <button className="relative p-2.5 rounded-xl glass border border-white/5 hover:border-white/10 text-muted-foreground hover:text-foreground transition-all">
              <Bell className="h-4 w-4" />
              {unreadCount > 0 && (
                <span className="absolute top-1.5 right-1.5 flex h-2.5 w-2.5 items-center justify-center">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-destructive opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-destructive" />
                </span>
              )}
            </button>

            {/* Avatar */}
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white text-sm font-bold cursor-pointer hover:scale-105 transition-transform glow-primary-sm">
              {initials}
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 p-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
