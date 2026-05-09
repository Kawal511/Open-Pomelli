import { useEffect, useMemo, useState } from "react";
import { Background, Controls, MarkerType, ReactFlow } from "@xyflow/react";
import { useCampaignStore } from "../store/campaignStore";
import { rerunCriticAgent } from "../lib/api";
import type { CampaignStateResponse } from "../types";
import "@xyflow/react/dist/style.css";

const NODE_ORDER = [
  "A01_BrandDNA",
  "A02_MarketIntel",
  "A08_KeywordGraph",
  "A10_Competitors",
  "A03_Audience",
  "A04_Localisation",
  "A05_Strategy",
  "A06_Content",
  "A11_CreativeAgent",
  "A07_Critic",
  "A09_Scheduler",
];

const FLOW_EDGES = [
  ["A01_BrandDNA", "A02_MarketIntel"],
  ["A01_BrandDNA", "A08_KeywordGraph"],
  ["A01_BrandDNA", "A10_Competitors"],
  ["A02_MarketIntel", "A03_Audience"],
  ["A08_KeywordGraph", "A03_Audience"],
  ["A10_Competitors", "A03_Audience"],
  ["A03_Audience", "A04_Localisation"],
  ["A04_Localisation", "A05_Strategy"],
  ["A05_Strategy", "A06_Content"],
  ["A06_Content", "A11_CreativeAgent"],
  ["A11_CreativeAgent", "A07_Critic"],
  ["A07_Critic", "A09_Scheduler"],
];

const GRID_POSITIONS: Record<string, { x: number; y: number }> = {
  A01_BrandDNA: { x: 0, y: 60 },
  A02_MarketIntel: { x: 220, y: 0 },
  A08_KeywordGraph: { x: 220, y: 100 },
  A10_Competitors: { x: 220, y: 200 },
  A03_Audience: { x: 470, y: 100 },
  A04_Localisation: { x: 700, y: 100 },
  A05_Strategy: { x: 930, y: 100 },
  A06_Content: { x: 1160, y: 100 },
  A11_CreativeAgent: { x: 1390, y: 100 },
  A07_Critic: { x: 1620, y: 100 },
  A09_Scheduler: { x: 1850, y: 100 },
};

type TabKey = "input" | "output" | "logs";

