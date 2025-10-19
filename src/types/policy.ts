export interface Premium {
  base?: number;
  fsl?: number;
  gst?: number;
  stamp?: number;
  total?: number;
}

export interface SumsInsured {
  contents?: number;
  theft_total?: number;
  bi_turnover?: number;
  public_liability?: number;
  property_in_your_control?: number;
}

export interface PeriodOfInsurance {
  from: string;
  to: string;
}

export interface PolicyBlock {
  id: string;
  text: string;
  page_number?: number;
  bbox?: [number, number, number, number];
  section_path?: string[];
  is_admin?: boolean;
  clause_type?: string;
  ors?: number;
  ors_threshold?: number;
  is_operational?: boolean;
  max_sim_positive?: number;
  max_sim_negative?: number;
  concepts?: string[];
  cues?: string[];
  why_kept?: string[];
}

export interface PolicyData {
  policy_year?: string;
  insurer?: string;
  insured?: string;
  policy_number?: string;
  period_of_insurance?: PeriodOfInsurance;
  sums_insured: SumsInsured;
  premium: Premium;
  raw_text?: string;
  blocks?: PolicyBlock[];
}

export interface ComparisonDelta {
  a: number | null;
  b: number | null;
  delta_abs: number | null;
  delta_pct: number | null;
}

export interface ComparisonResult {
  [key: string]: ComparisonDelta;
}
