import { useState } from "react";
import ClassificationBreadcrumb from "./ClassificationBreadcrumb.jsx";
import { confirmImport } from "../api/importApi.js";

// Human-readable file size
function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Map import_state + ui-phase to status badge text / class
function statusBadge(doc, phase) {
  if (phase === "uploading") return { label: "上传中…", cls: "badge--uploading" };
  if (phase === "classifying") return { label: "分析中…", cls: "badge--classifying" };
  if (phase === "error") return { label: "失败", cls: "badge--error" };
  if (phase === "confirming") return { label: "确认中…", cls: "badge--uploading" };
  if (doc?.import_state === "imported") return { label: "已导入", cls: "badge--imported" };
  if (doc?.import_state === "pending") {
    return doc?.status === "unknown"
      ? { label: "未分类", cls: "badge--unknown" }
      : { label: "待确认", cls: "badge--pending" };
  }
  return { label: "未知", cls: "" };
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
      setConfirmError(err.message || "确认失败");
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
          {isImported ? "✅" : isError ? "❌" : isClassifying ? "⏳" : "📄"}
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
          <span>正在分类，请稍候（CPU 模式可能需要数分钟）…</span>
        </div>
      )}

      {/* Classification result */}
      {!isClassifying && !isError && effectiveDoc && (
        <div className="doc-card__classification">
          <span className="doc-card__cls-label">分类结果</span>
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
          <span className="doc-card__path-label">路径</span>
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
            {confirming ? "确认中…" : "确认导入"}
          </button>
          <span className="doc-card__hint">
            {effectiveDoc?.status === "unknown"
              ? "分类未确定，仍可导入存档"
              : "接受分类结果并写入知识库"}
          </span>
        </div>
      )}
    </div>
  );
}
