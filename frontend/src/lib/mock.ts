import type {
  Config,
  Finding,
  Findings,
  NarrateRequest,
  NarrateResponse,
  RunRequest,
  Stage,
  VendorSummary,
} from "./types";

// Demo company: Lumen Labs, Series A AI company, ~$500K/mo, ~42 cardholders.
// Numbers are deterministic; `mockRun` applies the request's config, overrides and
// open issues on top so the settings and ask flows behave like the real pipeline.

export const MOCK_DEFAULT_CONFIG: Config = {
  thresholds: {
    usage: { alert_pct: 0.01, alerts: true },
    fixed: { alert_pct: 0.01, alerts: true },
    headcount: { alert_pct: 0.01, alerts: true },
    annual: { alert_pct: 0.01, alerts: false },
    payroll: { alert_pct: 0.01, alerts: false },
  },
  report_floor_pct: 0.0025,
  buffer_months: 3,
  treasury_apy: 0.038,
};

const VENDORS: VendorSummary[] = [
  { vendor: "Gusto", category: "Payroll", cost_type: "payroll", cost_type_source: "taxonomy", cadence: "semi-monthly", monthly_spend: 331200, growth_pct: null },
  { vendor: "Deel", category: "Payroll", cost_type: "payroll", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 12400, growth_pct: null },
  { vendor: "Anthropic", category: "AI APIs", cost_type: "usage", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 25550, growth_pct: 0.15 },
  { vendor: "OpenAI", category: "AI APIs", cost_type: "usage", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 18200, growth_pct: 0.08 },
  { vendor: "Pinecone", category: "AI APIs", cost_type: "usage", cost_type_source: "llm", cadence: "monthly", monthly_spend: 1000, growth_pct: null },
  { vendor: "AWS", category: "Infrastructure", cost_type: "usage", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 27800, growth_pct: 0.05 },
  { vendor: "Modal", category: "Infrastructure", cost_type: "usage", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 8500, growth_pct: 0.12 },
  { vendor: "Datadog", category: "Infrastructure", cost_type: "usage", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 9840, growth_pct: 0.06 },
  { vendor: "Vercel", category: "Infrastructure", cost_type: "usage", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 2300, growth_pct: 0.03 },
  { vendor: "Figma", category: "Software", cost_type: "fixed", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 3000, growth_pct: null },
  { vendor: "Notion", category: "Software", cost_type: "headcount", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 1012, growth_pct: null },
  { vendor: "Linear", category: "Software", cost_type: "headcount", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 1344, growth_pct: null },
  { vendor: "Slack", category: "Software", cost_type: "headcount", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 2940, growth_pct: null },
  { vendor: "GitHub", category: "Software", cost_type: "headcount", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 1890, growth_pct: null },
  { vendor: "Google Workspace", category: "Software", cost_type: "headcount", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 1260, growth_pct: null },
  { vendor: "Loom", category: "Software", cost_type: "headcount", cost_type_source: "llm", cadence: "monthly", monthly_spend: 1440, growth_pct: null },
  { vendor: "1Password", category: "Software", cost_type: "headcount", cost_type_source: "llm", cadence: "monthly", monthly_spend: 336, growth_pct: null },
  { vendor: "Zoom", category: "Software", cost_type: "headcount", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 0, growth_pct: null },
  { vendor: "Vanta", category: "Professional services", cost_type: "annual", cost_type_source: "taxonomy", cadence: "annual", monthly_spend: 1500, growth_pct: null },
  { vendor: "Pilot", category: "Professional services", cost_type: "fixed", cost_type_source: "taxonomy", cadence: "monthly", monthly_spend: 4200, growth_pct: null },
  { vendor: "Cooley LLP", category: "Professional services", cost_type: "fixed", cost_type_source: "llm", cadence: "irregular", monthly_spend: 8400, growth_pct: null },
  { vendor: "United Airlines", category: "Travel", cost_type: "fixed", cost_type_source: "taxonomy", cadence: "irregular", monthly_spend: 4600, growth_pct: null },
  { vendor: "Marriott Hotels", category: "Travel", cost_type: "fixed", cost_type_source: "llm", cadence: "irregular", monthly_spend: 1180, growth_pct: null },
];

