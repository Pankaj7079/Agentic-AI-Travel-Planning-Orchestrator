import { create } from "zustand";

interface AgentStatus {
  name: string;
  status: "queued" | "running" | "completed" | "failed";
  message: string;
}

interface TripState {
  activeTripId: string | null;
  agentStatuses: AgentStatus[];
  setActiveTrip: (id: string) => void;
  updateAgentStatus: (status: AgentStatus) => void;
  clearTrip: () => void;
}

export const useTripStore = create<TripState>((set) => ({
  activeTripId: null,
  agentStatuses: [],
  setActiveTrip: (id) => set({ activeTripId: id, agentStatuses: [] }),
  updateAgentStatus: (newStatus) =>
    set((state) => {
      const existing = state.agentStatuses.findIndex((s) => s.name === newStatus.name);
      if (existing >= 0) {
        const updated = [...state.agentStatuses];
        updated[existing] = newStatus;
        return { agentStatuses: updated };
      }
      return { agentStatuses: [...state.agentStatuses, newStatus] };
    }),
  clearTrip: () => set({ activeTripId: null, agentStatuses: [] }),
}));
