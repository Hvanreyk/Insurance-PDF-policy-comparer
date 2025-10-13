import { useState, useMemo } from 'react';
import { Play, Download, RefreshCw, AlertCircle } from 'lucide-react';
import ClauseComparerUpload from './ClauseComparerUpload';
import SummaryBanner from './clause/SummaryBanner';
import FilterToolbar from './clause/FilterToolbar';
import ClauseMatchResults from './clause/ClauseMatchResults';
import WarningsTimingsPanel from './clause/WarningsTimingsPanel';
import { UCCComparisonResult, FilterState, ClauseStatus } from '../types/clauseComparison';
import { compareClausesViaPython } from '../utils/pythonApiClient';
import { filterClauseMatches, countActiveFilters } from '../utils/clauseFilters';

export default function PolicyWordingComparator() {
  const [fileA, setFileA] = useState<File | null>(null);
  const [fileB, setFileB] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [result, setResult] = useState<UCCComparisonResult | null>(null);

  const [filters, setFilters] = useState<FilterState>({
    statuses: new Set<ClauseStatus>(['added', 'removed', 'modified', 'unchanged']),
    clauseType: 'All Types',
    materialityRange: 'all',
    reviewRequired: null,
  });

  const filteredMatches = useMemo(() => {
    if (!result) return [];
    return filterClauseMatches(result.matches, filters);
  }, [result, filters]);

  const activeFilterCount = useMemo(() => {
    return countActiveFilters(filters);
  }, [filters]);

  const handleRunComparison = async () => {
    if (!fileA || !fileB) {
      setError('Please upload both policy documents');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const comparisonResult = await compareClausesViaPython(fileA, fileB);
      setResult(comparisonResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to compare policy clauses');
      console.error('Comparison error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setFileA(null);
    setFileB(null);
    setResult(null);
    setError('');
    setFilters({
      statuses: new Set<ClauseStatus>(['added', 'removed', 'modified', 'unchanged']),
      clauseType: 'All Types',
      materialityRange: 'all',
      reviewRequired: null,
    });
  };

  const handleDownloadJSON = () => {
    if (!result) return;

    const jsonData = {
      ...result,
      metadata: {
        comparison_date: new Date().toISOString(),
        file_a_name: fileA?.name,
        file_b_name: fileB?.name,
      },
    };

    const blob = new Blob([JSON.stringify(jsonData, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    a.download = `clause-comparison-${timestamp}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (result) {
    return (
      <div className="space-y-6">
        <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold text-slate-800 mb-2">
                Clause Comparison Results
              </h2>
              <p className="text-slate-600">
                Comparing <span className="font-medium">{fileA?.name}</span> vs{' '}
                <span className="font-medium">{fileB?.name}</span>
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={handleDownloadJSON}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                <Download className="w-4 h-4" />
                Download JSON
              </button>
              <button
                onClick={handleReset}
                className="flex items-center gap-2 px-4 py-2 bg-slate-600 text-white rounded-lg hover:bg-slate-700 transition-colors"
              >
                <RefreshCw className="w-4 h-4" />
                New Comparison
              </button>
            </div>
          </div>
        </div>

        <SummaryBanner summary={result.summary} />

        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <FilterToolbar
              filters={filters}
              onFiltersChange={setFilters}
              activeFilterCount={activeFilterCount}
            />

            <div className="bg-slate-50 rounded-lg p-4">
              <p className="text-sm text-slate-700">
                Showing <span className="font-semibold">{filteredMatches.length}</span> of{' '}
                <span className="font-semibold">{result.matches.length}</span> clause matches
              </p>
            </div>

            <ClauseMatchResults matches={filteredMatches} />
          </div>

          <div className="lg:col-span-1">
            <WarningsTimingsPanel warnings={result.warnings} timings={result.timings_ms} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
        <h2 className="text-2xl font-bold text-slate-800 mb-2">
          Upload Policy Documents
        </h2>
        <p className="text-slate-600">
          Upload two policy documents to compare their clause-level wording and identify
          changes
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-red-900 mb-1">Error</h3>
            <p className="text-red-700">{error}</p>
          </div>
        </div>
      )}

      <ClauseComparerUpload
        fileA={fileA}
        fileB={fileB}
        onFileASelect={setFileA}
        onFileBSelect={setFileB}
        onClear={() => {
          setFileA(null);
          setFileB(null);
          setError('');
        }}
      />

      {fileA && fileB && (
        <div className="flex justify-center">
          <button
            onClick={handleRunComparison}
            disabled={loading}
            className="flex items-center gap-3 px-8 py-4 bg-blue-600 text-white text-lg font-semibold rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-lg hover:shadow-xl"
          >
            {loading ? (
              <>
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-white"></div>
                Analyzing Clauses...
              </>
            ) : (
              <>
                <Play className="w-6 h-6" />
                Run Universal Clause Comparer
              </>
            )}
          </button>
        </div>
      )}

      {!fileA && !fileB && (
        <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6 mt-8">
          <h3 className="text-xl font-semibold text-slate-800 mb-4">
            How to Use This Tool
          </h3>
          <ol className="space-y-3 text-slate-700">
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-sm font-semibold">
                1
              </span>
              <span>Upload the expiring policy document (Policy A) in the left panel</span>
            </li>
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-sm font-semibold">
                2
              </span>
              <span>Upload the new quote document (Policy B) in the right panel</span>
            </li>
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-sm font-semibold">
                3
              </span>
              <span>Click "Run Universal Clause Comparer" to analyze clause differences</span>
            </li>
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-sm font-semibold">
                4
              </span>
              <span>
                Review added, removed, and modified clauses with materiality scores
              </span>
            </li>
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-sm font-semibold">
                5
              </span>
              <span>Use filters to focus on specific clause types or risk levels</span>
            </li>
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-sm font-semibold">
                6
              </span>
              <span>Download the full comparison report as JSON for records</span>
            </li>
          </ol>
        </div>
      )}
    </div>
  );
}
