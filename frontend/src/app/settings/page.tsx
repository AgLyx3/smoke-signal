import type { Metadata } from "next";
import { SettingsForm } from "@/components/settings/SettingsForm";

export const metadata: Metadata = { title: "Settings · Cost Signals" };

export default function SettingsPage() {
  return <SettingsForm />;
}
