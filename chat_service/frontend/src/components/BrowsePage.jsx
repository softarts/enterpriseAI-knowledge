import { useEffect, useMemo, useState } from "react";
import { getTaxonomy, listDocuments, getDocumentPreview } from "../api/importApi.js";

function getNodeLabel(node) {
  return node?.name || node?.label || node?.key || "Untitled Category";
}

// Flat "index card" icon used for ALL category levels (L1/L2/L3):
// a plain card with 1-2 text lines, like a catalogue index card.
function IndexCardIcon() {
  return (
    <svg
      className="icon icon--index-card"
      viewBox="0 0 24 24"
      width="26"
      height="26"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <line x1="7" y1="10" x2="17" y2="10" />
      <line x1="7" y1="14" x2="13" y2="14" />
    </svg>
  );
}

// Flat "document" icon used for real documents (page with folded corner).
function DocumentIcon() {
  return (
    <svg
      className="icon icon--document"
      viewBox="0 0 24 24"
      width="24"
      height="24"
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

function fmtSize(bytes) {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function BackCard({ onClick }) {
  return (
    <button className="browse-card browse-card--back" onClick={onClick}>
      <span className="browse-card__icon">←</span>
      <span className="browse-card__name">Back</span>
      <span className="browse-card__meta">Go to previous category</span>
    </button>
  );
}

// One document card in the list of a leaf category (L3).
function DocumentCard({ doc, onPreview, isActive }) {
  return (
    <button
      className={`browse-card browse-card--doc ${isActive ? "browse-card--active" : ""}`}
      onClick={() => onPreview(doc)}
    >
      <span className="browse-card__icon">
        <DocumentIcon />
      </span>
      <span className="browse-card__doc-name" title={doc.filename}>
        {doc.filename}
      </span>
      <div className="browse-card__doc-meta">
        <span className="browse-card__doc-size">{fmtSize(doc.file_size)}</span>
        {doc.created_at && (
          <span className="browse-card__doc-date">{doc.created_at.slice(0, 10)}</span>
        )}
      </div>
    </button>
  );
}

// Paginated document list for a leaf (L3) category.
function DocumentList({ path, onBack }) {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(null);       // preview response
  const [previewLoading, setPreviewLoading] = useState(false);
  const pageSize = 10;

  const catKey = path.map(getNodeLabel).join(">");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    listDocuments({
      categoryLevel1: getNodeLabel(path[0]),
      categoryLevel2: path[1] ? getNodeLabel(path[1]) : undefined,
      categoryLevel3: path[2] ? getNodeLabel(path[2]) : undefined,
      page,
      pageSize,
    })
      .then((d) => { if (!cancelled) setData(d); })
      .catch((err) => { if (!cancelled) setError(err.message || "Failed to load documents"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catKey, page]);

  // Reset to page 1 and close preview when the category changes.
  useEffect(() => {
    setPage(1);
    setPreview(null);
  }, [catKey]);

  async function openPreview(doc) {
    if (preview?.id === doc.id) { setPreview(null); return; }
    setPreviewLoading(true);
    try {
      const full = await getDocumentPreview(doc.id);
      setPreview(full);
    } catch (err) {
      setPreview({ id: doc.id, filename: doc.filename, error: err.message || "Failed to load preview" });
    } finally {
      setPreviewLoading(false);
    }
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <div className="doc-list-view">
      {loading && (
        <>
          <div className="browse-grid">
            {onBack && <BackCard onClick={onBack} />}
          </div>
          <div className="browse-state">Loading documents…</div>
        </>
      )}
      {!loading && error && (
        <>
          <div className="browse-grid">
            {onBack && <BackCard onClick={onBack} />}
          </div>
          <div className="browse-state browse-state--error">{error}</div>
        </>
      )}
      {!loading && !error && data && data.items.length === 0 && (
        <>
          <div className="browse-grid">
            {onBack && <BackCard onClick={onBack} />}
          </div>
          <div className="browse-state browse-state--empty">
            <span><DocumentIcon /></span>
            <strong>No documents in this category</strong>
            <p>Documents will appear here once imported and confirmed.</p>
          </div>
        </>
      )}
      {!loading && !error && data && data.items.length > 0 && (
        <>
          <div className="browse-grid">
            {onBack && <BackCard onClick={onBack} />}
            {data.items.map((doc) => (
              <DocumentCard
                key={doc.id}
                doc={doc}
                onPreview={openPreview}
                isActive={preview?.id === doc.id}
              />
            ))}
          </div>
          {totalPages > 1 && (
            <div className="pagination">
              <button
                className="pagination__btn"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                ← Previous
              </button>
              <span className="pagination__info">
                Page {page} of {totalPages} · {data.total} documents
              </span>
              <button
                className="pagination__btn"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
      {previewLoading && <div className="browse-state">Loading preview…</div>}
      {!previewLoading && preview && (
        <div className="doc-preview">
          <div className="doc-preview__header">
            <span className="doc-preview__icon"><DocumentIcon /></span>
            <div className="doc-preview__title-wrap">
              <strong className="doc-preview__title">{preview.filename}</strong>
              <span className="doc-preview__meta">
                {preview.file_size != null && `${fmtSize(preview.file_size)} · `}
                {preview.classification?.breadcrumb && `${preview.classification.breadcrumb}`}
              </span>
            </div>
            <button className="doc-preview__close" onClick={() => setPreview(null)}>✕ Close</button>
          </div>
          {preview.error ? (
            <div className="doc-preview__error">{preview.error}</div>
          ) : (
            <pre className="doc-preview__body">{preview.document_body || "(No previewable text)"}</pre>
          )}
        </div>
      )}
    </div>
  );
}

function CategoryCard({ node, onClick }) {
  const childCount = node.children?.length || 0;
  const isLeaf = childCount === 0;
  const docCount = node.document_count ?? 0;

  return (
    <button className="browse-card browse-card--category" onClick={onClick}>
      <span className="browse-card__icon"><IndexCardIcon /></span>
      <span className="browse-card__name">{getNodeLabel(node)}</span>
      <span className="browse-card__meta">
        {isLeaf ? `${docCount} documents` : `${childCount} subcategories`}
      </span>
      <span className="browse-card__arrow">›</span>
    </button>
  );
}

export default function BrowsePage() {
  const [taxonomy, setTaxonomy] = useState(null);
  const [path, setPath] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getTaxonomy()
      .then((data) => {
        if (!cancelled) setTaxonomy(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Failed to load categories");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const nodes = taxonomy?.nodes || [];
  const currentNode = path[path.length - 1];
  const currentNodes = currentNode?.children || nodes;
  const isLeaf = Boolean(currentNode && !currentNode.children?.length);

  const heading = useMemo(() => {
    if (!path.length) return "Knowledge Base";
    return getNodeLabel(currentNode);
  }, [currentNode, path.length]);

  function enter(node) {
    setPath((currentPath) => [...currentPath, node]);
  }

  function goTo(index) {
    setPath(index < 0 ? [] : path.slice(0, index + 1));
  }

  function goBack() {
    setPath((currentPath) => currentPath.slice(0, -1));
  }

  return (
    <section className="browse-page">
      <header className="browse-page__header">
        <div>
          <p className="browse-page__eyebrow">Documents</p>
          <h1 className="browse-page__title">Browse Categories</h1>
        </div>
        {taxonomy?.taxonomy_version && (
          <span className="browse-page__version">taxonomy v{taxonomy.taxonomy_version}</span>
        )}
      </header>

      <nav className="browse-breadcrumb" aria-label="Category path">
        <button className={!path.length ? "is-current" : ""} onClick={() => goTo(-1)}>
          Knowledge Base
        </button>
        {path.map((node, index) => (
          <span className="browse-breadcrumb__part" key={`${node.key || getNodeLabel(node)}-${index}`}>
            <span className="browse-breadcrumb__separator">›</span>
            <button className={index === path.length - 1 ? "is-current" : ""} onClick={() => goTo(index)}>
              {getNodeLabel(node)}
            </button>
          </span>
        ))}
      </nav>

      <div className="browse-page__body">
        {loading && <div className="browse-state">Loading categories…</div>}
        {!loading && error && <div className="browse-state browse-state--error">{error}</div>}
        {!loading && !error && (
          <>
            <div className="browse-page__heading-row">
              <div>
                <h2>{heading}</h2>
                <p>{isLeaf ? "Documents in this category" : "Select a category to browse"}</p>
              </div>
              {path.length > 0 && (
                <button className="browse-text-button" onClick={goBack}>← Back</button>
              )}
            </div>
            {!isLeaf ? (
              <div className="browse-grid">
                {path.length > 0 && <BackCard onClick={goBack} />}
                {currentNodes.map((node) => (
                  <CategoryCard
                    key={node.key || getNodeLabel(node)}
                    node={node}
                    onClick={() => enter(node)}
                  />
                ))}
              </div>
            ) : (
              <DocumentList path={path} onBack={path.length > 0 ? goBack : null} />
            )}
          </>
        )}
      </div>
    </section>
  );
}

