import { PolicyBlock, PolicyData } from '../types/policy';
import { UCCComparisonResult } from '../types/clauseComparison';

const API_URL = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:8000';
const WS_URL = import.meta.env.VITE_WS_URL || API_URL.replace('http', 'ws');

// =============================================================================
// Job Progress Types
// =============================================================================

export interface JobSubmitResponse {
  job_id: string;
  celery_task_id: string;
  status: string;
  message: string;
}

export interface JobStatus {
  job_id: string;
  doc_id_a: string;
  doc_id_b: string;
  file_name_a?: string;
  file_name_b?: string;
  status: 'PENDING' | 'QUEUED' | 'RUNNING' | 'RETRYING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  current_segment: number;
  current_segment_name: string;
  total_segments: number;
  progress_pct: number;
  error_message?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
}

export interface JobProgress {
  type: 'initial' | 'progress' | 'final' | 'error';
  job_id: string;
  status: string;
  segment?: number;
  segment_name?: string;
  progress_pct?: number;
  error_message?: string;
  timestamp?: string;
}

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

// =============================================================================
// Async Job API (Celery + Redis)
// =============================================================================

/**
 * Submit a comparison job for async processing.
 * Returns immediately with a job_id for tracking progress.
 */
export const submitComparisonJob = async (
  fileA: File,
  fileB: File,
  options?: Record<string, any>
): Promise<JobSubmitResponse> => {
  const formData = new FormData();
  formData.append('file_a', fileA);
  formData.append('file_b', fileB);

  if (options) {
    formData.append('options', JSON.stringify(options));
  }

  const response = await fetch(`${API_URL}/jobs/compare`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to submit job' }));
    throw new Error(error.detail || 'Failed to submit comparison job');
  }

  return await response.json();
};

/**
 * Get the current status of a comparison job.
 */
export const getJobStatus = async (jobId: string): Promise<JobStatus> => {
  const response = await fetch(`${API_URL}/jobs/${jobId}`);

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`Job not found: ${jobId}`);
    }
    const error = await response.json().catch(() => ({ detail: 'Failed to get job status' }));
    throw new Error(error.detail || 'Failed to get job status');
  }

  return await response.json();
};

/**
 * Get the result of a completed comparison job.
 * Throws if job is not yet complete.
 */
export const getJobResult = async (jobId: string): Promise<UCCComparisonResult> => {
  const response = await fetch(`${API_URL}/jobs/${jobId}/result`);

  if (response.status === 202) {
    const status = await response.json();
    throw new Error(`Job still processing: ${status.progress_pct}% complete`);
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to get job result' }));
    throw new Error(error.detail?.message || error.detail || 'Failed to get job result');
  }

  return await response.json();
};

/**
 * Cancel a running comparison job.
 */
export const cancelJob = async (jobId: string): Promise<{ cancelled: boolean; message: string }> => {
  const response = await fetch(`${API_URL}/jobs/${jobId}/cancel`, {
    method: 'POST',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to cancel job' }));
    throw new Error(error.detail || 'Failed to cancel job');
  }

  return await response.json();
};

/**
 * Subscribe to real-time job progress updates via WebSocket.
 * 
 * @param jobId - The job ID to subscribe to
 * @param onProgress - Callback for progress updates
 * @param onError - Optional callback for errors
 * @param onClose - Optional callback when connection closes
 * @returns WebSocket instance (can call .close() to unsubscribe)
 */
export const subscribeToJobProgress = (
  jobId: string,
  onProgress: (progress: JobProgress) => void,
  onError?: (error: Event) => void,
  onClose?: (event: CloseEvent) => void
): WebSocket => {
  const ws = new WebSocket(`${WS_URL}/ws/jobs/${jobId}`);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as JobProgress;
      onProgress(data);
    } catch (e) {
      console.error('Failed to parse WebSocket message:', e);
    }
  };

  ws.onerror = (event) => {
    console.error('WebSocket error:', event);
    onError?.(event);
  };

  ws.onclose = (event) => {
    onClose?.(event);
  };

  return ws;
};

/**
 * List all jobs with optional filtering.
 */
export const listJobs = async (params?: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<{ jobs: JobStatus[]; total: number }> => {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.append('status', params.status);
  if (params?.limit) searchParams.append('limit', String(params.limit));
  if (params?.offset) searchParams.append('offset', String(params.offset));

  const url = `${API_URL}/jobs${searchParams.toString() ? `?${searchParams}` : ''}`;
  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to list jobs' }));
    throw new Error(error.detail || 'Failed to list jobs');
  }

  return await response.json();
};