const CATEGORY_TOTALS: Record<string, number> = {
  Payroll: 343600,
  "AI APIs": 44750,
  Infrastructure: 48440,
  Software: 13222,
  "Professional services": 14100,
  Travel: 5780,
  "Card spend (other)": 28508,
};

const ANTHROPIC_ALERT: Finding = {
  id: "anthropic:growth_break",
  vendor: "Anthropic",
  category: "AI APIs",
  cost_type: "usage",
  cost_type_source: "taxonomy",
  kind: "growth_break",
  route: "alert",
  actual_monthly: 35550,
  impact_monthly: 10000,
  impact_pct_of_spend: 0.0199,
  baseline: { n_obs: 12, expected_monthly: 25550, growth_pct: 0.15, sigma: 0.07, last_price: null, cost_per_head: null },
  drivers: [
    { driver: "volume", share: 0.8 },
    { driver: "price", share: 0.2 },
  ],
  confidence: "high",
  ask_cost_type: false,
  escalation_of: null,
  cardholders: ["Sam O.", "Priya N."],
};

const PINECONE_ALERT: Finding = {
  id: "pinecone:new_vendor",
  vendor: "Pinecone",
  category: "AI APIs",
  cost_type: "usage",
  cost_type_source: "llm",
  kind: "new_vendor",
  route: "alert",
  actual_monthly: 6500,
  impact_monthly: 6500,
  impact_pct_of_spend: 0.013,
  baseline: { n_obs: 2, expected_monthly: 0, growth_pct: null, sigma: null, last_price: null, cost_per_head: null },
  drivers: [{ driver: "new", share: 1 }],
  confidence: "medium",
  ask_cost_type: true,
  escalation_of: null,
  cardholders: ["Sam O."],
};

const HISTORY: Findings = {
  stage: "history",
  window_start: "2025-09-01",
  window_end: "2026-08-31",
  trailing_monthly_spend: 498400,
  headcount_proxy: 42,
  findings: [
    {
      id: "gusto:growth_break",
      vendor: "Gusto",
      category: "Payroll",
      cost_type: "payroll",
      cost_type_source: "taxonomy",
      kind: "growth_break",
      route: "report",
      actual_monthly: 331200,
      impact_monthly: 46800,
      impact_pct_of_spend: 0.094,
      baseline: { n_obs: 24, expected_monthly: 284400, growth_pct: null, sigma: null, last_price: null, cost_per_head: 7886 },
      drivers: [{ driver: "who", share: 1 }],
      confidence: "high",
      ask_cost_type: false,
      escalation_of: null,
      cardholders: [],
    },
    {
      id: "marriott:spike",
      vendor: "Marriott Hotels",
      category: "Travel",
      cost_type: "fixed",
      cost_type_source: "llm",
      kind: "spike",
      route: "report",
      actual_monthly: 14200,
      impact_monthly: 14200,
      impact_pct_of_spend: 0.0285,
      baseline: { n_obs: 3, expected_monthly: 0, growth_pct: null, sigma: null, last_price: null, cost_per_head: null },
      drivers: [{ driver: "volume", share: 1 }],
      confidence: "high",
      ask_cost_type: false,
      escalation_of: null,
      cardholders: ["Dana K."],
    },
    {
      id: "datadog:growth_break",
      vendor: "Datadog",
      category: "Infrastructure",
      cost_type: "usage",
      cost_type_source: "taxonomy",
      kind: "growth_break",
      route: "report",
      actual_monthly: 9840,
      impact_monthly: 1140,
      impact_pct_of_spend: 0.0023,
      baseline: { n_obs: 12, expected_monthly: 8700, growth_pct: 0.06, sigma: 0.05, last_price: null, cost_per_head: null },
      drivers: [
        { driver: "volume", share: 0.7 },
        { driver: "price", share: 0.3 },
      ],
      confidence: "medium",
      ask_cost_type: false,
      escalation_of: null,
      cardholders: ["Priya N."],
    },
    {
      id: "zoom:stopped",
      vendor: "Zoom",
      category: "Software",
      cost_type: "headcount",
      cost_type_source: "taxonomy",
      kind: "stopped",
      route: "report",
      actual_monthly: 0,
      impact_monthly: -890,
      impact_pct_of_spend: -0.0018,
      baseline: { n_obs: 9, expected_monthly: 890, growth_pct: null, sigma: null, last_price: 890, cost_per_head: 23 },
      drivers: [{ driver: "missing", share: 1 }],
      confidence: "high",
      ask_cost_type: false,
      escalation_of: null,
      cardholders: ["Dana K."],
    },
    {
      id: "linear:per_head",
      vendor: "Linear",
      category: "Software",
      cost_type: "headcount",
      cost_type_source: "taxonomy",
      kind: "per_head",
      route: "report",
      actual_monthly: 1344,
      impact_monthly: 168,
      impact_pct_of_spend: 0.0003,
      baseline: { n_obs: 12, expected_monthly: 1176, growth_pct: null, sigma: null, last_price: null, cost_per_head: 28 },
      drivers: [{ driver: "price", share: 1 }],
      confidence: "medium",
      ask_cost_type: false,
      escalation_of: null,
      cardholders: ["Priya N."],
    },
  ],
  vendors: VENDORS,
  category_totals: CATEGORY_TOTALS,
};

