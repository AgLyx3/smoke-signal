import type { components } from "./api-types";

// Short aliases over the generated contract. `api-types.ts` stays the source of truth.
export type Schemas = components["schemas"];

export type Findings = Schemas["Findings"];
export type Finding = Schemas["Finding"];
export type Baseline = Schemas["Baseline"];
export type DriverShare = Schemas["DriverShare"];
export type VendorSummary = Schemas["VendorSummary"];
export type Config = Schemas["Config"];
export type TypeThreshold = Schemas["TypeThreshold"];
export type Override = Schemas["Override"];
export type OpenIssue = Schemas["OpenIssue"];
export type RunRequest = Schemas["RunRequest"];
export type NarrateRequest = Schemas["NarrateRequest"];
export type NarrateResponse = Schemas["NarrateResponse"];
export type AlertText = Schemas["AlertText"];
export type ReportText = Schemas["ReportText"];
export type ReportItemText = Schemas["ReportItemText"];

export type Stage = Findings["stage"];
export type CostType = Finding["cost_type"];
export type CostTypeSource = Finding["cost_type_source"];
export type Kind = Finding["kind"];
export type Route = Finding["route"];
export type Confidence = Finding["confidence"];
export type Driver = DriverShare["driver"];

export const STAGES: Stage[] = ["history", "inject-1", "inject-2"];
export const COST_TYPES: CostType[] = ["usage", "fixed", "headcount", "annual", "payroll"];

export function stageIndex(stage: Stage): number {
  return STAGES.indexOf(stage);
}
