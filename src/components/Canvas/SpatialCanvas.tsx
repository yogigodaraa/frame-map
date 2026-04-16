/**
 * SpatialCanvas — React-Konva canvas that renders the spatial view.
 *
 * Draws:
 * - Zones (polygons with labels)
 * - Actors (icons at interpolated positions)
 * - Movement paths (dotted lines)
 * - Annotations
 *
 * Driven by currentTime (seconds) from the Timeline component.
 */
import React, { useMemo } from 'react';
import { Stage, Layer, Line, Circle, Text, Group, Rect } from 'react-konva';
import type { VisualSpecification, Coordinate, AnimationSequence } from '../../types';

interface Props {
  spec: VisualSpecification;
  currentTime: number;
  width?: number;
  height?: number;
}

const SCALE_X = (containerW: number, canvasW: number) => containerW / canvasW;
const SCALE_Y = (containerH: number, canvasH: number) => containerH / canvasH;

export const SpatialCanvas: React.FC<Props> = ({
  spec,
  currentTime,
  width = 900,
  height = 630,
}) => {
  const sx = width / spec.canvas_width;
  const sy = height / spec.canvas_height;

  // Compute actor positions at currentTime
  const actorPositions = useMemo(
    () => computeActorPositions(spec, currentTime),
    [spec, currentTime]
  );

  // Active sequences (steps currently in progress)
  const activeSequences = useMemo(
    () => spec.sequences.filter(
      (seq) => currentTime >= seq.start_seconds && currentTime <= seq.end_seconds
    ),
    [spec.sequences, currentTime]
  );

  return (
    <Stage width={width} height={height} style={{ background: '#F8FAFC', borderRadius: 12 }}>
      <Layer>
        {/* Background grid */}
        <Rect x={0} y={0} width={width} height={height} fill="#F1F5F9" />

        {/* Zones */}
        {spec.zones.map((zone) => {
          const pts = zone.polygon.flatMap((p) => [p.x * sx, p.y * sy]);
          const cx = zone.polygon.reduce((s, p) => s + p.x, 0) / zone.polygon.length * sx;
          const cy = zone.polygon.reduce((s, p) => s + p.y, 0) / zone.polygon.length * sy;
          return (
            <Group key={zone.zone_id}>
              <Line
                points={pts}
                closed
                fill={zone.color}
                stroke={zone.color.replace('33', 'AA')}
                strokeWidth={2}
              />
              <Text
                x={cx - 50}
                y={cy - 8}
                width={100}
                text={zone.label}
                align="center"
                fontSize={11}
                fill="#374151"
                fontStyle="bold"
              />
            </Group>
          );
        })}

        {/* Movement paths (show full path faintly) */}
        {spec.sequences.map((seq) => {
          const pathPoints = seq.keyframes.flatMap((kf) => [
            kf.position.x * sx,
            kf.position.y * sy,
          ]);
          if (pathPoints.length < 4) return null;
          return (
            <Line
              key={`path_${seq.sequence_id}`}
              points={pathPoints}
              stroke="#94A3B8"
              strokeWidth={1}
              dash={[4, 4]}
              opacity={0.5}
            />
          );
        })}

        {/* Actor icons at current positions */}
        {spec.icons.map((icon) => {
          const pos = actorPositions[icon.icon_id];
          if (!pos) return null;
          return (
            <Group key={icon.icon_id} x={pos.x * sx} y={pos.y * sy}>
              <Circle radius={icon.size / 2} fill={icon.color} opacity={0.9} />
              <Text
                x={-icon.size}
                y={icon.size / 2 + 4}
                width={icon.size * 2}
                text={icon.label}
                align="center"
                fontSize={9}
                fill="#1E293B"
              />
            </Group>
          );
        })}

        {/* Active step annotations */}
        {activeSequences.map((seq, i) => (
          <Group key={seq.sequence_id}>
            <Rect
              x={10}
              y={10 + i * 36}
              width={260}
              height={30}
              fill="#1E40AF"
              opacity={0.85}
              cornerRadius={6}
            />
            <Text
              x={16}
              y={20 + i * 36}
              width={248}
              text={`▶ ${seq.step_title}`}
              fontSize={12}
              fill="white"
              fontStyle="bold"
              ellipsis
            />
          </Group>
        ))}
      </Layer>
    </Stage>
  );
};

// ---------------------------------------------------------------------------
// Interpolation helpers
// ---------------------------------------------------------------------------

function computeActorPositions(
  spec: VisualSpecification,
  currentTime: number
): Record<string, Coordinate> {
  const positions: Record<string, Coordinate> = {};

  for (const icon of spec.icons) {
    // Find all keyframes for this icon, sorted by time
    const kfs = spec.sequences
      .flatMap((seq) => seq.keyframes)
      .filter((kf) => kf.icon_id === icon.icon_id)
      .sort((a, b) => a.timestamp_seconds - b.timestamp_seconds);

    if (kfs.length === 0) continue;
    if (currentTime <= kfs[0].timestamp_seconds) {
      positions[icon.icon_id] = kfs[0].position;
      continue;
    }
    if (currentTime >= kfs[kfs.length - 1].timestamp_seconds) {
      positions[icon.icon_id] = kfs[kfs.length - 1].position;
      continue;
    }

    for (let i = 0; i < kfs.length - 1; i++) {
      const a = kfs[i];
      const b = kfs[i + 1];
      if (a.timestamp_seconds <= currentTime && currentTime <= b.timestamp_seconds) {
        const dt = b.timestamp_seconds - a.timestamp_seconds;
        const ratio = dt > 0 ? (currentTime - a.timestamp_seconds) / dt : 0;
        positions[icon.icon_id] = {
          x: a.position.x + ratio * (b.position.x - a.position.x),
          y: a.position.y + ratio * (b.position.y - a.position.y),
        };
        break;
      }
    }
  }

  return positions;
}
