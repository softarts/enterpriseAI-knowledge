import { useState, useRef, useEffect } from "react";
import DocumentCard from "./DocumentCard.jsx";
import ImportResult from "./ImportResult.jsx";
import { importDocument, confirmImport } from "../api/importApi.js";

const ALLOWED_EXTS = [".pdf", ".docx", ".doc", ".html", ".htm", ".txt", ".md", ".rst"];
const ALLOWED_MIME = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
  "text/html",
  "text/plain",
  "text/markdown",
  "text/x-rst",
];
const MAX_MB = 25;
const MAX_BYTES = MAX_MB * 1024 * 1024;

function extOf(name) {
  const idx = name.lastIndexOf(".");
  return idx >= 0 ? name.slice(idx).toLowerCase() : "";
}

function validateFile(file) {
  if (!file) return "未选择文件";
  if (file.size === 0) return "文件为空";
  if (file.size > MAX_BYTES) return `文件超过 ${MAX_MB} MB 上限`;
  const ext = extOf(file.name);
  if (!ALLOWED_EXTS.includes(ext)) {
    return `不支持 ${ext || "(无扩展名)"} 格式，支持：${ALLOWED_EXTS.join("  ")}`;
  }
  return null;
}

export default function UploadArea({ onImportStarted }) {
  const [dragOver, setDragOver] = useState(false);
  const [validationError, setValidationError] = useState(null);
  const fileInputRef = useRef(null);

  // List of import entries: { id, fileObj, doc, phase, error }
  const [imports, setImports] = useState([]);
  const [activeResult, setActiveResult] = useState(null);

  function updateEntry(id, patch) {
    setImports((prev) =>
      prev.map((e) => (e.id === id ? { ...e, ...patch } : e))
    );
  }

  async function processFile(file) {
    const err = validateFile(file);
    if (err) {
      setValidationError(err);
      return;
    }
    setValidationError(null);

    const entryId = `${Date.now()}-${Math.random()}`;
    const entry = { id: entryId, fileObj: file, doc: null, phase: "uploading", error: null };
    setImports((prev) => [entry, ...prev]);

    // Upload & classify (synchronous on server side)
    try {
      // Show classifying state once upload bytes are sent
      updateEntry(entryId, { phase: "classifying" });
      const doc = await importDocument(file);
      updateEntry(entryId, { doc, phase: "classified" });
      // Show import result panel for the newly classified document
      setActiveResult({ id: entryId, fileObj: file, doc });
    } catch (e) {
      updateEntry(entryId, { phase: "error", error: e.message || "导入失败" });
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) processFile(file);
  }

  function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (file) processFile(file);
    // Reset so same file can be selected again
    e.target.value = "";
  }

  async function handleConfirmImport() {
    if (!activeResult?.doc?.id) return;
    try {
      const confirmed = await confirmImport(activeResult.doc.id);
      updateEntry(activeResult.id, { doc: confirmed, phase: "done" });
      setActiveResult(null);
    } catch (err) {
      console.error("Confirm failed:", err);
      // Could show error in the UI
    }
  }

  function handleCancelImport() {
    setActiveResult(null);
    // Optionally remove the entry from imports list
    setImports((prev) => prev.filter((e) => e.id !== activeResult.id));
  }

  // Prevent accidental refresh during import
  useEffect(() => {
    const hasActiveImport = activeResult !== null || imports.some(e => e.phase === "uploading" || e.phase === "classifying");

    const handleBeforeUnload = (e) => {
      if (hasActiveImport) {
        e.preventDefault();
        e.returnValue = "";
        return "";
      }
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [activeResult, imports]);

  return (
    <div className="upload-area-container">
      {/* Drop zone */}
      <div
        className={`upload-dropzone ${dragOver ? "upload-dropzone--over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        id="upload-dropzone"
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click(); }}
        aria-label="拖放或点击选择文件上传"
      >
        <div className="upload-dropzone__icon">📂</div>
        <div className="upload-dropzone__primary">
          拖放文件到此处，或 <span className="upload-dropzone__link">点击选择</span>
        </div>
        <div className="upload-dropzone__hint">
          支持：PDF · DOCX · TXT · Markdown · HTML · RST &nbsp;·&nbsp; 最大 {MAX_MB} MB
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept={ALLOWED_EXTS.join(",")}
          onChange={handleFileChange}
          style={{ display: "none" }}
          id="upload-file-input"
        />
      </div>

      {/* Validation error */}
      {validationError && (
        <div className="upload-validation-error">
          ⚠️ {validationError}
        </div>
      )}

      {/* Import result panel */}
      {activeResult && (
        <ImportResult
          fileObj={activeResult.fileObj}
          doc={activeResult.doc}
          onConfirm={handleConfirmImport}
          onCancel={handleCancelImport}
        />
      )}

      {/* Import cards list */}
      {imports.length > 0 && !activeResult && (
        <div className="upload-cards">
          <div className="upload-cards__header">
            <span className="upload-cards__title">导入记录</span>
            <span className="upload-cards__count">{imports.length} 个文件</span>
          </div>
          <div className="upload-cards__list">
            {imports.map((entry) => (
              <DocumentCard
                key={entry.id}
                fileObj={entry.fileObj}
                doc={entry.doc}
                phase={entry.phase}
                error={entry.error}
                onConfirmed={(confirmed) => updateEntry(entry.id, { doc: confirmed, phase: "done" })}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
