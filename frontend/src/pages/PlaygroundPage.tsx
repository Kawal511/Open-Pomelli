import { type ChangeEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  addEdge,
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { listCampaignHistory, runMiniAgent, runVadooVideo } from "../lib/api";
import type { MiniAgentType, UploadedAssetContext } from "../types";
import "@xyflow/react/dist/style.css";

type InputNodeData = {
  value: string;
  onChange: (value: string) => void;
};

type AgentNodeData = {
  agentType: MiniAgentType;
  onChange: (value: MiniAgentType) => void;
};

type ImageGeneratorProvider = "kie" | "gemini";

type OutputNodeData = {
  value: string;
  blocks: StructuredOutputBlock[];
  images: GeneratedImagePreview[];
  videos: GeneratedVideoPreview[];
};

type ImageGenNodeData = {
  status: "idle" | "running" | "completed" | "skipped" | "error";
  provider: ImageGeneratorProvider;
  onProviderChange?: (value: ImageGeneratorProvider) => void;
  warning?: string | null;
};

type StructuredOutputBlock = {
  title: string;
  lines: string[];
};

type GeneratedImagePreview = {
  title: string;
  image_url: string;
  provider: string;
  status: string;
  model: string;
  error?: string;
};

type GeneratedVideoPreview = {
  video_url: string;
  provider: string;
  status: string;
  model: string;
  prompt: string;
};

const DEFAULT_INPUT = "I sell specialty coffee subscriptions.";

async function copyTextToClipboard(value: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // Fallback path below.
  }

  try {
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "true");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(textarea);
    return copied;
  } catch {
    return false;
  }
}

function buildOutputCopyText(data: OutputNodeData): string {
  const sections: string[] = [];

  if (data.blocks.length > 0) {
    data.blocks.forEach((block) => {
      const blockContent = block.lines.join("\n").trim();
      if (blockContent) {
        sections.push(`${block.title}\n${blockContent}`);
      }
    });
  } else if (data.value.trim()) {
    sections.push(data.value.trim());
  }

  if (data.images.length > 0) {
    const imageLines = data.images.map((image, index) => {
      const title = image.title?.trim() || `Image ${index + 1}`;
      return `${title}: ${image.image_url}`;
    });
    sections.push(`Images\n${imageLines.join("\n")}`);
  }

  if (data.videos.length > 0) {
    const videoLines = data.videos.map((video, index) => {
      const model = video.model?.trim() || `Video ${index + 1}`;
      return `${model}: ${video.video_url}`;
    });
    sections.push(`Videos\n${videoLines.join("\n")}`);
  }

  return sections.join("\n\n");
}

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
    reader.onload = () => {
      if (typeof reader.result !== "string") {
        reject(new Error(`Invalid encoding for ${file.name}`));
        return;
      }
      resolve(reader.result.split(",")[1] ?? "");
    };
    reader.readAsDataURL(file);
  });
}

const MINI_AGENTS: Array<{ label: string; value: MiniAgentType }> = [
  { label: "Hook Writer", value: "hook-writer" },
  { label: "SEO Analyzer", value: "seo-analyzer" },
  { label: "Image Prompter", value: "image-prompter" },
  { label: "Competitor Roaster", value: "competitor-roaster" },
  { label: "Instagram Message Generator", value: "instagram-generator" },
  { label: "LinkedIn Post Generator", value: "linkedin-generator" },
  { label: "Professional Email Drafter", value: "email-drafter" },
];

const IMAGE_GENERATOR_PROVIDERS: Array<{ label: string; value: ImageGeneratorProvider }> = [
  { label: "KIE", value: "kie" },
  { label: "Gemini", value: "gemini" },
];

