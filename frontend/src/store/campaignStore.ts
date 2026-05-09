import { create } from "zustand";
import { getCampaignLogs, getCampaignState, getCampaignStatus, startCampaign } from "../lib/api";
import type {
  CampaignLog,
  CampaignStartRequest,
  CampaignStateResponse,
  CampaignStatusResponse,
} from "../types";

export type UIState = "EMPTY" | "GENERATING" | "OUTPUT" | "DEBUG";

type ProgressState = {
  step: string;
  completed: string[];
};

type DebugInfo = {
  logs: CampaignLog[];
  nodes: Array<{ name: string; status: string }>;
  raw: CampaignStateResponse | null;
};

type CampaignStore = {
  campaignId: string | null;
  status: CampaignStatusResponse | null;
  campaign: CampaignStateResponse | null;
  logs: CampaignLog[];
  isLoading: boolean;
  error: string | null;
  uiState: UIState;
  progress: ProgressState;
  debug: DebugInfo;
  start: (payload: CampaignStartRequest) => Promise<void>;
  refresh: () => Promise<void>;
  pollUntilTerminal: () => Promise<void>;
  initialize: () => Promise<void>;
  selectCampaign: (campaignId: string) => Promise<void>;
  clearError: () => void;
  setUIState: (state: UIState) => void;
  updateProgress: (step: string) => void;
  setDebug: (data: DebugInfo) => void;
};

const STORAGE_KEY = "openpomelli:lastCampaignId";
const SNAPSHOT_KEY = "openpomelli:lastCampaignSnapshot";

type CampaignSnapshot = {
  campaignId: string;
  status: CampaignStatusResponse;
  campaign: CampaignStateResponse;
  logs: CampaignLog[];
  cachedAt: number;
};

const NODE_TO_STEP: Record<string, string> = {
  A01_BrandDNA: "Understanding Brand",
  A02_MarketIntel: "Analyzing Market",
  A08_KeywordGraph: "Analyzing Market",
  A10_Competitors: "Analyzing Market",
  A03_Audience: "Analyzing Market",
  A04_Localisation: "Generating Creatives",
  A05_Strategy: "Generating Creatives",
  A06_Content: "Generating Creatives",
  A07_Critic: "Generating Creatives",
  A09_Scheduler: "Building Schedule",
};

function readStoredCampaignId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored && stored.trim().length > 0 ? stored : null;
}

function persistCampaignId(campaignId: string | null): void {
  if (typeof window === "undefined") {
    return;
  }
  if (!campaignId) {
    window.localStorage.removeItem(STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, campaignId);
}

function readStoredSnapshot(campaignId: string): CampaignSnapshot | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(SNAPSHOT_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<CampaignSnapshot>;
    if (!parsed || parsed.campaignId !== campaignId) {
      return null;
    }
    if (!parsed.status || !parsed.campaign || !Array.isArray(parsed.logs)) {
      return null;
    }
    return {
      campaignId: parsed.campaignId,
      status: parsed.status as CampaignStatusResponse,
      campaign: parsed.campaign as CampaignStateResponse,
      logs: parsed.logs as CampaignLog[],
      cachedAt: Number(parsed.cachedAt || Date.now()),
    };
  } catch {
    return null;
  }
}

function persistSnapshot(snapshot: CampaignSnapshot | null): void {
  if (typeof window === "undefined") {
    return;
  }
  if (!snapshot) {
    window.localStorage.removeItem(SNAPSHOT_KEY);
    return;
  }
  window.localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snapshot));
}

const wait = (ms: number): Promise<void> => new Promise((resolve) => {
  window.setTimeout(resolve, ms);
});

function isMissingCampaignError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  const message = error.message.toLowerCase();
  return message.includes("404") || message.includes("not found");
}

function buildProgress(status: CampaignStatusResponse): ProgressState {
  const completed = Array.from(
    new Set(
      (status.completed_nodes ?? [])
        .map((node) => NODE_TO_STEP[node])
        .filter((step): step is string => Boolean(step))
    )
  );
  return {
    step: NODE_TO_STEP[status.current_node] || "",
    completed,
  };
}

