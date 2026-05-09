import type { CampaignStateResponse } from "../../types";

interface KeywordGraphBoxProps {
  campaign: CampaignStateResponse;
}

type GraphNode = {
  id: string;
  x: number;
  y: number;
  label: string;
  isCenter?: boolean;
};

export function KeywordGraphBox({ campaign }: KeywordGraphBoxProps) {
  const keywords: string[] = campaign.keyword_strategy?.top_10 ?? [];
  const keywordTrace = campaign.keyword_strategy?.trace ?? {};
  const sourceProvider = String(keywordTrace.provider ?? "local");
  const sourceDocuments = Number(keywordTrace.source_documents ?? 0);
  const selected = keywords.slice(0, 10);
  if (selected.length === 0) {
    return null;
  }

  const width = 980;
  const height = 360;
  const cx = width / 2;
  const cy = height / 2;
  const radius = 130;

  const nodes: GraphNode[] = [
    { id: "main", x: cx, y: cy, label: "Main Agent", isCenter: true },
    ...selected.map((keyword: string, index: number) => {
      const angle = (Math.PI * 2 * index) / selected.length;
      return {
        id: `kw-${index}`,
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius,
        label: String(keyword),
      };
    }),
  ];

  return (
    <section className="content-bento-card keyword-graph-box">
      <div className="creative-section-head">
        <p className="mono overline">SEO Keyword Graph Engine</p>
        <p className="creative-section-count">
          Source: {sourceProvider} · Documents: {Number.isFinite(sourceDocuments) ? sourceDocuments : 0}
        </p>
      </div>

      <div className="keyword-graph-stage">
        <svg viewBox={`0 0 ${width} ${height}`} className="keyword-graph-svg" role="img" aria-label="SEO keyword graph">
          {nodes
            .filter((node) => !node.isCenter)
            .map((node) => (
              <g key={`edge-main-${node.id}`}>
                <line x1={cx} y1={cy} x2={node.x} y2={node.y} className="keyword-edge" />
              </g>
            ))}

          {nodes
            .filter((node) => !node.isCenter)
            .map((node, index, arr) => {
              const next = arr[(index + 1) % arr.length];
              if (!next) {
                return null;
              }
              return <line key={`edge-ring-${node.id}`} x1={node.x} y1={node.y} x2={next.x} y2={next.y} className="keyword-edge-soft" />;
            })}

          {nodes.map((node) => (
            <g key={node.id}>
              <circle cx={node.x} cy={node.y} r={node.isCenter ? 22 : 14} className={node.isCenter ? "keyword-node-center" : "keyword-node"} />
              <text x={node.x} y={node.y + (node.isCenter ? 40 : 30)} textAnchor="middle" className={node.isCenter ? "keyword-label-center" : "keyword-label"}>
                {node.label}
              </text>
            </g>
          ))}
        </svg>
      </div>
    </section>
  );
}
