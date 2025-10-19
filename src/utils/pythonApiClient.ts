import { PolicyBlock, PolicyData } from '../types/policy';
import { UCCComparisonResult } from '../types/clauseComparison';

const API_URL = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:8000';

const parseOptionalNumber = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return undefined;
};

const normalisePolicyData = (data: any): PolicyData => {
  const metadata = data?.metadata ?? {};
  const sumsInsuredSource = data?.sums_insured ?? metadata?.sums_insured ?? {};
  const premiumSource = data?.premium ?? metadata?.premium ?? {};

  const policyData: PolicyData = {
    policy_year: data?.policy_year ?? metadata?.policy_year ?? undefined,
    insurer: data?.insurer ?? metadata?.insurer ?? undefined,
    insured: data?.insured ?? metadata?.insured ?? undefined,
    policy_number: data?.policy_number ?? metadata?.policy_number ?? undefined,
    period_of_insurance:
      data?.period_of_insurance ?? metadata?.period_of_insurance ?? undefined,
    sums_insured: {
      contents: parseOptionalNumber(sumsInsuredSource?.contents),
      theft_total: parseOptionalNumber(sumsInsuredSource?.theft_total),
      bi_turnover: parseOptionalNumber(sumsInsuredSource?.bi_turnover),
      public_liability: parseOptionalNumber(sumsInsuredSource?.public_liability),
      property_in_your_control: parseOptionalNumber(
        sumsInsuredSource?.property_in_your_control
      ),
    },
    premium: {
      base: parseOptionalNumber(premiumSource?.base),
      fsl: parseOptionalNumber(premiumSource?.fsl),
      gst: parseOptionalNumber(premiumSource?.gst),
      stamp: parseOptionalNumber(premiumSource?.stamp),
      total: parseOptionalNumber(premiumSource?.total),
    },
    raw_text: data?.raw_text ?? metadata?.raw_text ?? undefined,
  };

  if (Array.isArray(data?.blocks)) {
    policyData.blocks = data.blocks as PolicyBlock[];
    if (!policyData.raw_text) {
      const combinedText = policyData.blocks
        .map((block) => (typeof block.text === 'string' ? block.text.trim() : ''))
        .filter(Boolean)
        .join('\n\n');
      policyData.raw_text = combinedText || undefined;
    }
  }

  return policyData;
};

export const parsePolicyPDFViaPython = async (file: File): Promise<PolicyData> => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_URL}/ucc/preprocess`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to parse PDF');
  }

  const data = await response.json();
  return normalisePolicyData(data);
};

export const comparePoliciesViaPython = async (
  policyA: File,
  policyB: File
): Promise<{ policy_a: PolicyData; policy_b: PolicyData; comparison: any }> => {
  const formData = new FormData();
  formData.append('policy_a', policyA);
  formData.append('policy_b', policyB);

  const response = await fetch(`${API_URL}/api/compare-policies`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to compare policies');
  }

  return await response.json();
};

export const compareClausesViaPython = async (
  fileA: File,
  fileB: File,
  options?: Record<string, any>
): Promise<UCCComparisonResult> => {
  const formData = new FormData();
  formData.append('file_a', fileA);
  formData.append('file_b', fileB);

  if (options) {
    formData.append('options', JSON.stringify(options));
  }

  const response = await fetch(`${API_URL}/ucc/compare`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to compare clauses' }));
    throw new Error(error.detail || 'Failed to compare clauses');
  }

  return await response.json();
};
