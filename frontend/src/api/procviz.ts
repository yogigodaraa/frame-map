import axios from "axios";
import type {
  DocumentDomain,
  PipelineRunResponse,
  VisualSpecification,
} from "../types";

const BASE_URL = process.env.REACT_APP_API_URL ?? "http://localhost:8000";

const api = axios.create({ baseURL: BASE_URL });

/**
 * Upload a document and run the full ProcViz pipeline.
 */
export async function runPipeline(
  file: File,
  domain: DocumentDomain
): Promise<PipelineRunResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("domain", domain);
  const { data } = await api.post<PipelineRunResponse>(
    "/api/pipeline/run",
    formData,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data;
}

/**
 * Retrieve a VisualSpecification by its spec_id.
 */
export async function fetchSpec(specId: string): Promise<VisualSpecification> {
  const { data } = await api.get<VisualSpecification>(`/api/spec/${specId}`);
  return data;
}

/**
 * Poll the pipeline run status.
 */
export async function fetchPipelineStatus(
  runId: string
): Promise<PipelineRunResponse> {
  const { data } = await api.get<PipelineRunResponse>(
    `/api/pipeline/${runId}`
  );
  return data;
}
