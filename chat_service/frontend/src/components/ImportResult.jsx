import ClassificationBreadcrumb from "./ClassificationBreadcrumb.jsx";

// Human-readable file size
function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Get file icon based on extension
function getFileIcon(filename) {
  const ext = filename?.split('.').pop()?.toLowerCase() || '';
  const iconMap = {
    pdf: '📄',
    docx: '📝',
    doc: '📝',
    txt: '📃',
    md: '📃',
    html: '🌐',
    htm: '🌐',
    rst: '📃',
  };
  return iconMap[ext] || '📄';
}

// Format classifier score
function fmtScore(score) {
  if (score == null) return '—';
  return score.toFixed(2);
}

export default function ImportResult({ fileObj, doc, onConfirm, onCancel }) {
  const classification = doc?.classification;
  const levelScores = classification?.level_scores || {};

  // Build storage path from classification
  const buildStoragePath = () => {
    if (doc?.storage_path) {
      return doc.storage_path;
    }
    // Predict storage path based on UUID and filename (same logic as backend)
    // Format: documents/{shard}/{uuid}_{safe_filename}
    if (!doc?.id || !fileObj?.name) return null;
    
    // Simple shard calculation (matching backend logic)
    const shard = parseInt(doc.id.split('').reduce((a, b) => {
      a = ((a << 5) - a) + b.charCodeAt(0);
      return a & a;
    }, 0) >>> 0, 10) % 256;
    const shardStr = shard.toString().padStart(3, '0');
    
    // Sanitize filename (simple version)
    const safeName = fileObj.name.replace(/[^A-Za-z0-9._ \-()]/g, '_').replace(/^[ .]+|[ .]+$/g, '') || 'file';
    
    return `documents/${shardStr}/${doc.id}_${safeName}`;
  };

  const storagePath = buildStoragePath();

  return (
    <div className="import-result">
      <div className="import-result__layout">
        {/* Left panel: Document info + Classification + Storage */}
        <div className="import-result__left">
          <div className="import-result__section">
            <h3 className="import-result__section-title">Document Info</h3>
            <div className="import-result__info">
              <div className="import-result__info-row">
                <span className="import-result__icon">{getFileIcon(fileObj?.name)}</span>
                <div className="import-result__file-details">
                  <div className="import-result__filename" title={fileObj?.name}>
                    {fileObj?.name || doc?.filename || '—'}
                  </div>
                  <div className="import-result__file-meta">
                    <span className="import-result__file-type">
                      {(fileObj?.name || doc?.filename || '').split('.').pop()?.toUpperCase() || '—'}
                    </span>
                    <span className="import-result__file-size">
                      {fileObj?.size ? fmtSize(fileObj.size) : '—'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Classification result */}
          {classification && (
            <div className="import-result__section">
              <h3 className="import-result__section-title">Classification</h3>
              <div className="import-result__classification">
                <ClassificationBreadcrumb
                  classification={classification}
                  status={doc?.status}
                />
                <div className="import-result__scores">
                  <div className="import-result__score-row">
                    <span className="import-result__score-label">L1</span>
                    <span className="import-result__score-value">{fmtScore(levelScores.L1)}</span>
                  </div>
                  <div className="import-result__score-row">
                    <span className="import-result__score-label">L2</span>
                    <span className="import-result__score-value">{fmtScore(levelScores.L2)}</span>
                  </div>
                  <div className="import-result__score-row">
                    <span className="import-result__score-label">L3</span>
                    <span className="import-result__score-value">{fmtScore(levelScores.L3)}</span>
                  </div>
                </div>
                <div className="import-result__tax-version">
                  Taxonomy {doc?.taxonomy_version || 'v7'}
                </div>
              </div>
            </div>
          )}

          {/* Storage location */}
          <div className="import-result__section">
            <h3 className="import-result__section-title">Storage Location</h3>
            <div className="import-result__storage">
              {storagePath ? (
                <div className="import-result__storage-path">
                  {storagePath.split('/').map((part, i, arr) => (
                    <span key={i}>
                      {i > 0 && <span className="import-result__storage-sep">›</span>}
                      <span className="import-result__storage-part">{part}</span>
                    </span>
                  ))}
                </div>
              ) : (
                <span className="import-result__storage-unknown">Undetermined</span>
              )}
            </div>
          </div>
        </div>

        {/* Right panel: Document body preview */}
        <div className="import-result__right">
          <div className="import-result__preview-header">
            <h3 className="import-result__preview-title">Document Content</h3>
          </div>
          <div className="import-result__preview-content">
            {doc?.document_body ? (
              <pre className="import-result__preview-text">{doc.document_body}</pre>
            ) : (
              <div className="import-result__preview-empty">No content</div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom action bar */}
      <div className="import-result__actions">
        <button
          className="btn btn--secondary"
          onClick={onCancel}
        >
          Cancel
        </button>
        <button
          className="btn btn--primary"
          onClick={onConfirm}
        >
          Confirm Import
        </button>
      </div>
    </div>
  );
}
