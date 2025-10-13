import { ClauseMatch, FilterState } from '../types/clauseComparison';

export const filterClauseMatches = (
  matches: ClauseMatch[],
  filters: FilterState
): ClauseMatch[] => {
  return matches.filter((match) => {
    if (!filters.statuses.has(match.status)) {
      return false;
    }

    if (filters.clauseType !== 'All Types') {
      if (!match.clause_type || match.clause_type !== filters.clauseType) {
        return false;
      }
    }

    if (filters.materialityRange !== 'all') {
      const score = match.materiality_score;
      if (filters.materialityRange === 'high' && (score < 0.7 || score > 1.0)) {
        return false;
      }
      if (filters.materialityRange === 'medium' && (score < 0.4 || score >= 0.7)) {
        return false;
      }
      if (filters.materialityRange === 'low' && (score < 0 || score >= 0.4)) {
        return false;
      }
    }

    if (filters.reviewRequired !== null) {
      if (match.review_required !== filters.reviewRequired) {
        return false;
      }
    }

    return true;
  });
};

export const countActiveFilters = (filters: FilterState): number => {
  let count = 0;

  const allStatuses = new Set(['added', 'removed', 'modified', 'unchanged']);
  if (filters.statuses.size !== allStatuses.size) {
    count++;
  }

  if (filters.clauseType !== 'All Types') {
    count++;
  }

  if (filters.materialityRange !== 'all') {
    count++;
  }

  if (filters.reviewRequired !== null) {
    count++;
  }

  return count;
};

export const getFilterSummary = (filters: FilterState): string => {
  const parts: string[] = [];

  if (filters.statuses.size < 4) {
    const statusNames = Array.from(filters.statuses).join(', ');
    parts.push(`Status: ${statusNames}`);
  }

  if (filters.clauseType !== 'All Types') {
    parts.push(`Type: ${filters.clauseType}`);
  }

  if (filters.materialityRange !== 'all') {
    parts.push(`Materiality: ${filters.materialityRange}`);
  }

  if (filters.reviewRequired !== null) {
    parts.push(filters.reviewRequired ? 'Review Required' : 'No Review Required');
  }

  return parts.length > 0 ? parts.join(' • ') : 'No filters applied';
};
