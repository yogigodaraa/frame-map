/**
 * StepPanel — sidebar showing step list, validation issues, and narration.
 */
import React from 'react';
import type { VisualSpecification } from '../../types';

interface Props {
  spec: VisualSpecification;
  currentTime: number;
  onSeekToStep: (startSeconds: number) => void;
}

const SEVERITY_STYLE: Record<string, string> = {
  critical: 'bg-red-50 border-red-300 text-red-800',
  warning: 'bg-amber-50 border-amber-300 text-amber-800',
  info: 'bg-blue-50 border-blue-300 text-blue-700',
};

const SEVERITY_ICON: Record<string, string> = {
  critical: '🚨',
  warning: '⚠️',
  info: 'ℹ️',
};

export const StepPanel: React.FC<Props> = ({ spec, currentTime, onSeekToStep }) => {
  const activeSeq = spec.sequences.find(
    (seq) => currentTime >= seq.start_seconds && currentTime <= seq.end_seconds
  );

  return (
    <div className="flex flex-col gap-4 h-full overflow-y-auto p-4 bg-gray-50">
      {/* Metadata */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h2 className="font-bold text-gray-900 text-sm truncate" title={spec.title}>
          {spec.title}
        </h2>
        <div className="flex gap-2 mt-2 flex-wrap">
          <Badge label={spec.domain} color="blue" />
          <Badge label={`${spec.sequences.length} steps`} color="gray" />
          <Badge
            label={spec.confidence_level}
            color={spec.confidence_level === 'high' ? 'green' : spec.confidence_level === 'medium' ? 'amber' : 'red'}
          />
        </div>
      </div>

      {/* Current narration */}
      {activeSeq?.narration && (
        <div className="bg-blue-600 rounded-xl p-4 text-white">
          <p className="text-xs font-semibold uppercase tracking-wider mb-1 opacity-70">Now</p>
          <p className="text-sm font-medium">{activeSeq.narration}</p>
        </div>
      )}

      {/* Step list */}
      <div className="flex flex-col gap-1">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider px-1">Steps</p>
        {spec.sequences.map((seq, i) => {
          const isActive = currentTime >= seq.start_seconds && currentTime <= seq.end_seconds;
          const isPast = currentTime > seq.end_seconds;
          return (
            <button
              key={seq.sequence_id}
              onClick={() => onSeekToStep(seq.start_seconds)}
              className={`flex items-start gap-3 p-3 rounded-lg text-left transition-colors w-full
                ${isActive ? 'bg-blue-50 border border-blue-200' : 'hover:bg-gray-100'}`}
            >
              <span
                className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold
                  ${isActive ? 'bg-blue-600 text-white' : isPast ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-500'}`}
              >
                {isPast ? '✓' : i + 1}
              </span>
              <div className="min-w-0">
                <p className={`text-sm font-medium truncate ${isActive ? 'text-blue-900' : 'text-gray-700'}`}>
                  {seq.step_title}
                </p>
                <p className="text-xs text-gray-400">
                  {formatDuration(seq.end_seconds - seq.start_seconds)}
                </p>
              </div>
            </button>
          );
        })}
      </div>

      {/* Validation issues */}
      {spec.validation_issues.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider px-1">
            Validation ({spec.validation_issues.length})
          </p>
          {spec.validation_issues.map((issue) => (
            <div
              key={issue.issue_id}
              className={`rounded-lg border p-3 text-xs ${SEVERITY_STYLE[issue.severity] ?? 'bg-gray-50 border-gray-200'}`}
            >
              <p className="font-semibold mb-0.5">
                {SEVERITY_ICON[issue.severity]} {issue.description}
              </p>
              {issue.recommendation && (
                <p className="opacity-75 mt-1">{issue.recommendation}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const Badge: React.FC<{ label: string; color: string }> = ({ label, color }) => {
  const colorMap: Record<string, string> = {
    blue: 'bg-blue-100 text-blue-700',
    gray: 'bg-gray-100 text-gray-600',
    green: 'bg-green-100 text-green-700',
    amber: 'bg-amber-100 text-amber-700',
    red: 'bg-red-100 text-red-700',
  };
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${colorMap[color] ?? colorMap.gray}`}>
      {label}
    </span>
  );
};

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
}