function InputNode({ data }: NodeProps) {
  const typed = data as unknown as InputNodeData;
  return (
    <div className="play-node">
      <p className="mono overline">INPUT</p>
      <textarea
        value={typed.value}
        onChange={(event) => typed.onChange(event.target.value)}
        rows={5}
        className="play-text"
      />
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function AgentNode({ data }: NodeProps) {
  const typed = data as unknown as AgentNodeData;
  return (
    <div className="play-node">
      <p className="mono overline">MINI AGENT</p>
      <select
        value={typed.agentType}
        onChange={(event) => typed.onChange(event.target.value as MiniAgentType)}
      >
        {MINI_AGENTS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function OutputNode({ data }: NodeProps) {
  const typed = data as unknown as OutputNodeData;
  const [copiedAll, setCopiedAll] = useState(false);
  const [copiedSectionIndex, setCopiedSectionIndex] = useState<number | null>(null);

  const copyAll = useCallback(async (value: string) => {
    if (!value.trim()) {
      return;
    }
    const copied = await copyTextToClipboard(value);
    if (!copied) {
      setCopiedAll(false);
      return;
    }
    setCopiedAll(true);
    window.setTimeout(() => setCopiedAll(false), 1400);
  }, []);

  const copySection = useCallback(async (index: number, value: string) => {
    if (!value.trim()) {
      return;
    }
    const copied = await copyTextToClipboard(value);
    if (!copied) {
      return;
    }
    setCopiedSectionIndex(index);
    window.setTimeout(() => {
      setCopiedSectionIndex((current) => (current === index ? null : current));
    }, 1400);
  }, []);

  const allOutputText = useMemo(() => buildOutputCopyText(typed), [typed]);

  return (
    <div className="play-node">
      <div className="output-header-row">
        <p className="mono overline">OUTPUT</p>
        <button
          type="button"
          className="output-copy-btn"
          onClick={() => copyAll(allOutputText)}
          disabled={!allOutputText.trim()}
        >
          {copiedAll ? "Copied" : "Copy all"}
        </button>
      </div>
      <div className="output-box">
        {typed.blocks.length === 0 ? (
          <p className="output-line">{typed.value || "Run the flow to generate structured output."}</p>
        ) : (
          <div className="output-structured">
            {typed.blocks.map((block, index) => (
              <section key={`${block.title}-${index}`} className="output-block">
                <div className="output-block-head">
                  <h4>{block.title}</h4>
                  <button
                    type="button"
                    className="output-copy-btn"
                    onClick={() => copySection(index, block.lines.join("\n"))}
                    disabled={block.lines.length === 0}
                  >
                    {copiedSectionIndex === index ? "Copied" : "Copy"}
                  </button>
                </div>
                {block.lines.map((line, lineIndex) => (
                  <p key={`${block.title}-${lineIndex}`} className="output-line">
                    {line}
                  </p>
                ))}
              </section>
            ))}
          </div>
        )}
        {typed.images.length > 0 && (
          <div className="output-image-grid">
            {typed.images.map((image, index) => (
              <article key={`${image.image_url}-${index}`} className="output-image-card">
                <img src={image.image_url} alt={image.title || `Generated preview ${index + 1}`} loading="lazy" />
                <p className="mono overline">{(image.provider || "unknown").toUpperCase()}</p>
                <p className="output-line">{image.title || `Preview ${index + 1}`}</p>
              </article>
            ))}
          </div>
        )}
        {typed.videos.length > 0 && (
          <div className="output-image-grid">
            {typed.videos.map((video, index) => (
              <article key={`${video.video_url}-${index}`} className="output-image-card">
                <video src={video.video_url} controls playsInline />
                <p className="mono overline">{(video.provider || "unknown").toUpperCase()}</p>
                <p className="output-line">{video.model || "vadoo-ai-story"}</p>
              </article>
            ))}
          </div>
        )}
      </div>
      <Handle type="target" position={Position.Left} />
    </div>
  );
}

function VideoGeneratorNode({ data }: NodeProps) {
  const typed = data as unknown as {
    status: "idle" | "running" | "completed" | "error";
    provider: "vadooai";
    latestUrl?: string;
  };
  return (
    <div className="play-node image-gen-node">
      <p className="mono overline">VIDEO GENERATOR</p>
      <p className="output-line">Provider Route: VADOO AI</p>
      <p className="image-gen-node-status">Status: {typed.status.toUpperCase()}</p>
      {typed.latestUrl ? <p className="output-line">Video: ready</p> : null}
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function ImageGeneratorNode({ data }: NodeProps) {
  const typed = data as unknown as ImageGenNodeData;
  return (
    <div className="play-node image-gen-node">
      <p className="mono overline">IMAGE GENERATOR</p>
      <select
        value={typed.provider}
        onChange={(event) => typed.onProviderChange?.(event.target.value as ImageGeneratorProvider)}
      >
        {IMAGE_GENERATOR_PROVIDERS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <p className="output-line">Provider Route: {typed.provider.toUpperCase()}</p>
      <p className="image-gen-node-status">Status: {typed.status.toUpperCase()}</p>
      {typed.warning && <p className="image-gen-node-warning">{typed.warning}</p>}
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = {
  inputNode: InputNode,
  agentNode: AgentNode,
  imageGenNode: ImageGeneratorNode,
  videoGenNode: VideoGeneratorNode,
  outputNode: OutputNode,
};

type FlowNode = Node<Record<string, unknown>>;

function PlaygroundCanvas() {
  const [inputValue, setInputValue] = useState(DEFAULT_INPUT);
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [contextNotes, setContextNotes] = useState("");
  const [outputValue, setOutputValue] = useState("");
  const [outputBlocks, setOutputBlocks] = useState<StructuredOutputBlock[]>([]);
  const [generatedImages, setGeneratedImages] = useState<GeneratedImagePreview[]>([]);
  const [generatedVideos, setGeneratedVideos] = useState<GeneratedVideoPreview[]>([]);
  const [imageGenStatus, setImageGenStatus] = useState<ImageGenNodeData["status"]>("idle");
  const [videoGenStatus, setVideoGenStatus] = useState<"idle" | "running" | "completed" | "error">("idle");
  const [imageProvider, setImageProvider] = useState<ImageGeneratorProvider>("kie");
  const [imageGenWarning, setImageGenWarning] = useState<string | null>(null);
  const [traceValue, setTraceValue] = useState<Record<string, unknown> | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadedAssets, setUploadedAssets] = useState<UploadedAssetContext[]>([]);
  const [campaignOptions, setCampaignOptions] = useState<Array<{ id: string; brand: string }>>([]);
  const [videoCampaignId, setVideoCampaignId] = useState("");
  const [videoBrandName, setVideoBrandName] = useState("");
  const [running, setRunning] = useState(false);
  const reactFlow = useReactFlow();

  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>([
    {
      id: "input-1",
      type: "inputNode",
      position: { x: 70, y: 120 },
      data: { value: inputValue, onChange: setInputValue },
    },
    {
      id: "agent-1",
      type: "agentNode",
      position: { x: 420, y: 120 },
      data: {
        agentType: "hook-writer",
        onChange: (value: MiniAgentType) => {
          setNodes((currentNodes) =>
            currentNodes.map((node) => {
              if (node.id !== "agent-1") {
                return node;
              }
              return {
                ...node,
                data: {
                  ...(node.data as Record<string, unknown>),
                  agentType: value,
                },
              };
            })
          );
        },
      },
    },
    {
      id: "imagegen-1",
      type: "imageGenNode",
      position: { x: 710, y: 120 },
      data: {
        status: imageGenStatus,
        provider: imageProvider,
        warning: imageGenWarning,
        onProviderChange: (value: ImageGeneratorProvider) => {
          setImageProvider(value);
          setNodes((currentNodes) =>
            currentNodes.map((node) => {
              if (node.id !== "imagegen-1") {
                return node;
              }
              return {
                ...node,
                data: {
                  ...(node.data as Record<string, unknown>),
                  provider: value,
                },
              };
            })
          );
        },
      },
    },
    {
      id: "videogen-1",
      type: "videoGenNode",
      position: { x: 920, y: 120 },
      data: {
        status: videoGenStatus,
        provider: "vadooai",
      },
    },
    {
      id: "output-1",
      type: "outputNode",
      position: { x: 1160, y: 120 },
      data: { value: outputValue, blocks: outputBlocks, images: generatedImages, videos: generatedVideos },
    },
  ]);

  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([
    { id: "e1", source: "input-1", target: "agent-1" },
    { id: "e2", source: "agent-1", target: "imagegen-1" },
    { id: "e3", source: "imagegen-1", target: "videogen-1" },
    { id: "e4", source: "videogen-1", target: "output-1" },
  ]);

  const sidebarItems = useMemo(
    () => [
      { kind: "inputNode", label: "Input Node" },
      ...MINI_AGENTS.map((agent) => ({
        kind: "agentNode",
        label: agent.label,
        agentType: agent.value,
      })),
      { kind: "imageGenNode", label: "Image Generator" },
      { kind: "videoGenNode", label: "Vadoo Video Generator" },
      { kind: "outputNode", label: "Output Node" },
    ],
    []
  );

  const onConnect = useCallback(
    (connection: Connection | Edge) => {
      setEdges((currentEdges) => addEdge(connection, currentEdges));
    },
    [setEdges]
  );

  const onDragStart = (event: React.DragEvent<HTMLButtonElement>, payload: Record<string, string>) => {
    event.dataTransfer.setData("application/x-nexus-node", JSON.stringify(payload));
    event.dataTransfer.effectAllowed = "move";
  };

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const raw = event.dataTransfer.getData("application/x-nexus-node");
    if (!raw) {
      return;
    }
    const payload = JSON.parse(raw) as { kind: string; agentType?: MiniAgentType };
    const position = reactFlow.screenToFlowPosition({ x: event.clientX, y: event.clientY });
    const id = `${payload.kind}-${Date.now()}`;

    if (payload.kind === "inputNode") {
      setNodes((current) => [
        ...current,
        {
          id,
          type: "inputNode",
          position,
          data: { value: "", onChange: () => undefined },
        },
      ]);
      return;
    }

    if (payload.kind === "outputNode") {
      setNodes((current) => [
        ...current,
        {
          id,
          type: "outputNode",
          position,
          data: { value: "", blocks: [], images: [], videos: [] },
        },
      ]);
      return;
    }

    if (payload.kind === "imageGenNode") {
      setNodes((current) => [
        ...current,
        {
          id,
          type: "imageGenNode",
          position,
          data: {
            status: "idle",
            provider: imageProvider,
            warning: null,
            onProviderChange: (value: ImageGeneratorProvider) => {
              setNodes((currentNodes) =>
                currentNodes.map((node) => {
                  if (node.id !== id) {
                    return node;
                  }
                  return {
                    ...node,
                    data: {
                      ...(node.data as Record<string, unknown>),
                      provider: value,
                    },
                  };
                })
              );
            },
          },
        },
      ]);
      return;
    }

    if (payload.kind === "videoGenNode") {
      setNodes((current) => [
        ...current,
        {
          id,
          type: "videoGenNode",
          position,
          data: {
            status: "idle",
            provider: "vadooai",
          },
        },
      ]);
      return;
    }

    setNodes((current) => [
      ...current,
      {
        id,
        type: "agentNode",
        position,
        data: {
          agentType: payload.agentType ?? "hook-writer",
          onChange: (value: MiniAgentType) => {
            setNodes((currentNodes) =>
              currentNodes.map((node) => {
                if (node.id !== id) {
                  return node;
                }
                return {
                  ...node,
                  data: {
                    ...(node.data as Record<string, unknown>),
                    agentType: value,
                  },
                };
              })
            );
          },
        },
      },
    ]);
  };

  const onDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  };

  const resolveSelectedAgentType = (): MiniAgentType => {
    let cursor = "output-1";
    const visited = new Set<string>();

    while (!visited.has(cursor)) {
      visited.add(cursor);
      const incoming = [...edges].reverse().find((edge) => edge.target === cursor);
      if (!incoming) {
        break;
      }
      const sourceNode = nodes.find((node) => node.id === incoming.source);
      if (sourceNode?.type === "agentNode") {
        const candidate = (sourceNode.data as { agentType?: MiniAgentType }).agentType;
        return candidate ?? "hook-writer";
      }
      cursor = incoming.source;
    }

    const selectedNode = nodes.find((node) => node.type === "agentNode" && node.selected);
    if (selectedNode?.data && typeof selectedNode.data === "object") {
      const candidate = (selectedNode.data as { agentType?: MiniAgentType }).agentType;
      if (candidate) {
        return candidate;
      }
    }

    const fallbackPrimary = nodes.find((node) => node.id === "agent-1");
    if (fallbackPrimary?.data && typeof fallbackPrimary.data === "object") {
      return ((fallbackPrimary.data as { agentType?: MiniAgentType }).agentType ?? "hook-writer") as MiniAgentType;
    }

    return "hook-writer";
  };

  const resolveSelectedImageProvider = (): ImageGeneratorProvider => {
    let cursor = "output-1";
    const visited = new Set<string>();

    while (!visited.has(cursor)) {
      visited.add(cursor);
      const incoming = [...edges].reverse().find((edge) => edge.target === cursor);
      if (!incoming) {
        break;
      }
      const sourceNode = nodes.find((node) => node.id === incoming.source);
      if (sourceNode?.type === "imageGenNode") {
        const candidate = (sourceNode.data as { provider?: ImageGeneratorProvider }).provider;
        return candidate ?? "kie";
      }
      cursor = incoming.source;
    }

    const selectedNode = nodes.find((node) => node.type === "imageGenNode" && node.selected);
    if (selectedNode?.data && typeof selectedNode.data === "object") {
      const candidate = (selectedNode.data as { provider?: ImageGeneratorProvider }).provider;
      if (candidate) {
        return candidate;
      }
    }

    const fallbackPrimary = nodes.find((node) => node.id === "imagegen-1");
    if (fallbackPrimary?.data && typeof fallbackPrimary.data === "object") {
      return ((fallbackPrimary.data as { provider?: ImageGeneratorProvider }).provider ?? "kie") as ImageGeneratorProvider;
    }

    return "kie";
  };

  const parseOutputBlocks = (raw: string): StructuredOutputBlock[] => {
    const text = raw.trim();
    if (!text) {
      return [];
    }

    const lines = text.replace(/\r/g, "").split("\n");
    const blocks: StructuredOutputBlock[] = [];
    let current: StructuredOutputBlock = { title: "Response", lines: [] };

    const flush = () => {
      if (current.lines.length > 0 || current.title !== "Response") {
        blocks.push(current);
      }
    };

    for (const originalLine of lines) {
      const line = originalLine.trim();
      if (!line) {
        continue;
      }

      const headingMatch = line.match(/^#{2,3}\s+(.+)/);
      if (headingMatch) {
        flush();
        current = { title: headingMatch[1].trim(), lines: [] };
        continue;
      }

      const boldHeadingMatch = line.match(/^\*\*(.+)\*\*$/);
      if (boldHeadingMatch) {
        flush();
        current = { title: boldHeadingMatch[1].trim(), lines: [] };
        continue;
      }

      const cleaned = line
        .replace(/^[-*]\s+/, "")
        .replace(/^\d+\.\s+/, "")
        .trim();

      if (cleaned) {
        current.lines.push(cleaned);
      }
    }

    flush();
    return blocks.length > 0 ? blocks : [{ title: "Response", lines: [text] }];
  };

  const extractGeneratedImages = (trace: Record<string, unknown> | null): GeneratedImagePreview[] => {
    if (!trace) {
      return [];
    }
    const raw = trace.generated_images;
    if (!Array.isArray(raw)) {
      return [];
    }
    return raw
      .map((item, index) => {
        if (!item || typeof item !== "object") {
          return null;
        }
        const candidate = item as Record<string, unknown>;
        const imageUrl = typeof candidate.image_url === "string" ? candidate.image_url.trim() : "";
        if (!imageUrl) {
          return null;
        }
        return {
          title: typeof candidate.title === "string" ? candidate.title : `Preview ${index + 1}`,
          image_url: imageUrl,
          provider: typeof candidate.provider === "string" ? candidate.provider : "unknown",
          status: typeof candidate.status === "string" ? candidate.status : "ok",
          model: typeof candidate.model === "string" ? candidate.model : "unknown",
          error: typeof candidate.error === "string" ? candidate.error : undefined,
        } as GeneratedImagePreview;
      })
      .filter((item): item is GeneratedImagePreview => Boolean(item));
  };

  const extractImageProviderWarning = (
    trace: Record<string, unknown> | null,
    provider: ImageGeneratorProvider
  ): string | null => {
    if (!trace || provider !== "gemini") {
      return null;
    }

    const raw = trace.generated_images;
    if (!Array.isArray(raw)) {
      return null;
    }

    const geminiErrors: string[] = [];
    for (const item of raw) {
      if (!item || typeof item !== "object") {
        continue;
      }
      const candidate = item as Record<string, unknown>;
      const itemProvider = typeof candidate.provider === "string" ? candidate.provider.toLowerCase().trim() : "";
      const itemError = typeof candidate.error === "string" ? candidate.error.trim() : "";
      if (itemProvider === "gemini" && itemError) {
        geminiErrors.push(itemError);
      }
    }

    if (geminiErrors.length === 0) {
      return null;
    }

    const first = geminiErrors[0];
    const lowered = first.toLowerCase();
    if (lowered.includes("429") || lowered.includes("rate limit")) {
      return "Gemini image rate limited (429). Try again in a few seconds.";
    }
    if (lowered.includes("404") || lowered.includes("not found")) {
      return "Gemini image model unavailable (404). Try another Gemini image model.";
    }
    return `Gemini image provider error: ${first}`;
  };

  const hasVideoGeneratorNode = (): boolean => nodes.some((node) => node.type === "videoGenNode");

  const extractBrandFromCampaignId = (campaignId: string): string => {
    const found = campaignOptions.find((item) => item.id === campaignId);
    return found?.brand ?? "";
  };

  const setPrimaryAgentType = (value: MiniAgentType) => {
    setNodes((currentNodes) =>
      currentNodes.map((node) => {
        if (node.id !== "agent-1") {
          return node;
        }
        return {
          ...node,
          data: {
            ...(node.data as Record<string, unknown>),
            agentType: value,
          },
        };
      })
    );
  };

  useEffect(() => {
    void (async () => {
      try {
        const history = await listCampaignHistory(200);
        const options = (history.campaigns ?? [])
          .map((entry) => {
            const payload = entry.start_payload ?? {};
            return {
              id: entry.campaign_id,
              brand: String(payload.brand_name ?? "").trim(),
            };
          })
          .filter((item) => item.brand.length > 0);
        setCampaignOptions(options);
        if (!videoCampaignId && options[0]) {
          setVideoCampaignId(options[0].id);
          setVideoBrandName(options[0].brand);
        }
      } catch {
        setCampaignOptions([]);
      }
    })();
  }, []);

  const runFlow = async () => {
    const selectedAgent = resolveSelectedAgentType();
    const selectedImageProvider = resolveSelectedImageProvider();
    const shouldGenerateImages = selectedAgent === "image-prompter";
    const videoOnlyMode = hasVideoGeneratorNode();

    setImageProvider(selectedImageProvider);
    setRunning(true);
    setUploadError(null);
    setImageGenWarning(null);
    setVideoGenStatus(videoOnlyMode ? "running" : "idle");
    setImageGenStatus(videoOnlyMode ? "skipped" : shouldGenerateImages ? "running" : "skipped");
    setGeneratedVideos([]);
    try {
      if (videoOnlyMode) {
        const chosenCampaignId = videoCampaignId.trim();
        const chosenBrand = (videoBrandName.trim() || extractBrandFromCampaignId(chosenCampaignId)).trim();
        if (!chosenCampaignId || !chosenBrand) {
          setVideoGenStatus("error");
          setOutputValue("Vadoo routing requires both Video Campaign and Video Brand.");
          setOutputBlocks(parseOutputBlocks("Vadoo routing requires both Video Campaign and Video Brand."));
          setTraceValue({
            provider: "vadooai",
            route: "video-node",
            error: "Missing campaign_id or brand_name",
          });
          return;
        }

        const vadoo = await runVadooVideo({
          campaign_id: chosenCampaignId,
          brand_name: chosenBrand,
          duration: "5",
          aspect_ratio: "1:1",
        });

        if (vadoo.video_url) {
          setGeneratedVideos([
            {
              video_url: vadoo.video_url,
                provider: "vadooai",
              status: vadoo.status,
              model: vadoo.model,
              prompt: vadoo.prompt,
            },
          ]);
          setVideoGenStatus("completed");
          const vadooSummary = [
            "## Vadoo Video Output",
            `- Brand: ${vadoo.brand_name}`,
            `- Status: ${vadoo.status}`,
            `- Model: ${vadoo.model}`,
            vadoo.video_url ? `- Video URL: ${vadoo.video_url}` : "- Video URL: unavailable",
            "",
            "### Prompt",
            vadoo.prompt || "Prompt unavailable",
          ].join("\n");
          setOutputValue(vadooSummary);
          setOutputBlocks(parseOutputBlocks(vadooSummary));
          setTraceValue({
            provider: "vadooai",
            route: "video-node",
            model: vadoo.model,
            agent_type: "vadoo-video-generator",
            vadoo_video: vadoo,
          });
        } else {
          const vadooError = String(((vadoo.trace as Record<string, unknown>)?.vadoo as Record<string, unknown>)?.error || "").trim();
          const authFailure = vadooError.includes("401") || vadooError.toLowerCase().includes("invalid api key");
          const balanceFailure = vadooError.toLowerCase().includes("balance") || vadooError.toLowerCase().includes("credit");
          const rateLimitFailure = vadooError.includes("429");
          const actionable = authFailure
            ? "Vadoo authentication failed (HTTP 401). Check VADOO_AI_API_KEY in backend env."
            : balanceFailure
              ? "Vadoo request rejected: account balance is insufficient. Top up Vadoo credits."
              : rateLimitFailure
                ? "Vadoo request rate-limited (HTTP 429). Retry in a minute."
            : "Vadoo video generation did not return a playable URL.";
          setVideoGenStatus("error");
          setOutputValue(actionable);
          setOutputBlocks(parseOutputBlocks(actionable));
          setTraceValue({
            provider: "vadooai",
            route: "video-node",
            error: actionable,
            vadoo_video: vadoo,
          });
        }
        return;
      }

      const response = await runMiniAgent({
        input: inputValue,
        agent_type: selectedAgent,
        website_url: websiteUrl.trim() || undefined,
        context_notes: contextNotes.trim() || undefined,
        uploaded_assets: uploadedAssets,
        model_overrides: shouldGenerateImages
          ? {
              image_provider: selectedImageProvider,
              image_providers: [selectedImageProvider],
            }
          : {},
      });
      setOutputValue(response.output);
      setOutputBlocks(parseOutputBlocks(response.output));
      setTraceValue(response.trace);
      const previews = extractGeneratedImages(response.trace ?? null);
      const providerWarning = extractImageProviderWarning(response.trace ?? null, selectedImageProvider);
      setGeneratedImages(previews);
      setImageGenWarning(providerWarning);
      if (shouldGenerateImages) {
        setImageGenStatus(previews.length > 0 ? "completed" : "error");
      }

      setVideoGenStatus("idle");
    } catch (error) {
      setOutputValue(error instanceof Error ? error.message : "Live run failed");
      setOutputBlocks(parseOutputBlocks(error instanceof Error ? error.message : "Live run failed"));
      setGeneratedImages([]);
      setTraceValue(null);
      if (!videoOnlyMode && selectedImageProvider === "gemini") {
        setImageGenWarning("Gemini image request failed before provider response.");
      } else {
        setImageGenWarning(null);
      }
      setGeneratedVideos([]);
      setVideoGenStatus(videoOnlyMode ? "error" : "idle");
      setImageGenStatus(videoOnlyMode ? "skipped" : shouldGenerateImages ? "error" : "skipped");
    } finally {
      setRunning(false);
    }
  };

  const onAssetChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) {
      return;
    }
    try {
      const encoded = await Promise.all(
        files.map(async (file) => ({
          name: file.name,
          type: file.type || "application/octet-stream",
          size: file.size,
          base64: await toBase64(file),
        }))
      );
      setUploadedAssets((current) => [...current, ...encoded].slice(0, 4));
      setUploadError(null);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Failed to encode uploaded file");
    } finally {
      event.target.value = "";
    }
  };

  const syncNodes = useMemo(
    () =>
      nodes.map((node) => {
        if (node.id === "input-1") {
          return {
            ...node,
            data: { value: inputValue, onChange: setInputValue },
          };
        }
        if (node.id === "output-1") {
          return {
            ...node,
            data: { value: outputValue, blocks: outputBlocks, images: generatedImages, videos: generatedVideos },
          };
        }
        if (node.id === "videogen-1") {
          return {
            ...node,
            data: {
              status: videoGenStatus,
              provider: "vadooai",
              latestUrl: generatedVideos[0]?.video_url,
            },
          };
        }
        if (node.id === "imagegen-1") {
          return {
            ...node,
            data: {
              status: imageGenStatus,
              provider: imageProvider,
              warning: imageGenWarning,
              onProviderChange: (value: ImageGeneratorProvider) => {
                setImageProvider(value);
                setImageGenWarning(null);
                setNodes((currentNodes) =>
                  currentNodes.map((currentNode) => {
                    if (currentNode.id !== "imagegen-1") {
                      return currentNode;
                    }
                    return {
                      ...currentNode,
                      data: {
                        ...(currentNode.data as Record<string, unknown>),
                        provider: value,
                      },
                    };
                  })
                );
              },
            },
          };
        }
        return node;
      }),
    [generatedImages, generatedVideos, imageGenStatus, imageProvider, imageGenWarning, inputValue, nodes, outputBlocks, outputValue, videoGenStatus]
  );

  return (
    <div className="playground-shell">
      <aside className="playground-sidebar">
        <p className="mono overline">TOOL PALETTE</p>
        <h3>Mini Agents</h3>
        <p>Drag blocks into the canvas, connect them, and run with live website + image context.</p>
        <label className="play-config-label">
          Website URL
          <input
            className="play-config-input"
            value={websiteUrl}
            onChange={(event) => setWebsiteUrl(event.target.value)}
            placeholder="https://brand-site.com"
          />
        </label>
        <label className="play-config-label">
          Context Notes
          <textarea
            className="play-config-text"
            rows={3}
            value={contextNotes}
            onChange={(event) => setContextNotes(event.target.value)}
            placeholder="Add campaign angle, market constraints, tone constraints..."
          />
        </label>
        <label className="play-config-label">
          Upload Context Assets
          <input className="play-config-input" type="file" multiple accept="image/*,application/pdf" onChange={onAssetChange} />
        </label>
        <label className="play-config-label">
          Video Campaign
          <select
            className="play-config-input"
            value={videoCampaignId}
            onChange={(event) => {
              const value = event.target.value;
              setVideoCampaignId(value);
              const brand = extractBrandFromCampaignId(value);
              if (brand) {
                setVideoBrandName(brand);
              }
            }}
          >
            <option value="">Select campaign</option>
            {campaignOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.brand} · {option.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        <label className="play-config-label">
          Video Brand
          <input
            className="play-config-input"
            value={videoBrandName}
            onChange={(event) => setVideoBrandName(event.target.value)}
            placeholder="Brand identity source for Vadoo prompt"
          />
        </label>
        {uploadError && <p className="play-error">{uploadError}</p>}
        {uploadedAssets.length > 0 && (
          <ul className="play-asset-list">
            {uploadedAssets.map((asset) => (
              <li key={`${asset.name}-${asset.size}`} className="mono">
                {asset.name}
              </li>
            ))}
          </ul>
        )}
        <div className="palette-list">
          {sidebarItems.map((item) => (
            <button
              key={`${item.kind}-${item.label}`}
              type="button"
              draggable
              className="palette-item"
              onClick={() => {
                if ("agentType" in item && item.agentType) {
                  setPrimaryAgentType(item.agentType);
                }
              }}
              onDragStart={(event) =>
                onDragStart(event, {
                  kind: item.kind,
                  agentType: "agentType" in item ? item.agentType ?? "hook-writer" : "hook-writer",
                })
              }
            >
              {item.label}
            </button>
          ))}
        </div>
        <button type="button" className="primary-action" onClick={runFlow} disabled={running}>
          {running ? "RUNNING..." : "RUN FLOW ->"}
        </button>
        {traceValue && (
          <div className="play-trace-box">
            <p className="mono overline">LAST RUN TRACE</p>
            <pre>{JSON.stringify(traceValue, null, 2)}</pre>
          </div>
        )}
      </aside>

      <div className="playground-canvas" onDrop={onDrop} onDragOver={onDragOver}>
        <ReactFlow
          nodes={syncNodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          nodeTypes={nodeTypes}
          fitView
        >
          <Background color="#d3d8c3" gap={20} />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}

export function PlaygroundPage() {
  return (
    <section className="playground-page">
      <header className="playground-header">
        <p className="mono overline">LANGFLOW MINI MODE</p>
        <h2>Agent Playground</h2>
      </header>
      <ReactFlowProvider>
        <PlaygroundCanvas />
      </ReactFlowProvider>
    </section>
  );
}
