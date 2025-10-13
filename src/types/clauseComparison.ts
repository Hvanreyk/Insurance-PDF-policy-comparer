export type ClauseStatus = 'added' | 'removed' | 'modified' | 'unchanged';

export type ClauseType =
  | 'All Types'
  | 'Coverage'
  | 'Exclusion'
  | 'Condition'
  | 'Definition'
  | 'Warranty'
  | 'Extension'
  | 'Endorsement'
  | 'Subjectivity'
  | 'Deductible';

export interface TokenDiff {
  added: string[];
  removed: string[];
}

export interface Evidence {
  a?: {
    page_start: number;
    page_end: number;
  };
  b?: {
    page_start: number;
    page_end: number;
  };
}

export interface NumericFieldDelta {
  a: number | null;
  b: number | null;
  pct: number | null;
}

export type NumericDelta = Record<string, NumericFieldDelta>;

export interface ClauseMatch {
  a_id: string | null;
  b_id: string | null;
  similarity: number | null;
  status: ClauseStatus;
  token_diff: TokenDiff | null;
  numeric_delta: NumericDelta | null;
  materiality_score: number;
  strictness_delta: number;
  review_required: boolean;
  evidence: Evidence;
  clause_type?: ClauseType;
  a_text?: string | null;
  b_text?: string | null;
  a_title?: string | null;
  b_title?: string | null;
}

export interface Counts {
  added: number;
  removed: number;
  modified: number;
  unchanged: number;
}

export interface Summary {
  counts: Counts;
  bullets: string[];
}

export interface Timings {
  parse_a: number;
  parse_b: number;
  align: number;
  diff: number;
  total: number;
}

export interface UCCComparisonResult {
  summary: Summary;
  matches: ClauseMatch[];
  unmapped_a: string[];
  unmapped_b: string[];
  warnings: string[];
  timings_ms: Timings;
}

export interface FilterState {
  statuses: Set<ClauseStatus>;
  clauseType: ClauseType;
  materialityRange: 'all' | 'high' | 'medium' | 'low';
  reviewRequired: boolean | null;
}
