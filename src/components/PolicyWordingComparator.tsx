import { useState, useMemo, useCallback } from 'react';
import { Play, Download, RefreshCw, AlertCircle, Zap, Clock } from 'lucide-react';
import ClauseComparerUpload from './ClauseComparerUpload';
import SummaryBanner from './clause/SummaryBanner';
import FilterToolbar from './clause/FilterToolbar';
import ClauseMatchResults from './clause/ClauseMatchResults';
import WarningsTimingsPanel from './clause/WarningsTimingsPanel';
import JobProgressPanel from './clause/JobProgressPanel';
import { UCCComparisonResult, FilterState, ClauseStatus } from '../types/clauseComparison';
import { 
  submitComparisonJob, 
  getJobResult,
  compareClausesViaPython,
  JobSubmitResponse,
} from '../utils/pythonApiClient';
import { filterClauseMatches, countActiveFilters } from '../utils/clauseFilters';

type ProcessingMode = 'sync' | 'async';

export default function PolicyWordingComparator() {
  const [fileA, setFileA] = useState<File | null>(null);
  const [fileB, setFileB] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [result, setResult] = useState<UCCComparisonResult | null>(null);
  
  // Async job state
  const [jobId, setJobId] = useState<string | null>(null);
  const [processingMode, setProcessingMode] = useState<ProcessingMode>('async');

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

  // Async job completion handler
  const handleJobComplete = useCallback(async () => {
    if (!jobId) return;
    
    try {
      const comparisonResult = await getJobResult(jobId);
      setResult(comparisonResult);
      setJobId(null);
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retrieve comparison results');
      setJobId(null);
      setLoading(false);
    }
  }, [jobId]);

  const handleJobError = useCallback((errorMessage: string) => {
    setError(errorMessage);
    setJobId(null);
    setLoading(false);
  }, []);

  const handleJobCancel = useCallback(() => {
    setJobId(null);
    setLoading(false);
    setError('Comparison cancelled');
  }, []);

  const handleRunComparison = async () => {
    if (!fileA || !fileB) {
      setError('Please upload both policy documents');
      return;
    }

    setLoading(true);
    setError('');

    if (processingMode === 'async') {
      // Async mode - submit job and track progress
      try {
        const response: JobSubmitResponse = await submitComparisonJob(fileA, fileB);
        setJobId(response.job_id);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to submit comparison job');
        setLoading(false);
      }
    } else {
      // Sync mode - wait for full result (fallback)
      try {
        const comparisonResult = await compareClausesViaPython(fileA, fileB);
        setResult(comparisonResult);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to compare policy clauses');
        console.error('Comparison error:', err);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleReset = () => {
    setFileA(null);
    setFileB(null);
    setResult(null);
    setJobId(null);
    setError('');
    setLoading(false);
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

  // Show progress panel when job is running
  if (jobId && loading) {
    return (
      <div className="space-y-6">
        <JobProgressPanel
          jobId={jobId}
          fileNameA={fileA?.name}
          fileNameB={fileB?.name}
          onComplete={handleJobComplete}
          onError={handleJobError}
          onCancel={handleJobCancel}
        />
      </div>
    );
  }

  // Show results when comparison is complete
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

  // Show upload interface
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
        <div className="space-y-4">
          {/* Processing Mode Toggle */}
          <div className="flex justify-center">
            <div className="bg-slate-100 rounded-lg p-1 inline-flex gap-1">
              <button
                onClick={() => setProcessingMode('async')}
                className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
                  processingMode === 'async'
                    ? 'bg-white text-slate-800 shadow-sm'
                    : 'text-slate-600 hover:text-slate-800'
                }`}
              >
                <Zap className="w-4 h-4" />
                With Progress Tracking
              </button>
              <button
                onClick={() => setProcessingMode('sync')}
                className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
                  processingMode === 'sync'
                    ? 'bg-white text-slate-800 shadow-sm'
                    : 'text-slate-600 hover:text-slate-800'
                }`}
              >
                <Clock className="w-4 h-4" />
                Simple Mode
              </button>
            </div>
          </div>

          {/* Run Button */}
          <div className="flex justify-center">
            <button
              onClick={handleRunComparison}
              disabled={loading}
              className="flex items-center gap-3 px-8 py-4 bg-blue-600 text-white text-lg font-semibold rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-lg hover:shadow-xl"
            >
              {loading ? (
                <>
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-white"></div>
                  {processingMode === 'async' ? 'Submitting Job...' : 'Analyzing Clauses...'}
                </>
              ) : (
                <>
                  <Play className="w-6 h-6" />
                  Run Universal Clause Comparer
                </>
              )}
            </button>
          </div>

          {processingMode === 'async' && (
            <p className="text-center text-sm text-slate-500">
              Progress tracking mode provides real-time updates as each analysis step completes
            </p>
          )}
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
                Watch real-time progress as each analysis step completes
              </span>
            </li>
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-sm font-semibold">
                5
              </span>
              <span>
                Review added, removed, and modified clauses with materiality scores
              </span>
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
