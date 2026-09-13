import type { Metadata } from "next";
import { TransactionRecords } from "@/components/TransactionRecords";

export const metadata: Metadata = { title: "Transaction records · Cost Signals" };

export default function TransactionRecordsPage() {
  return <TransactionRecords />;
}
