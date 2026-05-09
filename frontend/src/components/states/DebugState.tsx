import { useCampaignStore } from "../../store/campaignStore";

export function DebugState() {
  const { debug, logs, campaign } = useCampaignStore();
  const progress = campaign?.progress;

  return (
    <section className="debug-shell">
      <h1>Debug View</h1>

      <div className="debug-grid">
        <article className="debug-card">
          <p className="mono overline">Campaign Runtime</p>
          <p>Campaign ID: {campaign?.campaign_id || "n/a"}</p>
          <p>Status: {campaign?.status || "idle"}</p>
          <p>Current node: {campaign?.current_node || "n/a"}</p>
          <p>Progress: {progress ? `${progress.completed}/${progress.total} (${progress.percent}%)` : "n/a"}</p>
        </article>

        <article className="debug-card">
          <p className="mono overline">Node States</p>
          <div className="debug-node-list">
            {debug.nodes.map((node) => (
              <p key={node.name}>
                {node.name}: {node.status}
              </p>
            ))}
          </div>
        </article>

        <article className="debug-card debug-card-wide">
          <p className="mono overline">Recent Logs ({logs.length})</p>
          <div className="debug-log-list">
            {logs.slice(-80).map((log) => (
              <p key={`${log.seq}-${log.ts}`}>[{log.ts}] {log.agent} - {log.message}</p>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
}
