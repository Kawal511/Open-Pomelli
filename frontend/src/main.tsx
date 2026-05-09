import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ClerkProvider } from "@clerk/clerk-react";
import App from "./App.tsx";
import "./index.css";

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined;
const authMode = String(import.meta.env.VITE_AUTH_MODE ?? "clerk").toLowerCase();
const authEnabled = authMode !== "disabled";

function MissingClerkConfig() {
  return (
    <div style={{ padding: 24, fontFamily: "Inter, sans-serif" }}>
      <h2>Clerk Configuration Missing</h2>
      <p>Set VITE_CLERK_PUBLISHABLE_KEY in frontend/.env to enable login, or set VITE_AUTH_MODE=disabled for local dev.</p>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {!authEnabled ? (
      <BrowserRouter>
        <App />
      </BrowserRouter>
    ) : clerkPublishableKey ? (
      <ClerkProvider publishableKey={clerkPublishableKey}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ClerkProvider>
    ) : (
      <MissingClerkConfig />
    )}
  </StrictMode>,
)
