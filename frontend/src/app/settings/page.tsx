import type { Metadata } from "next";
import { SettingsForm } from "@/components/settings/SettingsForm";

export const metadata: Metadata = { title: "Settings · Smoke Signal" };

export default function SettingsPage() {
  return <SettingsForm />;
}
