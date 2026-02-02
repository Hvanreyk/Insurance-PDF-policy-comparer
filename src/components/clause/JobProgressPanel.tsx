import { useState, useEffect, useCallback } from 'react';
import { CheckCircle2, Circle, Loader2, XCircle, Clock, AlertTriangle } from 'lucide-react';
import { JobProgress, JobStatus, subscribeToJobProgress, getJobStatus, cancelJob } from '../../utils/pythonApiClient';

// Segment definitions matching the backend
const SEGMENTS = [
  { id: 0, name: 'Queued', group: 'start' },
  { id: 1, name: 'Document A: Layout Analysis', group: 'docA' },
  { id: 2, name: 'Document A: Definitions', group: 'docA' },
  { id: 3, name: 'Document A: Classification', group: 'docA' },
  { id: 4, name: 'Document A: Clause DNA', group: 'docA' },
  { id: 5, name: 'Document B: Layout Analysis', group: 'docB' },
  { id: 6, name: 'Document B: Definitions', group: 'docB' },
  { id: 7, name: 'Document B: Classification', group: 'docB' },
  { id: 8, name: 'Document B: Clause DNA', group: 'docB' },
  { id: 9, name: 'Semantic Alignment', group: 'compare' },
  { id: 10, name: 'Delta Interpretation', group: 'compare' },
  { id: 11, name: 'Narrative Summary', group: 'compare' },
];

interface JobProgressPanelProps {
  jobId: string;
  fileNameA?: string;
  fileNameB?: string;
  onComplete: () => void;
  onError: (error: string) => void;
  onCancel: () => void;
}

