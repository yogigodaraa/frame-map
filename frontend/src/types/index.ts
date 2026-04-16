// ProcViz TypeScript types — mirrors backend Pydantic schemas

export type DocumentDomain = 'mining' | 'healthcare' | 'defence' | 'generic';
export type ConfidenceLevel = 'high' | 'medium' | 'low';
export type ZoneType = 'work' | 'safety' | 'exclusion' | 'staging' | 'transit';

export interface Coordinate {
  x: number;
  y: number;
}

export interface Zone {
  zone_id: string;
  label: string;
  polygon: Coordinate[];
  zone_type: ZoneType;
  active_from_seconds: number;
  active_to_seconds: number | null;
  color: string;
}

export interface VisualIcon {
  icon_id: string;
  actor_id: string;
  icon_type: 'person' | 'vehicle' | 'equipment' | 'system';
  label: string;
  color: string;
  size: number;
}

export interface KeyFrame {
  keyframe_id: string;
  timestamp_seconds: number;
  icon_id: string;
  position: Coordinate;
  opacity: number;
  scale: number;
  annotation: string | null;
}

export interface AnimationSequence {
  sequence_id: string;
  step_id: string;
  step_title: string;
  start_seconds: number;
  end_seconds: number;
  keyframes: KeyFrame[];
  narration: string | null;
}

export interface ValidationIssue {
  issue_id: string;
  severity: 'critical' | 'warning' | 'info';
  step_id: string | null;
  regulation_ref: string | null;
  description: string;
  recommendation: string | null;
}

export interface VisualSpecification {
  doc_id: string;
  title: string;
  domain: DocumentDomain;
  total_duration_seconds: number;
  background_type: string;
  canvas_width: number;
  canvas_height: number;
  icons: VisualIcon[];
  zones: Zone[];
  sequences: AnimationSequence[];
  metadata: Record<string, unknown>;
  confidence_level: ConfidenceLevel;
  validation_issues: ValidationIssue[];
}

export interface JobStatus {
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'completed_with_errors' | 'failed';
  filename: string;
  domain: string;
  current_step: string | null;
  errors: string[];
  human_review_required: boolean;
}
