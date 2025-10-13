import { PolicyData } from '../types/policy';
import { UCCComparisonResult } from '../types/clauseComparison';

const API_URL = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:8000';

export const parsePolicyPDFViaPython = async (file: File): Promise<PolicyData> => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_URL}/api/parse-policy`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to parse PDF');
  }

  return await response.json();
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

  const response = await fetch(`${API_URL}/api/compare-clauses`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to compare clauses' }));
    throw new Error(error.detail || 'Failed to compare clauses');
  }

  return await response.json();
};
