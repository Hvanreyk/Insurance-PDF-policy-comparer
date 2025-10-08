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

export interface PolicyData {
  policy_year?: string;
  insurer?: string;
  insured?: string;
  policy_number?: string;
  period_of_insurance?: PeriodOfInsurance;
  sums_insured: SumsInsured;
  premium: Premium;
  raw_text?: string;
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