export default function JobProgressPanel({
  jobId,
  fileNameA,
  fileNameB,
  onComplete,
  onError,
  onCancel,
}: JobProgressPanelProps) {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [progress, setProgress] = useState<JobProgress | null>(null);
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [cancelling, setCancelling] = useState(false);

  // Subscribe to WebSocket updates
  useEffect(() => {
    const websocket = subscribeToJobProgress(
      jobId,
      (progressUpdate) => {
        setProgress(progressUpdate);
        
        // Update status from progress
        setStatus((prev) => prev ? {
          ...prev,
          status: progressUpdate.status as JobStatus['status'],
          current_segment: progressUpdate.segment ?? prev.current_segment,
          current_segment_name: progressUpdate.segment_name ?? prev.current_segment_name,
          progress_pct: progressUpdate.progress_pct ?? prev.progress_pct,
          error_message: progressUpdate.error_message ?? prev.error_message,
        } : null);

        // Handle completion
        if (progressUpdate.status === 'COMPLETED') {
          onComplete();
        } else if (progressUpdate.status === 'FAILED') {
          onError(progressUpdate.error_message || 'Job failed');
        } else if (progressUpdate.status === 'CANCELLED') {
          onCancel();
        }
      },
      (error) => {
        console.error('WebSocket error:', error);
        // Fall back to polling
        pollStatus();
      },
      () => {
        // Connection closed - check final status
        pollStatus();
      }
    );

    setWs(websocket);

    return () => {
      websocket.close();
    };
  }, [jobId, onComplete, onError, onCancel]);

  // Initial status fetch
  useEffect(() => {
    pollStatus();
  }, [jobId]);

  const pollStatus = useCallback(async () => {
    try {
      const jobStatus = await getJobStatus(jobId);
      setStatus(jobStatus);
      
      if (jobStatus.status === 'COMPLETED') {
        onComplete();
      } else if (jobStatus.status === 'FAILED') {
        onError(jobStatus.error_message || 'Job failed');
      } else if (jobStatus.status === 'CANCELLED') {
        onCancel();
      }
    } catch (e) {
      console.error('Failed to fetch job status:', e);
    }
  }, [jobId, onComplete, onError, onCancel]);

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await cancelJob(jobId);
      onCancel();
    } catch (e) {
      console.error('Failed to cancel job:', e);
    } finally {
      setCancelling(false);
    }
  };

  const currentSegment = status?.current_segment ?? progress?.segment ?? 0;
  const progressPct = status?.progress_pct ?? progress?.progress_pct ?? 0;
  const currentStatus = status?.status ?? progress?.status ?? 'PENDING';

  const getSegmentStatus = (segmentId: number) => {
    if (currentStatus === 'FAILED' && segmentId === currentSegment) {
      return 'failed';
    }
    if (segmentId < currentSegment) {
      return 'complete';
    }
    if (segmentId === currentSegment) {
      return currentStatus === 'RUNNING' || currentStatus === 'RETRYING' ? 'running' : 'pending';
    }
    return 'pending';
  };

  const getSegmentIcon = (segmentStatus: string) => {
    switch (segmentStatus) {
      case 'complete':
        return <CheckCircle2 className="w-5 h-5 text-emerald-500" />;
      case 'running':
        return <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />;
      case 'failed':
        return <XCircle className="w-5 h-5 text-red-500" />;
      default:
        return <Circle className="w-5 h-5 text-slate-300" />;
    }
  };

  const formatDuration = () => {
    if (!status?.started_at) return null;
    const start = new Date(status.started_at);
    const now = status.completed_at ? new Date(status.completed_at) : new Date();
    const seconds = Math.floor((now.getTime() - start.getTime()) / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-slate-800">
            Processing Policy Comparison
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            {fileNameA && fileNameB ? (
              <>Comparing {fileNameA} vs {fileNameB}</>
            ) : (
              <>Job ID: {jobId}</>
            )}
          </p>
        </div>
        {currentStatus !== 'COMPLETED' && currentStatus !== 'FAILED' && currentStatus !== 'CANCELLED' && (
          <button
            onClick={handleCancel}
            disabled={cancelling}
            className="px-4 py-2 text-sm font-medium text-red-600 hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
          >
            {cancelling ? 'Cancelling...' : 'Cancel'}
          </button>
        )}
      </div>

      {/* Progress Bar */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-slate-700">
            {status?.current_segment_name || SEGMENTS[currentSegment]?.name || 'Starting...'}
          </span>
          <span className="text-sm font-medium text-slate-700">
            {Math.round(progressPct)}%
          </span>
        </div>
        <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ease-out ${
              currentStatus === 'FAILED' ? 'bg-red-500' :
              currentStatus === 'COMPLETED' ? 'bg-emerald-500' :
              'bg-blue-500'
            }`}
            style={{ width: `${progressPct}%` }}
          />
        </div>
        {formatDuration() && (
          <div className="flex items-center gap-1 mt-2 text-xs text-slate-500">
            <Clock className="w-3 h-3" />
            <span>Elapsed: {formatDuration()}</span>
          </div>
        )}
      </div>

      {/* Segment Groups */}
      <div className="space-y-6">
        {/* Document A */}
        <div>
          <h3 className="text-sm font-semibold text-slate-600 mb-3 flex items-center gap-2">
            <span className="w-6 h-6 rounded bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold">A</span>
            {fileNameA || 'Document A'}
          </h3>
          <div className="grid grid-cols-2 gap-2">
            {SEGMENTS.filter(s => s.group === 'docA').map((segment) => {
              const segStatus = getSegmentStatus(segment.id);
              return (
                <div
                  key={segment.id}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${
                    segStatus === 'complete' ? 'bg-emerald-50 text-emerald-700' :
                    segStatus === 'running' ? 'bg-blue-50 text-blue-700' :
                    segStatus === 'failed' ? 'bg-red-50 text-red-700' :
                    'bg-slate-50 text-slate-500'
                  }`}
                >
                  {getSegmentIcon(segStatus)}
                  <span className="truncate">{segment.name.replace('Document A: ', '')}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Document B */}
        <div>
          <h3 className="text-sm font-semibold text-slate-600 mb-3 flex items-center gap-2">
            <span className="w-6 h-6 rounded bg-purple-100 text-purple-700 flex items-center justify-center text-xs font-bold">B</span>
            {fileNameB || 'Document B'}
          </h3>
          <div className="grid grid-cols-2 gap-2">
            {SEGMENTS.filter(s => s.group === 'docB').map((segment) => {
              const segStatus = getSegmentStatus(segment.id);
              return (
                <div
                  key={segment.id}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${
                    segStatus === 'complete' ? 'bg-emerald-50 text-emerald-700' :
                    segStatus === 'running' ? 'bg-blue-50 text-blue-700' :
                    segStatus === 'failed' ? 'bg-red-50 text-red-700' :
                    'bg-slate-50 text-slate-500'
                  }`}
                >
                  {getSegmentIcon(segStatus)}
                  <span className="truncate">{segment.name.replace('Document B: ', '')}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Comparison */}
        <div>
          <h3 className="text-sm font-semibold text-slate-600 mb-3 flex items-center gap-2">
            <span className="w-6 h-6 rounded bg-amber-100 text-amber-700 flex items-center justify-center text-xs font-bold">⚡</span>
            Comparison Analysis
          </h3>
          <div className="grid grid-cols-3 gap-2">
            {SEGMENTS.filter(s => s.group === 'compare').map((segment) => {
              const segStatus = getSegmentStatus(segment.id);
              return (
                <div
                  key={segment.id}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${
                    segStatus === 'complete' ? 'bg-emerald-50 text-emerald-700' :
                    segStatus === 'running' ? 'bg-blue-50 text-blue-700' :
                    segStatus === 'failed' ? 'bg-red-50 text-red-700' :
                    'bg-slate-50 text-slate-500'
                  }`}
                >
                  {getSegmentIcon(segStatus)}
                  <span className="truncate">{segment.name}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Error Message */}
      {currentStatus === 'FAILED' && status?.error_message && (
        <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-red-900">Processing Failed</h4>
              <p className="text-sm text-red-700 mt-1">{status.error_message}</p>
            </div>
          </div>
        </div>
      )}

      {/* Retrying Message */}
      {currentStatus === 'RETRYING' && (
        <div className="mt-6 p-4 bg-amber-50 border border-amber-200 rounded-lg">
          <div className="flex items-start gap-3">
            <Loader2 className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5 animate-spin" />
            <div>
              <h4 className="font-semibold text-amber-900">Retrying...</h4>
              <p className="text-sm text-amber-700 mt-1">
                Encountered a temporary issue. Automatically retrying...
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