const INJECT_1: Findings = {
  stage: "inject-1",
  window_start: "2026-09-01",
  window_end: "2026-09-05",
  trailing_monthly_spend: 502300,
  headcount_proxy: 42,
  findings: [ANTHROPIC_ALERT, PINECONE_ALERT],
  vendors: VENDORS.map((v) =>
    v.vendor === "Anthropic"
      ? { ...v, monthly_spend: 35550 }
      : v.vendor === "Pinecone"
        ? { ...v, monthly_spend: 6500 }
        : v,
  ),
  category_totals: { ...CATEGORY_TOTALS, "AI APIs": 60250 },
};

const INJECT_2: Findings = {
  stage: "inject-2",
  window_start: "2026-09-01",
  window_end: "2026-09-30",
  trailing_monthly_spend: 511800,
  headcount_proxy: 43,
  findings: [
    {
      ...ANTHROPIC_ALERT,
      actual_monthly: 36900,
      impact_monthly: 11350,
      impact_pct_of_spend: 0.0222,
    },
    {
      ...PINECONE_ALERT,
      baseline: { ...PINECONE_ALERT.baseline, n_obs: 3 },
      ask_cost_type: false,
    },
    {
      id: "figma:price_change",
      vendor: "Figma",
      category: "Software",
      cost_type: "fixed",
      cost_type_source: "taxonomy",
      kind: "price_change",
      route: "report",
      actual_monthly: 3660,
      impact_monthly: 660,
      impact_pct_of_spend: 0.0013,
      baseline: { n_obs: 12, expected_monthly: 3000, growth_pct: null, sigma: null, last_price: 3000, cost_per_head: null },
      drivers: [{ driver: "price", share: 1 }],
      confidence: "high",
      ask_cost_type: false,
      escalation_of: null,
      cardholders: ["Dana K."],
    },
    {
      id: "notion:per_head",
      vendor: "Notion",
      category: "Software",
      cost_type: "headcount",
      cost_type_source: "taxonomy",
      kind: "per_head",
      route: "report",
      actual_monthly: 1462,
      impact_monthly: 430,
      impact_pct_of_spend: 0.0008,
      baseline: { n_obs: 12, expected_monthly: 1032, growth_pct: null, sigma: null, last_price: null, cost_per_head: 24 },
      drivers: [
        { driver: "price", share: 0.65 },
        { driver: "who", share: 0.35 },
      ],
      confidence: "medium",
      ask_cost_type: false,
      escalation_of: null,
      cardholders: ["Dana K."],
    },
    {
      id: "loom:stopped",
      vendor: "Loom",
      category: "Software",
      cost_type: "headcount",
      cost_type_source: "llm",
      kind: "stopped",
      route: "report",
      actual_monthly: 0,
      impact_monthly: -1440,
      impact_pct_of_spend: -0.0028,
      baseline: { n_obs: 8, expected_monthly: 1440, growth_pct: null, sigma: null, last_price: 1440, cost_per_head: 34 },
      drivers: [{ driver: "missing", share: 1 }],
      confidence: "high",
      ask_cost_type: false,
      escalation_of: null,
      cardholders: ["Marcus T."],
    },
    {
      id: "modal:growth_break",
      vendor: "Modal",
      category: "Infrastructure",
      cost_type: "usage",
      cost_type_source: "taxonomy",
      kind: "growth_break",
      route: "report",
      actual_monthly: 6400,
      impact_monthly: -2100,
      impact_pct_of_spend: -0.0041,
      baseline: { n_obs: 12, expected_monthly: 8500, growth_pct: 0.12, sigma: 0.09, last_price: null, cost_per_head: null },
      drivers: [{ driver: "volume", share: 1 }],
      confidence: "medium",
      ask_cost_type: false,
      escalation_of: null,
      cardholders: ["Priya N."],
    },
    {
      id: "vanta:renewal",
      vendor: "Vanta",
      category: "Professional services",
      cost_type: "annual",
      cost_type_source: "taxonomy",
      kind: "renewal",
      route: "report",
      actual_monthly: 18000,
      impact_monthly: 18000,
      impact_pct_of_spend: 0.0352,
      baseline: { n_obs: 2, expected_monthly: 18000, growth_pct: null, sigma: null, last_price: 18000, cost_per_head: null },
      drivers: [{ driver: "price", share: 1 }],
      confidence: "high",
      ask_cost_type: false,
      escalation_of: null,
      cardholders: [],
    },
    {
      id: "gusto:growth_break",
      vendor: "Gusto",
      category: "Payroll",
      cost_type: "payroll",
      cost_type_source: "taxonomy",
      kind: "growth_break",
      route: "report",
      actual_monthly: 338400,
      impact_monthly: 7200,
      impact_pct_of_spend: 0.0141,
      baseline: { n_obs: 25, expected_monthly: 331200, growth_pct: null, sigma: null, last_price: null, cost_per_head: 7886 },
      drivers: [{ driver: "who", share: 1 }],
      confidence: "high",
      ask_cost_type: false,
      escalation_of: null,
      cardholders: [],
    },
  ],
  vendors: VENDORS.map((v) => {
    switch (v.vendor) {
      case "Anthropic":
        return { ...v, monthly_spend: 36900 };
      case "Pinecone":
        return { ...v, monthly_spend: 6500 };
      case "Figma":
        return { ...v, monthly_spend: 3660 };
      case "Notion":
        return { ...v, monthly_spend: 1462 };
      case "Loom":
        return { ...v, monthly_spend: 0 };
      case "Modal":
        return { ...v, monthly_spend: 6400 };
      case "Gusto":
        return { ...v, monthly_spend: 338400 };
      default:
        return v;
    }
  }),
  category_totals: { ...CATEGORY_TOTALS, Payroll: 350800, "AI APIs": 61600, Infrastructure: 46340, Software: 13892 },
};