function humanizeKey(raw: string): string {
  return raw
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function summarizeScalar(value: unknown): string {
  if (value === null) {
    return "null";
  }
  if (value === undefined) {
    return "undefined";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "";
}

function renderInspectorValue(value: unknown, depth = 0): React.ReactNode {
  const isScalar =
    value === null || value === undefined || typeof value === "string" || typeof value === "number" || typeof value === "boolean";

  if (isScalar) {
    return <p className="inspector-scalar">{summarizeScalar(value)}</p>;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <p className="inspector-empty">No items</p>;
    }

    return (
      <div className="inspector-array">
        {value.slice(0, 40).map((entry, index) => (
          <article key={`${depth}-arr-${index}`} className="inspector-array-item">
            <p className="inspector-key">Item {index + 1}</p>
            <div className="inspector-value">{renderInspectorValue(entry, depth + 1)}</div>
          </article>
        ))}
        {value.length > 40 ? <p className="inspector-empty">+{value.length - 40} more items</p> : null}
      </div>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) {
      return <p className="inspector-empty">Empty object</p>;
    }

    return (
      <div className="inspector-object">
        {entries.map(([key, entry]) => (
          <article key={`${depth}-${key}`} className="inspector-field">
            <p className="inspector-key">{humanizeKey(key)}</p>
            <div className="inspector-value">{renderInspectorValue(entry, depth + 1)}</div>
          </article>
        ))}
      </div>
    );
  }

  return <p className="inspector-scalar">{String(value)}</p>;
}

function selectNodePayload(campaign: CampaignStateResponse | null, nodeName: string, tab: TabKey): unknown {
  if (!campaign) {
    return {};
  }

  const nodeSnapshot = campaign.node_outputs?.[nodeName];

  if (tab === "input") {
    return nodeSnapshot?.input ?? {};
  }

  if (tab === "logs") {
    return campaign.agent_logs.filter((log) => log.agent === nodeName);
  }

  return nodeSnapshot?.output ?? {};
}

export function AdminPage() {
  const { campaign, campaignId, status, logs, refresh, isLoading, error } = useCampaignStore();
  const [selectedNode, setSelectedNode] = useState("A01_BrandDNA");
  const [tab, setTab] = useState<TabKey>("input");
  const [inspectorZoomOpen, setInspectorZoomOpen] = useState(false);
  const [criticLoading, setCriticLoading] = useState(false);

  useEffect(() => {
    const preferredNode = status?.current_node;
    if (!preferredNode) {
      return;
    }
    if (NODE_ORDER.includes(preferredNode)) {
      setSelectedNode(preferredNode);
    }
  }, [status?.current_node]);

  const flowNodes = useMemo(() => {
    const completed = new Set(status?.completed_nodes ?? []);
    const currentNode = status?.current_node;
    const fanOutNodes = ["A02_MarketIntel", "A08_KeywordGraph", "A10_Competitors"];
    const fanOutRunning =
      status?.status === "running" &&
      fanOutNodes.some((node) => node === currentNode || completed.has(node)) &&
      !fanOutNodes.every((node) => completed.has(node));

    const activeNodes = new Set<string>();
    if (currentNode) {
      activeNodes.add(currentNode);
    }
    if (fanOutRunning) {
      fanOutNodes.filter((node) => !completed.has(node)).forEach((node) => activeNodes.add(node));
    }

    return NODE_ORDER.map((name) => {
      const isActive = activeNodes.has(name);
      const isCompleted = completed.has(name);
      const nodeOutput = campaign?.node_outputs?.[name]?.output as Record<string, unknown> | undefined;
      const executionMode = String(nodeOutput?.execution_mode ?? nodeOutput?.algorithm ?? "").toLowerCase();
      const isZeroLlm = executionMode.includes("zero-llm") || executionMode.includes("pagerank");
      return {
        id: name,
        className: "admin-flow-node",
        position: GRID_POSITIONS[name],
        data: {
          label: (
            <div className="admin-node-inner">
              <span className={isActive ? "node-dot node-dot-active" : isCompleted ? "node-dot node-dot-complete" : "node-dot"} />
              <span>{name.replace("_", " ")}</span>
              {isZeroLlm ? <small className="node-badge">ZERO-LLM</small> : null}
            </div>
          ),
        },
        style: {
          background: "#fffef9",
          color: isCompleted ? "#2f2b18" : "#78755e",
          border: isActive ? "1px solid #d7b83a" : "1px solid #d9dccb",
          borderRadius: "16px",
          minWidth: "170px",
          padding: "2px 4px",
          boxShadow: isActive
            ? "0 0 0 2px rgba(243, 211, 59, 0.32), 0 10px 24px rgba(213, 188, 65, 0.28)"
            : "0 8px 22px rgba(87, 80, 36, 0.14)",
          animation: isActive ? "pulse-glow 1.2s ease-in-out infinite" : undefined,
          fontFamily: "var(--font-mono)",
          fontSize: "12px",
          textTransform: "uppercase" as const,
          letterSpacing: "0.08em",
        },
      };
    });
  }, [campaign?.node_outputs, status]);

  const flowEdges = useMemo(
    () =>
      FLOW_EDGES.map(([source, target]) => ({
        id: `${source}-${target}`,
        source,
        target,
        markerEnd: { type: MarkerType.ArrowClosed, color: "#d7b83a" },
        style: { stroke: "#d7b83a", strokeWidth: 1.6 },
      })),
    []
  );

  const panelPayload = selectNodePayload(campaign, selectedNode, tab);

  const pipelinePercent = useMemo(() => {
    const explicit = Number(status?.progress?.percent);
    if (Number.isFinite(explicit) && explicit >= 0) {
      return Math.max(0, Math.min(100, Math.round(explicit)));
    }
    const completed = status?.completed_nodes?.length ?? 0;
    return Math.max(0, Math.min(100, Math.round((completed / NODE_ORDER.length) * 100)));
  }, [status?.completed_nodes?.length, status?.progress?.percent]);

  const phoenixTraceRows = useMemo(() => {
    return NODE_ORDER.map((nodeName) => {
      const output = campaign?.node_outputs?.[nodeName];
      const inputKeys = Object.keys((output?.input as Record<string, unknown>) || {});
      const outputKeys = Object.keys((output?.output as Record<string, unknown>) || {});
      const nodeLogs = logs.filter((entry) => entry.agent === nodeName);
      const lastLog = nodeLogs[nodeLogs.length - 1];
      return {
        nodeName,
        status: status?.current_node === nodeName ? "active" : status?.completed_nodes.includes(nodeName) ? "completed" : "pending",
        inputKeys,
        outputKeys,
        lastMessage: lastLog?.message || "No trace event yet",
      };
    });
  }, [campaign?.node_outputs, logs, status?.completed_nodes, status?.current_node]);

  return (
    <section className="admin-page">
      <header className="admin-header">
        <div>
          <p className="mono overline">ADMIN COMMAND CENTER</p>
          <h2>Swarm Runtime and Critic Audit</h2>
        </div>
        <div>
          <p className="mono status-line">
            STATUS {status?.status.toUpperCase() ?? "IDLE"} · ACTIVE {status?.current_node ?? "N/A"} ·
            REFINEMENTS {status?.refinement_count ?? 0}
          </p>
          <div className="asset-actions">
            <button
              type="button"
              className={isLoading ? "loading-button" : ""}
              onClick={() => void refresh()}
              disabled={!campaignId || isLoading}
            >
              {isLoading ? "SYNCING" : "SYNC FROM ONBOARDING"}
            </button>
            <button
              type="button"
              className={criticLoading ? "loading-button" : ""}
              onClick={async () => {
                if (!campaignId || criticLoading) {
                  return;
                }
                try {
                  setCriticLoading(true);
                  await rerunCriticAgent(campaignId);
                  await refresh();
                } finally {
                  setCriticLoading(false);
                }
              }}
              disabled={!campaignId || criticLoading}
            >
              {criticLoading ? "RERUNNING CRITIC" : "RERUN CRITIC AGENT"}
            </button>
          </div>
        </div>
      </header>

      <article className="admin-progress-wrap" aria-label="Pipeline completion">
        <div className="admin-progress-head">
          <p className="mono overline">WARM ANALYZER PIPELINE</p>
          <p className="mono admin-progress-label">{pipelinePercent}% COMPLETE</p>
        </div>
        <div className="admin-progress-bar">
          <div className="admin-progress-fill" style={{ width: `${pipelinePercent}%` }} />
        </div>
      </article>

      {error && <p className="form-error">{error}</p>}
      {!campaignId && <p className="form-error">Start a campaign from Onboarding first. Command Center mirrors that run.</p>}

      <div className="admin-grid">
        <article className="panel flow-panel">
          <h3>Swarm Visualizer</h3>
          <div className="flow-frame">
            <ReactFlow
              nodes={flowNodes}
              edges={flowEdges}
              fitView
              minZoom={0.25}
              maxZoom={1.3}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable
              onNodeClick={(_, node) => setSelectedNode(node.id)}
            >
              <Background color="#d3d8c3" gap={20} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
        </article>

        <article className="panel code-panel">
          <div className="inspector-head">
            <h3>Node Inspector</h3>
            <button
              type="button"
              className="tab"
              onClick={() => setInspectorZoomOpen((current) => !current)}
            >
              {inspectorZoomOpen ? "CLOSE ZOOM" : "ZOOM"}
            </button>
          </div>
          <div className="tab-strip">
            {(["input", "output", "logs"] as const).map((tabKey) => (
              <button
                key={tabKey}
                type="button"
                className={tab === tabKey ? "tab tab-active" : "tab"}
                onClick={() => setTab(tabKey)}
              >
                {tabKey.toUpperCase()}
              </button>
            ))}
          </div>
          <p className="mono overline">{selectedNode}</p>
          <div className="inspector-scroll">{renderInspectorValue(panelPayload)}</div>
          {inspectorZoomOpen ? (
            <div className="inspector-zoom-window" role="dialog" aria-label="Node inspector zoomed view">
              <header className="inspector-zoom-head">
                <p className="mono overline">{selectedNode} · {tab.toUpperCase()}</p>
                <button type="button" className="tab" onClick={() => setInspectorZoomOpen(false)}>
                  CLOSE
                </button>
              </header>
              <div className="inspector-scroll inspector-scroll-zoom">{renderInspectorValue(panelPayload)}</div>
            </div>
          ) : null}
        </article>

        <article className="panel phoenix-panel">
          <h3>Agent Path</h3>
          <div className="phoenix-wrap">
            {phoenixTraceRows.map((row) => (
              <article key={row.nodeName} className={row.status === "active" ? "phoenix-row phoenix-row-active" : "phoenix-row"}>
                <div className="phoenix-row-head">
                  <p className="mono">{row.nodeName}</p>
                  <span className={`mono phoenix-status phoenix-status-${row.status}`}>{row.status}</span>
                </div>
                <p className="phoenix-message">{row.lastMessage}</p>
                <p className="phoenix-io mono">in: {row.inputKeys.slice(0, 4).join(", ") || "-"}</p>
                <p className="phoenix-io mono">out: {row.outputKeys.slice(0, 4).join(", ") || "-"}</p>
              </article>
            ))}
          </div>
        </article>

        <article className="panel terminal-panel">
          <h3>Live Audit Terminal</h3>
          <div className="terminal-scroll">
            {logs.length === 0 && <p className="mono">No logs yet.</p>}
            {logs.map((entry) => (
              <article key={`${entry.seq}-${entry.ts}`} className="terminal-entry">
                <header className="terminal-entry-head">
                  <span className="mono">{entry.ts}</span>
                  <span className="mono terminal-agent">{entry.agent}</span>
                  <span className={`mono terminal-level terminal-level-${entry.level.toLowerCase()}`}>{entry.level}</span>
                </header>
                <p className="terminal-line">{entry.message}</p>
                {entry.extra && Object.keys(entry.extra).length > 0 ? (
                  <div className="terminal-meta">
                    {Object.entries(entry.extra).slice(0, 8).map(([key, value]) => (
                      <span key={`${entry.seq}-${key}`} className="terminal-meta-chip mono">
                        {humanizeKey(key)}: {summarizeScalar(value) || "[structured]"}
                      </span>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
}
