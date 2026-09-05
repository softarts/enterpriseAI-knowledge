import { useState } from "react";
import ClassificationBreadcrumb from "./ClassificationBreadcrumb.jsx";
import { confirmImport } from "../api/importApi.js";

// Flat "document" icon (page with folded corner) for real documents.
function DocumentIcon() {
  return (
    <svg
      className="icon icon--document"
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 3h8l4 4v14H6z" />
      <path d="M14 3v4h4" />
      <line x1="9" y1="12" x2="15" y2="12" />
      <line x1="9" y1="16" x2="13" y2="16" />
    </svg>
  );
}

// Human-readable file size
function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Map import_state + ui-phase to status badge text / class
function statusBadge(doc, phase) {
  if (phase === "uploading") return { label: "Uploading…", cls: "badge--uploading" };
  if (phase === "classifying") return { label: "Classifying…", cls: "badge--classifying" };
  if (phase === "error") return { label: "Failed", cls: "badge--error" };
  if (phase === "confirming") return { label: "Confirming…", cls: "badge--uploading" };
  if (doc?.import_state === "imported") return { label: "Imported", cls: "badge--imported" };
  if (doc?.import_state === "pending") {
    return doc?.status === "unknown"
      ? { label: "Unclassified", cls: "badge--unknown" }
      : { label: "Pending", cls: "badge--pending" };
  }
  return { label: "Unknown", cls: "" };
}

export default function DocumentCard({ fileObj, doc, phase, error, onConfirmed }) {
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState(null);
  const [localDoc, setLocalDoc] = useState(doc);
  const [localPhase, setLocalPhase] = useState(phase);

  // Sync when parent updates doc/phase (e.g. after import completes)
  // Use a simple prop approach: parent controls phase until confirm.
  const effectiveDoc = localDoc ?? doc;
  const effectivePhase = confirming ? "confirming" : (localPhase === phase ? phase : localPhase);

  async function handleConfirm() {
    if (!effectiveDoc?.id) return;
    setConfirming(true);
    setConfirmError(null);
    try {
      const confirmed = await confirmImport(effectiveDoc.id);
      setLocalDoc(confirmed);
      setLocalPhase("done");
      if (onConfirmed) onConfirmed(confirmed);
    } catch (err) {
      setConfirmError(err.message || "Confirmation failed");
    } finally {
      setConfirming(false);
    }
  }

  const badge = statusBadge(effectiveDoc ?? doc, confirming ? "confirming" : phase);
  const isImported = (effectiveDoc ?? doc)?.import_state === "imported";
  const isPending = (effectiveDoc ?? doc)?.import_state === "pending" && phase !== "uploading" && phase !== "classifying" && phase !== "error";
  const isClassifying = phase === "classifying";
  const isError = phase === "error";

  return (
    <div className={`doc-card ${isImported ? "doc-card--imported" : ""} ${isError ? "doc-card--error" : ""}`}>
      {/* Header row */}
      <div className="doc-card__header">
        <span className="doc-card__icon">
          {isImported ? "✅" : isError ? "❌" : isClassifying ? "⏳" : <DocumentIcon />}
        </span>
        <div className="doc-card__meta">
          <span className="doc-card__filename" title={fileObj?.name}>
            {fileObj?.name || effectiveDoc?.filename || "—"}
          </span>
          {fileObj?.size != null && (
            <span className="doc-card__size">{fmtSize(fileObj.size)}</span>
          )}
        </div>
        <span className={`badge ${badge.cls}`}>{badge.label}</span>
      </div>

      {/* Classifying spinner state */}
      {isClassifying && (
        <div className="doc-card__classifying">
          <div className="spinner" />
          <span>Classifying, please wait (CPU mode may take a few minutes)…</span>
        </div>
      )}

      {/* Classification result */}
      {!isClassifying && !isError && effectiveDoc && (
        <div className="doc-card__classification">
          <span className="doc-card__cls-label">Classification</span>
          <ClassificationBreadcrumb
            classification={effectiveDoc.classification}
            status={effectiveDoc.status}
          />
          <span className="doc-card__tax-version">{effectiveDoc.taxonomy_version}</span>
        </div>
      )}

      {/* Storage path (after import) */}
      {isImported && effectiveDoc?.storage_path && (
        <div className="doc-card__path" title={effectiveDoc.storage_path}>
          <span className="doc-card__path-label">Path</span>
          <code className="doc-card__path-value">{effectiveDoc.storage_path}</code>
        </div>
      )}

      {/* Error message */}
      {isError && error && (
        <div className="doc-card__error">{error}</div>
      )}
      {confirmError && (
        <div className="doc-card__error">{confirmError}</div>
      )}

      {/* Confirm action */}
      {isPending && !isImported && (
        <div className="doc-card__actions">
          <button
            className="btn btn--primary"
            onClick={handleConfirm}
            disabled={confirming}
            id={`confirm-btn-${effectiveDoc?.id}`}
          >
            {confirming ? "Confirming…" : "Confirm Import"}
          </button>
          <span className="doc-card__hint">
            {effectiveDoc?.status === "unknown"
              ? "Classification uncertain; can still be archived"
              : "Accept classification and save to knowledge base"}
          </span>
        </div>
      )}
    </div>
  );
}
