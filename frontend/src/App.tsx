import React, { useCallback, useEffect, useRef, useState } from 'react';
import { UploadPanel } from './components/Upload/UploadPanel';
import { SpatialCanvas } from './components/Canvas/SpatialCanvas';
import { Timeline } from './components/Timeline/Timeline';
import { StepPanel } from './components/ProcessFlow/StepPanel';
import { submitJob, pollUntilDone, getVisualSpec } from './services/api';
import type { DocumentDomain, JobStatus, VisualSpecification } from './types';

type AppState = 'idle' | 'uploading' | 'processing' | 'review' | 'done' | 'error';

export default function App() {
  const [appState, setAppState] = useState<AppState>('idle');
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [spec, setSpec] = useState<VisualSpecification | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const playRef = useRef<number | null>(null);

  // Playback loop
  useEffect(() => {
    if (playing && spec) {
      playRef.current = window.setInterval(() => {
        setCurrentTime((t) => {
          const next = t + 0.5;
          if (next >= spec.total_duration_seconds) {
            setPlaying(false);
            return spec.total_duration_seconds;
          }
          return next;
        });
      }, 500);
    } else {
      if (playRef.current) clearInterval(playRef.current);
    }
    return () => { if (playRef.current) clearInterval(playRef.current); };
  }, [playing, spec]);

  const handleUpload = useCallback(async (file: File, domain: DocumentDomain) => {
    setAppState('uploading');
    setError(null);
    try {
      const job = await submitJob(file, domain);
      setJobStatus(job);
      setAppState('processing');

      const finalStatus = await pollUntilDone(job.job_id, (s) => {
        setJobStatus(s);
      });

      if (finalStatus.human_review_required) {
        setAppState('review');
        return;
      }

      if (finalStatus.status === 'failed') {
        throw new Error(finalStatus.errors.join('; ') || 'Pipeline failed');
      }

      const visualSpec = await getVisualSpec(finalStatus.job_id);
      setSpec(visualSpec);
      setCurrentTime(0);
      setAppState('done');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error');
      setAppState('error');
    }
  }, []);

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-3">
        <span className="text-2xl">🗺️</span>
        <span className="font-bold text-gray-900 text-lg">ProcViz</span>
        <span className="text-gray-400 text-sm">Document → Visual Plan</span>
        {jobStatus && (
          <span className="ml-auto text-xs text-gray-400 font-mono">{jobStatus.job_id.slice(0, 8)}</span>
        )}
      </header>

      {/* Main */}
      {appState === 'idle' || appState === 'uploading' || appState === 'error' ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="w-full max-w-xl">
            <UploadPanel onSubmit={handleUpload} loading={appState === 'uploading'} />
            {error && (
              <div className="mt-4 mx-8 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
                ❌ {error}
              </div>
            )}
          </div>
        </div>
      ) : appState === 'processing' ? (
        <div className="flex-1 flex items-center justify-center flex-col gap-4">
          <div className="animate-spin text-4xl">⚙️</div>
          <p className="text-gray-600 font-medium">Processing document…</p>
          {jobStatus?.current_step && (
            <p className="text-gray-400 text-sm capitalize">
              {jobStatus.current_step.replace('_', ' ')}
            </p>
          )}
        </div>
      ) : appState === 'review' ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="bg-white rounded-2xl border border-amber-200 p-8 max-w-md">
            <h2 className="text-lg font-bold text-amber-800 mb-2">⚠️ Human Review Required</h2>
            <p className="text-gray-600 text-sm mb-4">
              The pipeline flagged this document for human review due to low confidence or
              critical validation issues.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => { /* TODO: submit review via API */ }}
                className="flex-1 py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700"
              >
                Approve & Continue
              </button>
              <button
                onClick={() => setAppState('idle')}
                className="flex-1 py-2 bg-gray-100 text-gray-700 rounded-lg font-medium hover:bg-gray-200"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : spec ? (
        /* Done — main viewer */
        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar */}
          <div className="w-72 flex-shrink-0 border-r border-gray-200 bg-white overflow-hidden flex flex-col">
            <StepPanel
              spec={spec}
              currentTime={currentTime}
              onSeekToStep={(t) => { setCurrentTime(t); setPlaying(false); }}
            />
          </div>

          {/* Canvas + Timeline */}
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex-1 flex items-center justify-center p-4 overflow-hidden">
              <SpatialCanvas
                spec={spec}
                currentTime={currentTime}
                width={Math.min(900, window.innerWidth - 320)}
                height={Math.min(630, window.innerHeight - 200)}
              />
            </div>
            <Timeline
              spec={spec}
              currentTime={currentTime}
              onSeek={(t) => { setCurrentTime(t); setPlaying(false); }}
              playing={playing}
              onPlayPause={() => setPlaying((p) => !p)}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
