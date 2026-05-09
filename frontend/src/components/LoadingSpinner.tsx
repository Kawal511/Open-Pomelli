import { useEffect, useState } from "react";

const LOADING_MESSAGES = [
  "Initializing campaign runtime...",
  "Syncing latest campaign state...",
  "Preparing creative graph...",
  "Applying brand style pipeline...",
  "Finalizing content handoff...",
];

interface LoadingSpinnerProps {
  isVisible: boolean;
  message?: string;
  showMessages?: boolean;
}

export function LoadingSpinner({ isVisible, message, showMessages = true }: LoadingSpinnerProps) {
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    if (!isVisible || !showMessages) return;

    const timer = setInterval(() => {
      setMessageIndex((prev) => (prev + 1) % LOADING_MESSAGES.length);
    }, 1100);

    return () => clearInterval(timer);
  }, [isVisible, showMessages]);

  if (!isVisible) return null;

  const currentMessage = message || LOADING_MESSAGES[messageIndex];

  return (
    <div className="loading-spinner-overlay">
      <div className="loading-spinner-container">
        <div className="neon-loader">
          <div className="neon-ring neon-ring-1"></div>
          <div className="neon-ring neon-ring-2"></div>
          <div className="neon-ring neon-ring-3"></div>
          <div className="neon-center-dot"></div>
        </div>
        <p className="loading-message mono">{currentMessage}</p>
        <div className="loading-progress-bar">
          <div className="loading-progress-fill"></div>
        </div>
      </div>
    </div>
  );
}
