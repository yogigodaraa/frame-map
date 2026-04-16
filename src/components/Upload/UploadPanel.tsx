import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import type { DocumentDomain } from '../../types';

interface Props {
  onSubmit: (file: File, domain: DocumentDomain) => void;
  loading: boolean;
}

const DOMAINS: { value: DocumentDomain; label: string; emoji: string }[] = [
  { value: 'mining', label: 'Mining', emoji: '⛏️' },
  { value: 'healthcare', label: 'Healthcare', emoji: '🏥' },
  { value: 'defence', label: 'Defence', emoji: '🛡️' },
  { value: 'generic', label: 'Generic', emoji: '📄' },
];

export const UploadPanel: React.FC<Props> = ({ onSubmit, loading }) => {
  const [file, setFile] = useState<File | null>(null);
  const [domain, setDomain] = useState<DocumentDomain>('generic');

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) setFile(accepted[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1,
  });

  const handleSubmit = () => {
    if (file) onSubmit(file, domain);
  };

  return (
    <div className="flex flex-col gap-6 p-8 max-w-xl mx-auto">
      <h1 className="text-3xl font-bold text-gray-900">ProcViz</h1>
      <p className="text-gray-500 text-sm">
        Upload an industrial procedure document (SOP, work instruction, CONOPS) and get an
        interactive spatial-temporal visual plan.
      </p>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors
          ${isDragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-blue-400'}`}
      >
        <input {...getInputProps()} />
        {file ? (
          <div className="flex flex-col items-center gap-2">
            <span className="text-4xl">📄</span>
            <p className="font-medium text-gray-700">{file.name}</p>
            <p className="text-xs text-gray-400">{(file.size / 1024).toFixed(0)} KB</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 text-gray-400">
            <span className="text-4xl">⬆️</span>
            <p>{isDragActive ? 'Drop it!' : 'Drag & drop a PDF, or click to browse'}</p>
          </div>
        )}
      </div>

      {/* Domain selector */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Domain</label>
        <div className="grid grid-cols-4 gap-2">
          {DOMAINS.map((d) => (
            <button
              key={d.value}
              onClick={() => setDomain(d.value)}
              className={`flex flex-col items-center gap-1 p-3 rounded-lg border text-sm font-medium transition-colors
                ${domain === d.value
                  ? 'border-blue-500 bg-blue-50 text-blue-700'
                  : 'border-gray-200 hover:border-blue-300 text-gray-600'}`}
            >
              <span className="text-xl">{d.emoji}</span>
              {d.label}
            </button>
          ))}
        </div>
      </div>

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={!file || loading}
        className="w-full py-3 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700
          disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? 'Processing…' : 'Generate Visual Plan'}
      </button>
    </div>
  );
};
