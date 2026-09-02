import { useEffect, useMemo, useState } from "react";
import { getTaxonomy, listDocuments, getDocumentPreview } from "../api/importApi.js";

function getNodeLabel(node) {
  return node?.name || node?.label || node?.key || "未命名分类";
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
      width="26"
      height="26"
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

// One row in the document list of a leaf category.
function DocumentRow({ doc, onPreview, isActive }) {
  return (
    <button
      className={`doc-row ${isActive ? "doc-row--active" : ""}`}
      onClick={() => onPreview(doc)}
    >
      <span className="doc-row__icon"><DocumentIcon /></span>
      <span className="doc-row__name" title={doc.filename}>{doc.filename}</span>
      <span className="doc-row__meta">
        {doc.file_size != null && <span>{fmtSize(doc.file_size)}</span>}
        {doc.source && <span className="doc-row__source">{doc.source}</span>}
        {doc.created_at && <span>{doc.created_at.slice(0, 10)}</span>}
      </span>
    </button>
  );
}

// Paginated document list for a leaf (L3) category.
function DocumentList({ path }) {
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
      .catch((err) => { if (!cancelled) setError(err.message || "文档加载失败"); })
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
      setPreview({ id: doc.id, filename: doc.filename, error: err.message || "预览加载失败" });
    } finally {
      setPreviewLoading(false);
    }
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <div className="doc-list">
      {loading && <div className="browse-state">正在加载文档…</div>}
      {!loading && error && <div className="browse-state browse-state--error">{error}</div>}
      {!loading && !error && data && data.items.length === 0 && (
        <div className="browse-state browse-state--empty">
          <span><DocumentIcon /></span>
          <strong>该分类下暂无可浏览文档</strong>
          <p>文档导入并完成确认后，会显示在这里。</p>
        </div>
      )}
      {!loading && !error && data && data.items.length > 0 && (
        <>
          <div className="doc-list__rows">
            {data.items.map((doc) => (
              <DocumentRow
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
                ← 上一页
              </button>
              <span className="pagination__info">
                第 {page} / {totalPages} 页 · 共 {data.total} 篇
              </span>
              <button
                className="pagination__btn"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                下一页 →
              </button>
            </div>
          )}
        </>
      )}
      {previewLoading && <div className="browse-state">正在加载预览…</div>}
      {!previewLoading && preview && (
        <div className="doc-preview">
          <div className="doc-preview__header">
            <span className="doc-preview__icon"><DocumentIcon /></span>
            <div className="doc-preview__title-wrap">
              <strong className="doc-preview__title">{preview.filename}</strong>
              <span className="doc-preview__meta">
                {preview.file_size != null && `${fmtSize(preview.file_size)} · `}
                {preview.source || ""}
                {preview.classification?.breadcrumb && ` · ${preview.classification.breadcrumb}`}
              </span>
            </div>
            <button className="doc-preview__close" onClick={() => setPreview(null)}>✕ 关闭</button>
          </div>
          {preview.error ? (
            <div className="doc-preview__error">{preview.error}</div>
          ) : (
            <pre className="doc-preview__body">{preview.document_body || "（无可预览文本）"}</pre>
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
        {isLeaf ? `${docCount} 篇文档` : `${childCount} 个子分类`}
      </span>
      <span className="browse-card__arrow">›</span>
    </button>
  );
}

function BackCard({ onClick }) {
  return (
    <button className="browse-card browse-card--back" onClick={onClick}>
      <span className="browse-card__icon">←</span>
      <span className="browse-card__name">返回上一级</span>
      <span className="browse-card__meta">返回上一层分类</span>
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
        if (!cancelled) setError(err.message || "分类加载失败");
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
    if (!path.length) return "知识库";
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
          <p className="browse-page__eyebrow">文档</p>
          <h1 className="browse-page__title">分类浏览</h1>
        </div>
        {taxonomy?.taxonomy_version && (
          <span className="browse-page__version">taxonomy v{taxonomy.taxonomy_version}</span>
        )}
      </header>

      <nav className="browse-breadcrumb" aria-label="分类路径">
        <button className={!path.length ? "is-current" : ""} onClick={() => goTo(-1)}>
          知识库
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
        {loading && <div className="browse-state">正在加载分类…</div>}
        {!loading && error && <div className="browse-state browse-state--error">{error}</div>}
        {!loading && !error && (
          <>
            <div className="browse-page__heading-row">
              <div>
                <h2>{heading}</h2>
                <p>{isLeaf ? "该分类下的文档" : "选择一个分类继续浏览"}</p>
              </div>
              {path.length > 0 && (
                <button className="browse-text-button" onClick={goBack}>← 返回上一级</button>
              )}
            </div>
            <div className="browse-grid">
              {path.length > 0 && <BackCard onClick={goBack} />}
              {!isLeaf && currentNodes.map((node) => (
                <CategoryCard
                  key={node.key || getNodeLabel(node)}
                  node={node}
                  onClick={() => enter(node)}
                />
              ))}
            </div>
            {isLeaf && <DocumentList path={path} />}
          </>
        )}
      </div>
    </section>
  );
}

