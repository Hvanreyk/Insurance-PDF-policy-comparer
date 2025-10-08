import { PolicyData, ComparisonResult, ComparisonDelta } from '../types/policy';

export const comparePolicies = (
  policyA: PolicyData,
  policyB: PolicyData
): ComparisonResult => {
  const result: ComparisonResult = {};

  if (policyA.sums_insured.contents !== undefined || policyB.sums_insured.contents !== undefined) {
    result['Contents'] = calculateDelta(
      policyA.sums_insured.contents,
      policyB.sums_insured.contents
    );
  }

  if (policyA.sums_insured.theft_total !== undefined || policyB.sums_insured.theft_total !== undefined) {
    result['Theft (Contents & Stock)'] = calculateDelta(
      policyA.sums_insured.theft_total,
      policyB.sums_insured.theft_total
    );
  }

  if (policyA.sums_insured.bi_turnover !== undefined || policyB.sums_insured.bi_turnover !== undefined) {
    result['Business Interruption (Turnover)'] = calculateDelta(
      policyA.sums_insured.bi_turnover,
      policyB.sums_insured.bi_turnover
    );
  }

  if (policyA.sums_insured.public_liability !== undefined || policyB.sums_insured.public_liability !== undefined) {
    result['Public Liability'] = calculateDelta(
      policyA.sums_insured.public_liability,
      policyB.sums_insured.public_liability
    );
  }

  if (policyA.sums_insured.property_in_your_control !== undefined || policyB.sums_insured.property_in_your_control !== undefined) {
    result['Property in Control'] = calculateDelta(
      policyA.sums_insured.property_in_your_control,
      policyB.sums_insured.property_in_your_control
    );
  }

  if (policyA.premium.base !== undefined || policyB.premium.base !== undefined) {
    result['Premium (Base)'] = calculateDelta(
      policyA.premium.base,
      policyB.premium.base
    );
  }

  if (policyA.premium.fsl !== undefined || policyB.premium.fsl !== undefined) {
    result['Premium (FSL/ESL)'] = calculateDelta(
      policyA.premium.fsl,
      policyB.premium.fsl
    );
  }

  if (policyA.premium.gst !== undefined || policyB.premium.gst !== undefined) {
    result['Premium (GST)'] = calculateDelta(
      policyA.premium.gst,
      policyB.premium.gst
    );
  }

  if (policyA.premium.stamp !== undefined || policyB.premium.stamp !== undefined) {
    result['Premium (Stamp Duty)'] = calculateDelta(
      policyA.premium.stamp,
      policyB.premium.stamp
    );
  }

  if (policyA.premium.total !== undefined || policyB.premium.total !== undefined) {
    result['Total Premium'] = calculateDelta(
      policyA.premium.total,
      policyB.premium.total
    );
  }

  return result;
};

const calculateDelta = (
  a: number | undefined,
  b: number | undefined
): ComparisonDelta => {
  const valA = a ?? null;
  const valB = b ?? null;

  if (valA === null || valB === null) {
    return {
      a: valA,
      b: valB,
      delta_abs: null,
      delta_pct: null,
    };
  }

  const deltaAbs = valB - valA;
  const deltaPct = valA !== 0 ? ((valB - valA) / valA) * 100 : null;

  return {
    a: valA,
    b: valB,
    delta_abs: deltaAbs,
    delta_pct: deltaPct,
  };
};

export const formatCurrency = (value: number | null): string => {
  if (value === null) return 'N/A';
  return new Intl.NumberFormat('en-AU', {
    style: 'currency',
    currency: 'AUD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value);
};

export const formatPercent = (value: number | null): string => {
  if (value === null) return 'N/A';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
};
