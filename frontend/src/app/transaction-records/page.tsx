import type { Metadata } from "next";
import { TransactionRecords } from "@/components/TransactionRecords";

export const metadata: Metadata = { title: "Transaction records · Smoke Signal" };

export default function TransactionRecordsPage() {
  return <TransactionRecords />;
}
