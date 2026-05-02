/**
 * Timeline — horizontal scrubber showing steps as coloured segments.
 * Controls currentTime for SpatialCanvas.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { VisualSpecification } from '../../types';

interface Props {
  spec: VisualSpecification;
  currentTime: number;
  onSeek: (t: number) => void;
  playing: boolean;
  onPlayPause: () => void;
}

const STEP_COLORS = [
  '#3B82F6', '#8B5CF6', '#10B981', '#F59E0B',
  '#EF4444', '#06B6D4', '#84CC16', '#F97316',
];

export const Timeline: React.FC<Props> = ({
  spec,
  currentTime,
  onSeek,
  playing,
  onPlayPause,
}) => {
  const trackRef = useRef<HTMLDivElement>(null);
  const total = spec.total_duration_seconds;
  const progress = total > 0 ? (currentTime / total) * 100 : 0;

  const handleTrackClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const rect = trackRef.current?.getBoundingClientRect();
      if (!rect) return;
      const ratio = (e.clientX - rect.left) / rect.width;
      onSeek(Math.max(0, Math.min(total, ratio * total)));
    },
    [total, onSeek]
  );

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  return (
    <div className="bg-white border-t border-gray-200 px-6 py-4 flex flex-col gap-3">
      {/* Step segments */}
      <div
        ref={trackRef}
        className="relative h-8 rounded-lg overflow-hidden cursor-pointer"
        onClick={handleTrackClick}
      >
        {spec.sequences.map((seq, i) => {
          const left = (seq.start_seconds / total) * 100;
          const width = ((seq.end_seconds - seq.start_seconds) / total) * 100;
          const isActive = currentTime >= seq.start_seconds && currentTime <= seq.end_seconds;
          return (
            <div
              key={seq.sequence_id}
              className="absolute top-0 h-full flex items-center justify-center text-white text-xs font-medium truncate px-1 transition-opacity"
              style={{
                left: `${left}%`,
                width: `${width}%`,
                backgroundColor: STEP_COLORS[i % STEP_COLORS.length],
                opacity: isActive ? 1 : 0.6,
                borderRight: '1px solid rgba(255,255,255,0.3)',
              }}
              title={seq.step_title}
            >
              {width > 5 ? seq.step_title : ''}
            </div>
          );
        })}

        {/* Playhead */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-white shadow-lg pointer-events-none z-10"
          style={{ left: `${progress}%` }}
        />
      </div>

      {/* Controls */}
      <div className="flex items-center gap-4">
        <button
          onClick={onPlayPause}
          className="w-9 h-9 rounded-full bg-blue-600 text-white flex items-center justify-center hover:bg-blue-700 transition-colors"
        >
          {playing ? '⏸' : '▶'}
        </button>

        <span className="text-sm font-mono text-gray-600">
          {formatTime(currentTime)} / {formatTime(total)}
        </span>

        {/* Current step label */}
        {spec.sequences.find(
          (seq) => currentTime >= seq.start_seconds && currentTime <= seq.end_seconds
        ) && (
          <span className="text-sm text-blue-700 font-medium truncate max-w-xs">
            {spec.sequences.find(
              (seq) => currentTime >= seq.start_seconds && currentTime <= seq.end_seconds
            )?.step_title}
          </span>
        )}
      </div>
    </div>
  );
};
