import type { JobStatus, VisualSpecification } from '../types';

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export async function submitJob(
  file: File,
  domain: string
): Promise<JobStatus> {
  const form = new FormData();
  form.append('file', file);
  form.append('domain', domain);

  const res = await fetch(`${BASE_URL}/api/jobs`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function pollJobStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${BASE_URL}/api/jobs/${jobId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getVisualSpec(jobId: string): Promise<VisualSpecification> {
  const res = await fetch(`${BASE_URL}/api/jobs/${jobId}/spec`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitReview(
  jobId: string,
  approved: boolean,
  notes?: string
): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/jobs/${jobId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved, notes }),
  });
  if (!res.ok) throw new Error(await res.text());
}

/** Poll until complete or failed. Calls onProgress on each tick. */
export async function pollUntilDone(
  jobId: string,
  onProgress: (status: JobStatus) => void,
  intervalMs = 2000,
  timeoutMs = 300_000
): Promise<JobStatus> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const status = await pollJobStatus(jobId);
    onProgress(status);
    if (['completed', 'completed_with_errors', 'failed'].includes(status.status)) {
      return status;
    }
    if (status.human_review_required) {
      return status; // caller handles review
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error('Job timed out');
}
