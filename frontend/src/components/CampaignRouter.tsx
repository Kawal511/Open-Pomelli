import { useCampaignStore } from "../store/campaignStore";
import { EmptyState } from "./states/EmptyState";
import { GeneratingState } from "./states/GeneratingState";
import { OutputState } from "./states/OutputState";
import { DebugState } from "./states/DebugState";
import { LoadingSpinner } from "./LoadingSpinner";

export function CampaignRouter() {
  const { uiState, status, isLoading } = useCampaignStore();
  const showLoading = isLoading || status?.status === "queued";

  return (
    <>
      <LoadingSpinner isVisible={showLoading} showMessages={true} />
      {uiState === "EMPTY" && <EmptyState />}
      {uiState === "GENERATING" && <GeneratingState />}
      {uiState === "OUTPUT" && <OutputState />}
      {uiState === "DEBUG" && <DebugState />}
    </>
  );
}