export const useCampaignStore = create<CampaignStore>((set, get) => ({
  campaignId: readStoredCampaignId(),
  status: null,
  campaign: null,
  logs: [],
  isLoading: false,
  error: null,
  uiState: "EMPTY",
  progress: { step: "", completed: [] },
  debug: { logs: [], nodes: [], raw: null },
  
  setUIState: (state) => set({ uiState: state }),
  
  updateProgress: (step) =>
    set((s) => ({
      progress: {
        step,
        completed: [...new Set([...s.progress.completed, step])],
      },
    })),
  
  setDebug: (data) => set({ debug: data }),
  
  async start(payload) {
    set({ isLoading: true, error: null, uiState: "EMPTY" });
    try {
      const created = await startCampaign(payload);
      set({ campaignId: created.campaign_id, uiState: "GENERATING" });
      persistCampaignId(created.campaign_id);
      persistSnapshot(null);
      await get().refresh();
      void get().pollUntilTerminal();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to start campaign";
      set({ error: message, uiState: "EMPTY" });
      throw new Error(message);
    } finally {
      set({ isLoading: false });
    }
  },
  
  async refresh() {
    const campaignId = get().campaignId;
    if (!campaignId) {
      return;
    }
    try {
      const [status, campaign, logs] = await Promise.all([
        getCampaignStatus(campaignId),
        getCampaignState(campaignId),
        getCampaignLogs(campaignId),
      ]);
      const nodeNames = Array.from(
        new Set(
          [
            ...(status.completed_nodes ?? []),
            status.current_node,
            ...Object.keys(campaign.node_outputs ?? {}),
          ].filter((node): node is string => Boolean(node))
        )
      );
      const debugNodes = nodeNames.map((name) => ({
        name,
        status: status.current_node === name
          ? "active"
          : status.completed_nodes.includes(name)
            ? "completed"
            : "pending",
      }));

      let nextUiState: UIState = get().uiState;
      if (nextUiState !== "DEBUG") {
        if (status.status === "completed") {
          nextUiState = "OUTPUT";
        } else if (status.status === "running" || status.status === "queued") {
          nextUiState = "GENERATING";
        } else if (status.status === "error") {
          nextUiState = "EMPTY";
        }
      }

      set({
        status,
        campaign,
        logs: logs.logs,
        error: null,
        uiState: nextUiState,
        progress: buildProgress(status),
        debug: {
          logs: logs.logs,
          nodes: debugNodes,
          raw: campaign,
        },
      });
      persistSnapshot({
        campaignId,
        status,
        campaign,
        logs: logs.logs,
        cachedAt: Date.now(),
      });
    } catch (error) {
      if (isMissingCampaignError(error)) {
        persistCampaignId(null);
        persistSnapshot(null);
        set({
          campaignId: null,
          status: null,
          campaign: null,
          logs: [],
          debug: { logs: [], nodes: [], raw: null },
          progress: { step: "", completed: [] },
          error: "Saved campaign was not found. Start a new campaign from Onboarding.",
          uiState: "EMPTY",
        });
        return;
      }
      set({ error: error instanceof Error ? error.message : "Failed to refresh campaign" });
    }
  },
  
  async pollUntilTerminal() {
    const campaignId = get().campaignId;
    if (!campaignId) {
      return;
    }
    let attempts = 0;
    while (attempts < 120) {
      attempts += 1;
      await get().refresh();
      const currentStatus = get().status?.status;
      if (currentStatus === "completed" || currentStatus === "error") {
        return;
      }
      await wait(2000);
    }
  },
  
  async initialize() {
    const campaignId = get().campaignId;
    if (!campaignId) {
      return;
    }

    const currentStatus = get().status;
    const currentCampaign = get().campaign;
    if (currentStatus && currentCampaign && currentStatus.campaign_id === campaignId) {
      set({ uiState: currentStatus.status === "completed" ? "OUTPUT" : "GENERATING" });
    }

    const snapshot = readStoredSnapshot(campaignId);
    if (snapshot) {
      const nodeNames = Array.from(
        new Set(
          [
            ...(snapshot.status.completed_nodes ?? []),
            snapshot.status.current_node,
            ...Object.keys(snapshot.campaign.node_outputs ?? {}),
          ].filter((node): node is string => Boolean(node))
        )
      );
      const debugNodes = nodeNames.map((name) => ({
        name,
        status: snapshot.status.current_node === name
          ? "active"
          : snapshot.status.completed_nodes.includes(name)
            ? "completed"
            : "pending",
      }));
      set({
        status: snapshot.status,
        campaign: snapshot.campaign,
        logs: snapshot.logs,
        progress: buildProgress(snapshot.status),
        debug: {
          logs: snapshot.logs,
          nodes: debugNodes,
          raw: snapshot.campaign,
        },
        uiState: snapshot.status.status === "completed" ? "OUTPUT" : "GENERATING",
      });
    }

    try {
      await get().refresh();
      const hasStatus = Boolean(get().status);
      const hasCampaign = Boolean(get().campaign);
      if (!hasStatus || !hasCampaign) {
        throw new Error("Campaign not found");
      }
      const current = get().status;
      if (current?.status === "completed") {
        set({ uiState: "OUTPUT" });
      } else {
        set({ uiState: "GENERATING" });
      }
    } catch (error) {
      if (isMissingCampaignError(error)) {
        persistCampaignId(null);
        persistSnapshot(null);
        set({
          campaignId: null,
          status: null,
          campaign: null,
          logs: [],
          error: "Saved campaign was not found. Start a new campaign from Onboarding.",
          uiState: "EMPTY",
        });
        return;
      }
      set({ error: error instanceof Error ? error.message : "Failed to initialize campaign" });
    }
  },

  async selectCampaign(nextCampaignId) {
    const trimmed = nextCampaignId.trim();
    if (!trimmed) {
      return;
    }
    persistCampaignId(trimmed);
    persistSnapshot(null);
    set({ campaignId: trimmed, uiState: "GENERATING", error: null });
    await get().refresh();
    const latestStatus = get().status?.status;
    if (latestStatus === "running" || latestStatus === "queued") {
      void get().pollUntilTerminal();
    }
  },
  
  clearError() {
    set({ error: null });
  },
}));
