import { Link } from "react-router-dom";
import { DebugState } from "../components/states/DebugState";

export function DebugPage() {
  return (
    <section className="debug-page-shell">
      <div className="debug-page-topbar mono">
        <Link to="/dashboard" className="debug-back-link">
          Back to Dashboard
        </Link>
      </div>
      <DebugState />
    </section>
  );
}
