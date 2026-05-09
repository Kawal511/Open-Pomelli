import { useEffect } from "react";
import { useCampaignStore } from "../store/campaignStore";
import { CampaignRouter } from "../components/CampaignRouter";

export function DashboardPage() {
  const { initialize } = useCampaignStore();

  useEffect(() => {
    void initialize();
  }, []);

  return <CampaignRouter />;
}
