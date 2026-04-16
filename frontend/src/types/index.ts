// ProcViz TypeScript types — mirrors the Python Pydantic schemas

export type DocumentDomain = "mining" | "healthcare" | "defence" | "generic";

export interface Coordinate {
  x: number;
  y: number;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Waypoint {
  coordinate: Coordinate;
  timestamp_seconds: number;
  label?: string;
}

export interface VisualElement {
  element_id: string;
  element_type: "icon" | "label" | "zone" | "path" | "annotation";
  icon_name?: string;
  text?: string;
  color: string;
  opacity: number;
  coordinate: Coordinate;
  bounding_box?: BoundingBox;
  z_index: number;
}

export interface Keyframe {
  element_id: string;
  timestamp_seconds: number;
  coordinate?: Coordinate;
  opacity?: number;
  color?: string;
}

export interface VisualSpecification {
  spec_id: string;
  layout_id: string;
  title: string;
  description: string;
  domain: DocumentDomain;
  canvas_width: number;
  canvas_height: number;
  background_image_url?: string;
  elements: VisualElement[];
  keyframes: Keyframe[];
  total_duration_seconds: number;
  safety_annotations: string[];
  compliance_notes: string[];
  metadata: Record<string, unknown>;
}

export interface PipelineRunResponse {
  run_id: string;
  status: "completed" | "failed" | "partial";
  errors: string[];
  warnings: string[];
  requires_human_review: boolean;
  spec_id?: string;
}