export const MOCK_FINDINGS: Record<Stage, Findings> = {
  history: HISTORY,
  "inject-1": INJECT_1,
  "inject-2": INJECT_2,
};

export const MOCK_NARRATION: Record<Stage, NarrateResponse> = {
  history: {
    alerts: [],
    report: {
      intro:
        "Twelve months of Lumen Labs spend, Sep 2025 through Aug 2026. Trailing monthly spend is $498K across 23 recurring vendors and 42 cardholders. Nothing meets an alert threshold. Five things are worth knowing, listed by size.",
      needs_attention: [],
      worth_knowing: {
        Payroll: [
          {
            finding_id: "gusto:growth_break",
            text: "Gusto payroll stepped from $284K to $331K a month across the April–May hiring wave. Cost per head is flat at about $7.9K, so the increase is headcount, not pay. Distinct cardholders went from 34 to 42 over the same period.",
          },
        ],
        Travel: [
          {
            finding_id: "marriott:spike",
            text: "A one-off $14,200 at Marriott Hotels in June, on Dana K.'s card, matching the team offsite. Nothing since. Treated as non-recurring and kept out of the travel baseline.",
          },
        ],
        Infrastructure: [
          {
            finding_id: "datadog:growth_break",
            text: "Datadog ran about 13% above its 6%-a-month trend in August: $9,840 against $8,700 expected. Roughly two-thirds volume (more hosts and logs) and one-third price. At 0.2% of monthly spend it is below the alert line; noted so a second month is not a surprise.",
          },
        ],
        Software: [
          {
            finding_id: "zoom:stopped",
            text: "Zoom's monthly charge of about $890 has not appeared since May. Meeting spend did not move elsewhere, so this reads as a cancellation rather than a failed payment. Baseline retired.",
          },
          {
            finding_id: "linear:per_head",
            text: "Linear's cost per cardholder went from $28 to $32 in July with the seat count unchanged, consistent with a plan change. Small: $168 a month.",
          },
        ],
      },
    },
  },
  "inject-1": {
    alerts: [
      {
        finding_id: "anthropic:growth_break",
        headline: "Anthropic's September invoice is about $10,000 a month above its trend, around 2% of monthly spend.",
        what_moved:
          "The invoice that settled on Sep 4 was $35,550. From the trailing twelve months, $25,550 was expected. Anthropic had been growing about 15% a month; this month's step is about 60%.",
        why:
          "About 80% of the increase is volume (more tokens) and about 20% is mix (a larger share on the higher-priced model). Twelve months of history with a tight fit make this a high-confidence read. The charge is on Sam O.'s card; Priya N. also carries this vendor. Not known from the transaction: which workload drove the volume.",
      },
      {
        finding_id: "pinecone:new_vendor",
        headline: "Pinecone is now a recurring cost at $6,500 a month, about 1.3% of monthly spend.",
        what_moved:
          "A second invoice on Sep 4 confirms recurrence. The first was $1,000 in August. Pinecone is new to Lumen Labs and not in the taxonomy, so its cost type is inferred, not confirmed.",
        why:
          "The driver is entirely new spend. There is no baseline, so the expected amount is $0 and confidence is medium. Cardholder: Sam O. Not known: whether $6,500 is the run rate or a one-time backfill of an index.",
      },
    ],
    report: null,
  },
  "inject-2": {
    alerts: [],
    report: {
      intro:
        "September closed at $512K, up 2.7% from August. The two issues raised on Sep 5 are still open and account for most of the increase; nothing new crossed an alert threshold this month. Five items worth knowing below, plus payroll for context.",
      needs_attention: [
        {
          finding_id: "anthropic:growth_break",
          text: "Anthropic held at the new level: $36,900 for September, about $11,350 a month above its pre-September trend. Open since Sep 5; not a material escalation from the Sep 4 invoice.",
        },
        {
          finding_id: "pinecone:new_vendor",
          text: "Pinecone billed $6,500 again on Sep 30, its third invoice. This now looks like a run rate rather than a one-time backfill. Open since Sep 5.",
        },
      ],
      worth_knowing: {
        Software: [
          {
            finding_id: "figma:price_change",
            text: "Figma's monthly charge went from $3,000 to $3,660 (+22%) on Sep 14 with the same seat count. Consistent with a plan repricing; 0.1% of spend, so below the alert line.",
          },
          {
            finding_id: "notion:per_head",
            text: "Notion is growing faster than headcount: $34 per cardholder in September against $24 over the prior six months. About two-thirds of the increase is per-seat price, the rest added seats. Not known: whether an add-on was enabled.",
          },
          {
            finding_id: "loom:stopped",
            text: "Loom's $1,440 monthly charge did not arrive. It was due about Sep 18 and is 12 days overdue. Either cancelled or a failed payment; the card on file is Marcus T.'s.",
          },
        ],
        Infrastructure: [
          {
            finding_id: "modal:growth_break",
            text: "Modal came in $2,100 under its trend: $6,400 against $8,500 expected. Volume dropped mid-month; the timing matches the batch pipeline moving to reserved capacity. A decrease, listed for completeness.",
          },
        ],
        "Professional services": [
          {
            finding_id: "vanta:renewal",
            text: "Vanta's annual renewal is due around Oct 12, based on last year's charge date. Last year it was $18,000. No signal yet on this year's price.",
          },
        ],
        Payroll: [
          {
            finding_id: "gusto:growth_break",
            text: "Gusto payroll was $338K in September, up $7,200 from August. Two September starts; cost per head unchanged. Context, not a signal.",
          },
        ],
      },
    },
  },
};

