import React, { useState, useCallback } from "react";
import { runPipeline, fetchSpec } from "../api/procviz";
import { UploadPanel } from "./UploadPanel";
import { CanvasRenderer } from "./CanvasRenderer";
import type { DocumentDomain, PipelineRunResponse, VisualSpecification } from "../types";

type AppState = "idle" | "uploading" | "success" | "error";

export const App: React.FC = () => {
  const [appState, setAppState] = useState<AppState>("idle");
  const [runResult, setRunResult] = useState<PipelineRunResponse | null>(null);
  const [spec, setSpec] = useState<VisualSpecification | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");

  const handleUpload = useCallback(
    async (file: File, domain: DocumentDomain) => {
      setAppState("uploading");
      setErrorMsg("");
      setSpec(null);
      setRunResult(null);

      try {
        const result = await runPipeline(file, domain);
        setRunResult(result);

        if (result.status === "completed" && result.spec_id) {
          const fetchedSpec = await fetchSpec(result.spec_id);
          setSpec(fetchedSpec);
          setAppState("success");
        } else {
          setErrorMsg(result.errors.join("; ") || "Pipeline did not complete.");
          setAppState("error");
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setErrorMsg(`Network or server error: ${msg}`);
        setAppState("error");
      }
    },
    []
  );

  return (
    <div style={styles.root}>
      <UploadPanel
        onUpload={handleUpload}
        loading={appState === "uploading"}
      />

      {appState === "error" && (
        <div style={styles.errorBox}>
          <strong>⚠️ Error:</strong> {errorMsg}
          {runResult?.warnings && runResult.warnings.length > 0 && (
            <ul>
              {runResult.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
        </div>
      )}

      {runResult?.requires_human_review && (
        <div style={styles.reviewBanner}>
          🔍 <strong>Human review required</strong> — low confidence extraction.
          A domain expert has been notified.
        </div>
      )}

      {spec && appState === "success" && (
        <div style={styles.canvasWrapper}>
          <CanvasRenderer spec={spec} />
        </div>
      )}
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  root: {
    minHeight: "100vh",
    background: "#0d0d1a",
    padding: "16px",
  },
  errorBox: {
    maxWidth: "480px",
    margin: "16px auto",
    background: "rgba(229, 57, 53, 0.12)",
    border: "1px solid rgba(229,57,53,0.4)",
    borderRadius: "8px",
    padding: "12px 16px",
    color: "#ef9a9a",
    fontSize: "0.9rem",
    fontFamily: "Inter, system-ui, sans-serif",
  },
  reviewBanner: {
    maxWidth: "480px",
    margin: "12px auto",
    background: "rgba(245, 166, 35, 0.12)",
    border: "1px solid rgba(245,166,35,0.4)",
    borderRadius: "8px",
    padding: "10px 16px",
    color: "#F5A623",
    fontSize: "0.9rem",
    fontFamily: "Inter, system-ui, sans-serif",
  },
  canvasWrapper: {
    maxWidth: "1400px",
    margin: "24px auto",
    background: "#1a1a2e",
    borderRadius: "12px",
    padding: "16px",
    boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
  },
};
