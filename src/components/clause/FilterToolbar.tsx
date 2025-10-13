import { Filter, X } from 'lucide-react';
import { FilterState, ClauseStatus, ClauseType } from '../../types/clauseComparison';

interface FilterToolbarProps {
  filters: FilterState;
  onFiltersChange: (filters: FilterState) => void;
  activeFilterCount: number;
}

const CLAUSE_TYPES: ClauseType[] = [
  'All Types',
  'Coverage',
  'Exclusion',
  'Condition',
  'Definition',
  'Warranty',
  'Extension',
  'Endorsement',
  'Subjectivity',
  'Deductible',
];

export default function FilterToolbar({
  filters,
  onFiltersChange,
  activeFilterCount,
}: FilterToolbarProps) {
  const toggleStatus = (status: ClauseStatus) => {
    const newStatuses = new Set(filters.statuses);
    if (newStatuses.has(status)) {
      newStatuses.delete(status);
    } else {
      newStatuses.add(status);
    }
    onFiltersChange({ ...filters, statuses: newStatuses });
  };

  const setClauseType = (clauseType: ClauseType) => {
    onFiltersChange({ ...filters, clauseType });
  };

  const setMaterialityRange = (range: 'all' | 'high' | 'medium' | 'low') => {
    onFiltersChange({ ...filters, materialityRange: range });
  };

  const toggleReviewRequired = () => {
    onFiltersChange({
      ...filters,
      reviewRequired: filters.reviewRequired === null ? true : filters.reviewRequired ? false : null,
    });
  };

  const clearFilters = () => {
    onFiltersChange({
      statuses: new Set<ClauseStatus>(['added', 'removed', 'modified', 'unchanged']),
      clauseType: 'All Types',
      materialityRange: 'all',
      reviewRequired: null,
    });
  };

  const getStatusButtonClass = (status: ClauseStatus) => {
    const isActive = filters.statuses.has(status);
    const baseClass = 'px-4 py-2 rounded-lg text-sm font-medium transition-all';

    if (!isActive) {
      return `${baseClass} bg-slate-100 text-slate-400 hover:bg-slate-200`;
    }

    switch (status) {
      case 'added':
        return `${baseClass} bg-green-100 text-green-700 border-2 border-green-500`;
      case 'removed':
        return `${baseClass} bg-red-100 text-red-700 border-2 border-red-500`;
      case 'modified':
        return `${baseClass} bg-amber-100 text-amber-700 border-2 border-amber-500`;
      case 'unchanged':
        return `${baseClass} bg-slate-200 text-slate-700 border-2 border-slate-400`;
      default:
        return baseClass;
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Filter className="w-5 h-5 text-slate-600" />
          <h3 className="text-lg font-semibold text-slate-800">Filters</h3>
          {activeFilterCount > 0 && (
            <span className="bg-blue-600 text-white text-xs font-bold px-2 py-1 rounded-full">
              {activeFilterCount}
            </span>
          )}
        </div>
        {activeFilterCount > 0 && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-2 text-sm text-slate-600 hover:text-slate-800 font-medium"
          >
            <X className="w-4 h-4" />
            Clear Filters
          </button>
        )}
      </div>

      <div className="space-y-4">
        <div>
          <label className="text-sm font-semibold text-slate-700 mb-2 block">Status</label>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => toggleStatus('added')}
              className={getStatusButtonClass('added')}
            >
              Added
            </button>
            <button
              onClick={() => toggleStatus('removed')}
              className={getStatusButtonClass('removed')}
            >
              Removed
            </button>
            <button
              onClick={() => toggleStatus('modified')}
              className={getStatusButtonClass('modified')}
            >
              Modified
            </button>
            <button
              onClick={() => toggleStatus('unchanged')}
              className={getStatusButtonClass('unchanged')}
            >
              Unchanged
            </button>
          </div>
        </div>

        <div>
          <label className="text-sm font-semibold text-slate-700 mb-2 block">Clause Type</label>
          <select
            value={filters.clauseType}
            onChange={(e) => setClauseType(e.target.value as ClauseType)}
            className="w-full md:w-auto px-4 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {CLAUSE_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-sm font-semibold text-slate-700 mb-2 block">
            Materiality Score
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setMaterialityRange('all')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                filters.materialityRange === 'all'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              All
            </button>
            <button
              onClick={() => setMaterialityRange('high')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                filters.materialityRange === 'high'
                  ? 'bg-red-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              High (0.7-1.0)
            </button>
            <button
              onClick={() => setMaterialityRange('medium')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                filters.materialityRange === 'medium'
                  ? 'bg-amber-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              Medium (0.4-0.7)
            </button>
            <button
              onClick={() => setMaterialityRange('low')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                filters.materialityRange === 'low'
                  ? 'bg-green-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              Low (0-0.4)
            </button>
          </div>
        </div>

        <div>
          <label className="text-sm font-semibold text-slate-700 mb-2 block">
            Review Status
          </label>
          <button
            onClick={toggleReviewRequired}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              filters.reviewRequired === true
                ? 'bg-orange-600 text-white'
                : filters.reviewRequired === false
                ? 'bg-blue-600 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {filters.reviewRequired === null
              ? 'All Clauses'
              : filters.reviewRequired
              ? 'Review Required Only'
              : 'No Review Required'}
          </button>
        </div>
      </div>
    </div>
  );
}
