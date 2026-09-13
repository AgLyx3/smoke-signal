import { DemoShell } from "@/components/DemoShell";
import { Sidebar } from "@/components/slack/Sidebar";
import { TopBar } from "@/components/slack/TopBar";

export default function Home() {
  return <DemoShell topBar={<TopBar />} sidebar={<Sidebar />} />;
}
