import { useCampaignStore } from "../../store/campaignStore";

export function GeneratingState() {
  const { progress } = useCampaignStore();

  const steps = [
    "Understanding Brand",
    "Analyzing Market",
    "Generating Creatives",
    "Building Schedule",
  ];

  return (
    <section className="generating-shell">
      <h1>Generating Campaign</h1>

      <div className="generating-grid">
        {steps.map((step) => {
          const done = progress.completed.includes(step);
          const active = progress.step === step;

          return (
            <div
              key={step}
              className={active ? "generating-step generating-step-active" : done ? "generating-step generating-step-done" : "generating-step"}
            >
              <div className="generating-step-head">
                <span className="mono overline">{step}</span>
                <span className={done ? "step-dot step-dot-done" : active ? "step-dot step-dot-active" : "step-dot"} />
              </div>

              <p className="generating-step-status">
                {done ? "✓ Completed" : active ? "⏳ In progress..." : "⋯ Pending"}
              </p>
            </div>
          );
        })}
      </div>

      <div className="generating-active-row">
        <div className="mini-loader" />
        <p className="mono">
          Current step: {progress.step || "Starting..."}
        </p>
      </div>
    </section>
  );
}
