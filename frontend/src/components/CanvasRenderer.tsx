import React, { useEffect, useRef, useState } from "react";
import { Stage, Layer, Circle, Rect, Text, Group } from "react-konva";
import type { Keyframe, VisualElement, VisualSpecification } from "../types";

interface CanvasRendererProps {
  spec: VisualSpecification;
}

/** Interpolate a coordinate value at the given playhead time. */
function interpolateCoord(
  elementId: string,
  keyframes: Keyframe[],
  time: number,
  axis: "x" | "y"
): number | undefined {
  const kfs = keyframes
    .filter((kf) => kf.element_id === elementId && kf.coordinate)
    .sort((a, b) => a.timestamp_seconds - b.timestamp_seconds);

  if (kfs.length === 0) return undefined;
  if (time <= kfs[0].timestamp_seconds) return kfs[0].coordinate![axis];
  if (time >= kfs[kfs.length - 1].timestamp_seconds)
    return kfs[kfs.length - 1].coordinate![axis];

  for (let i = 0; i < kfs.length - 1; i++) {
    const a = kfs[i];
    const b = kfs[i + 1];
    if (time >= a.timestamp_seconds && time <= b.timestamp_seconds) {
      const t =
        (time - a.timestamp_seconds) / (b.timestamp_seconds - a.timestamp_seconds);
      return a.coordinate![axis]! + (b.coordinate![axis]! - a.coordinate![axis]!) * t;
    }
  }
  return undefined;
}

export const CanvasRenderer: React.FC<CanvasRendererProps> = ({ spec }) => {
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const animRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number | null>(null);

  const DISPLAY_W = Math.min(spec.canvas_width, window.innerWidth - 48);
  const scale = DISPLAY_W / spec.canvas_width;
  const DISPLAY_H = spec.canvas_height * scale;

  useEffect(() => {
    if (playing) {
      const step = (now: number) => {
        if (lastTimeRef.current === null) lastTimeRef.current = now;
        const dt = (now - lastTimeRef.current) / 1000;
        lastTimeRef.current = now;
        setPlayhead((prev) => {
          const next = prev + dt;
          if (next >= spec.total_duration_seconds) {
            setPlaying(false);
            return spec.total_duration_seconds;
          }
          return next;
        });
        animRef.current = requestAnimationFrame(step);
      };
      animRef.current = requestAnimationFrame(step);
    } else {
      lastTimeRef.current = null;
      if (animRef.current) cancelAnimationFrame(animRef.current);
    }
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, [playing, spec.total_duration_seconds]);

  const resolvePosition = (el: VisualElement) => {
    const ix = interpolateCoord(el.element_id, spec.keyframes, playhead, "x");
    const iy = interpolateCoord(el.element_id, spec.keyframes, playhead, "y");
    return {
      x: (ix ?? el.coordinate.x) * scale,
      y: (iy ?? el.coordinate.y) * scale,
    };
  };

  const renderElement = (el: VisualElement) => {
    const pos = resolvePosition(el);

    if (el.element_type === "zone" && el.bounding_box) {
      return (
        <Rect
          key={el.element_id}
          x={el.bounding_box.x * scale}
          y={el.bounding_box.y * scale}
          width={el.bounding_box.width * scale}
          height={el.bounding_box.height * scale}
          fill={el.color}
          opacity={el.opacity}
          cornerRadius={8 * scale}
        />
      );
    }

    if (el.element_type === "icon") {
      return (
        <Group key={el.element_id} x={pos.x} y={pos.y}>
          <Circle radius={18 * scale} fill={el.color} opacity={el.opacity} />
        </Group>
      );
    }

    if (el.element_type === "label" && el.text) {
      return (
        <Text
          key={el.element_id}
          x={pos.x - 60 * scale}
          y={pos.y}
          width={120 * scale}
          text={el.text}
          fontSize={Math.max(10, 12 * scale)}
          fill={el.color}
          opacity={el.opacity}
          align="center"
        />
      );
    }

    return null;
  };

  return (
    <div style={styles.wrapper}>
      <div style={styles.header}>
        <h3 style={styles.title}>{spec.title}</h3>
        <p style={styles.desc}>{spec.description}</p>
      </div>

      <Stage width={DISPLAY_W} height={DISPLAY_H} style={styles.stage}>
        <Layer>
          {/* Background */}
          <Rect
            width={DISPLAY_W}
            height={DISPLAY_H}
            fill="#0d0d1a"
            cornerRadius={8}
          />
          {/* Elements sorted by z_index */}
          {[...spec.elements]
            .sort((a, b) => a.z_index - b.z_index)
            .map(renderElement)}
        </Layer>
      </Stage>

      {/* Timeline controls */}
      <div style={styles.controls}>
        <button
          style={styles.playBtn}
          onClick={() => {
            if (playhead >= spec.total_duration_seconds) setPlayhead(0);
            setPlaying((p) => !p);
          }}
        >
          {playing ? "⏸ Pause" : "▶ Play"}
        </button>
        <input
          type="range"
          min={0}
          max={spec.total_duration_seconds}
          step={0.1}
          value={playhead}
          onChange={(e) => {
            setPlaying(false);
            setPlayhead(Number(e.target.value));
          }}
          style={styles.slider}
        />
        <span style={styles.time}>
          {playhead.toFixed(1)}s / {spec.total_duration_seconds.toFixed(0)}s
        </span>
      </div>

      {/* Annotations */}
      {spec.safety_annotations.length > 0 && (
        <div style={styles.annotations}>
          <strong>⚠️ Safety Annotations</strong>
          <ul>
            {spec.safety_annotations.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}

      {spec.compliance_notes.length > 0 && (
        <div style={styles.compliance}>
          <strong>📋 Compliance Notes</strong>
          <ul>
            {spec.compliance_notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    fontFamily: "Inter, system-ui, sans-serif",
    color: "#e0e0e0",
    padding: "16px",
    maxWidth: "100%",
  },
  header: {
    marginBottom: "12px",
  },
  title: {
    fontSize: "1.4rem",
    fontWeight: 700,
    margin: "0 0 4px",
    background: "linear-gradient(135deg, #4A90D9, #7ED321)",
    WebkitBackgroundClip: "text",
    WebkitTextFillColor: "transparent",
  },
  desc: {
    fontSize: "0.85rem",
    color: "#888",
    margin: 0,
  },
  stage: {
    borderRadius: "8px",
    overflow: "hidden",
    display: "block",
  },
  controls: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    marginTop: "12px",
    flexWrap: "wrap",
  },
  playBtn: {
    padding: "8px 20px",
    borderRadius: "6px",
    border: "none",
    background: "#4A90D9",
    color: "#fff",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: "0.9rem",
  },
  slider: {
    flex: 1,
    minWidth: "120px",
    accentColor: "#4A90D9",
  },
  time: {
    fontSize: "0.85rem",
    color: "#888",
    whiteSpace: "nowrap",
  },
  annotations: {
    marginTop: "16px",
    background: "rgba(245, 166, 35, 0.1)",
    border: "1px solid rgba(245, 166, 35, 0.3)",
    borderRadius: "8px",
    padding: "12px 16px",
    fontSize: "0.85rem",
    color: "#F5A623",
  },
  compliance: {
    marginTop: "12px",
    background: "rgba(74, 144, 217, 0.1)",
    border: "1px solid rgba(74, 144, 217, 0.3)",
    borderRadius: "8px",
    padding: "12px 16px",
    fontSize: "0.85rem",
    color: "#4A90D9",
  },
};