const ALWAYS_REPORT_KINDS: ReadonlySet<Finding["kind"]> = new Set(["renewal", "spike"]);

/** Same Findings the pipeline would return for this request: base data, then overrides,
 *  thresholds and open-issue dedupe applied in that order. */
export function mockRun(req: RunRequest): Findings {
  const base = structuredClone(MOCK_FINDINGS[req.stage]);
  const config = req.config ?? MOCK_DEFAULT_CONFIG;
  const overrides = new Map(req.overrides.map((o) => [o.vendor, o.cost_type]));

  base.vendors = base.vendors.map((v) => {
    const ct = overrides.get(v.vendor);
    return ct ? { ...v, cost_type: ct, cost_type_source: "user" } : v;
  });

  base.findings = base.findings.map((f) => {
    const next: Finding = { ...f };
    const ct = overrides.get(f.vendor);
    if (ct) {
      next.cost_type = ct;
      next.cost_type_source = "user";
      next.ask_cost_type = false;
    }

    const th = config.thresholds[next.cost_type] ?? MOCK_DEFAULT_CONFIG.thresholds[next.cost_type];
    const contextOnly = ALWAYS_REPORT_KINDS.has(next.kind) || next.cost_type === "annual" || next.cost_type === "payroll";
    const material = th.alerts && Math.abs(next.impact_pct_of_spend) >= th.alert_pct;
    next.route = !contextOnly && material ? "alert" : "report";
    next.escalation_of = null;

    const open = req.open_issues.find((o) => o.id === next.id || (o.vendor === next.vendor && o.kind === next.kind));
    if (open && next.route === "alert") {
      const escalated = Math.abs(next.impact_monthly) >= 1.5 * Math.abs(open.impact_monthly);
      if (escalated) next.escalation_of = open.id;
      else next.route = "report";
    }
    return next;
  });

  return base;
}

export function mockNarrate(req: NarrateRequest): NarrateResponse {
  const canned = structuredClone(MOCK_NARRATION[req.findings.stage]);
  if (req.mode === "alerts") {
    const alerting = new Set(req.findings.findings.filter((f) => f.route === "alert").map((f) => f.id));
    return { alerts: canned.alerts.filter((a) => alerting.has(a.finding_id)), report: null };
  }
  return { alerts: [], report: canned.report };
}
