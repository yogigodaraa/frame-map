import React, { useCallback, useRef } from "react";
import type { DocumentDomain } from "../types";

interface UploadPanelProps {
  onUpload: (file: File, domain: DocumentDomain) => void;
  loading: boolean;
}

const DOMAINS: { value: DocumentDomain; label: string }[] = [
  { value: "mining", label: "⛏️ Mining" },
  { value: "healthcare", label: "🏥 Healthcare" },
  { value: "defence", label: "🎖️ Defence" },
  { value: "generic", label: "📄 Generic" },
];

export const UploadPanel: React.FC<UploadPanelProps> = ({
  onUpload,
  loading,
}) => {
  const fileRef = useRef<HTMLInputElement>(null);
  const [domain, setDomain] = React.useState<DocumentDomain>("mining");
  const [dragOver, setDragOver] = React.useState(false);

  const handleFile = useCallback(
    (file: File) => {
      onUpload(file, domain);
    },
    [domain, onUpload]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div style={styles.panel}>
      <h2 style={styles.heading}>ProcViz</h2>
      <p style={styles.sub}>
        Upload an industrial SOP document to auto-generate a spatial-temporal
        visual plan.
      </p>

      <label style={styles.label}>Domain</label>
      <div style={styles.domainRow}>
        {DOMAINS.map((d) => (
          <button
            key={d.value}
            style={{
              ...styles.domainBtn,
              ...(domain === d.value ? styles.domainBtnActive : {}),
            }}
            onClick={() => setDomain(d.value)}
            type="button"
          >
            {d.label}
          </button>
        ))}
      </div>

      <div
        style={{
          ...styles.dropZone,
          ...(dragOver ? styles.dropZoneActive : {}),
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
      >
        {loading ? (
          <span>⏳ Processing document…</span>
        ) : (
          <span>
            📂 Drag & drop a PDF / DOCX here, or click to browse
          </span>
        )}
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx,.doc,.txt"
          style={{ display: "none" }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  panel: {
    padding: "24px",
    background: "#1a1a2e",
    color: "#e0e0e0",
    borderRadius: "12px",
    maxWidth: "480px",
    margin: "40px auto",
    boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
    fontFamily: "Inter, system-ui, sans-serif",
  },
  heading: {
    fontSize: "2rem",
    fontWeight: 700,
    marginBottom: "8px",
    background: "linear-gradient(135deg, #4A90D9, #7ED321)",
    WebkitBackgroundClip: "text",
    WebkitTextFillColor: "transparent",
  },
  sub: {
    fontSize: "0.9rem",
    color: "#aaa",
    marginBottom: "24px",
  },
  label: {
    fontSize: "0.8rem",
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    color: "#888",
    display: "block",
    marginBottom: "8px",
  },
  domainRow: {
    display: "flex",
    gap: "8px",
    flexWrap: "wrap",
    marginBottom: "20px",
  },
  domainBtn: {
    padding: "6px 14px",
    borderRadius: "20px",
    border: "1px solid #444",
    background: "transparent",
    color: "#ccc",
    cursor: "pointer",
    fontSize: "0.85rem",
    transition: "all 0.2s",
  },
  domainBtnActive: {
    background: "#4A90D9",
    borderColor: "#4A90D9",
    color: "#fff",
  },
  dropZone: {
    border: "2px dashed #444",
    borderRadius: "8px",
    padding: "40px 20px",
    textAlign: "center",
    cursor: "pointer",
    color: "#888",
    fontSize: "0.9rem",
    transition: "all 0.2s",
  },
  dropZoneActive: {
    borderColor: "#4A90D9",
    background: "rgba(74,144,217,0.08)",
    color: "#4A90D9",
  },
};
