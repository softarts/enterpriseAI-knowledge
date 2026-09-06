// Thin client for Document Import endpoints.

const BASE = "/api/documents/import";

/**
 * Upload one file for import. Synchronous — blocks until classification is done.
 * @param {File} file
 * @returns {Promise<object>} ImportDocumentResponse
 */
export async function importDocument(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(BASE, { method: "POST", body: form });
  const body = await res.json();
  if (!res.ok) {
    const msg =
      body?.detail?.message || body?.detail || `HTTP ${res.status}`;
    const err = new Error(msg);
    err.code = body?.detail?.code || "UNKNOWN";
    throw err;
  }
  return body;
}

/**
 * Fetch the current record for an import.
 * @param {string} docId
 * @returns {Promise<object>} ImportDocumentResponse
 */
export async function getImport(docId) {
  const res = await fetch(`${BASE}/${docId}`);
  const body = await res.json();
  if (!res.ok) {
    const msg = body?.detail?.message || `HTTP ${res.status}`;
    const err = new Error(msg);
    err.code = body?.detail?.code || "UNKNOWN";
    throw err;
  }
  return body;
}

/**
 * Confirm-to-proceed: finalize the pending import into permanent storage.
 * @param {string} docId
 * @returns {Promise<object>} ImportDocumentResponse
 */
export async function confirmImport(docId) {
  const res = await fetch(`${BASE}/${docId}/confirm`, { method: "POST" });
  const body = await res.json();
  if (!res.ok) {
    const msg = body?.detail?.message || `HTTP ${res.status}`;
    const err = new Error(msg);
    err.code = body?.detail?.code || "UNKNOWN";
    throw err;
  }
  return body;
}

/**
 * Fetch the full taxonomy tree for display.
 * @returns {Promise<object>} TaxonomyResponse
 */
export async function getTaxonomy() {
  const res = await fetch("/api/taxonomy");
  if (!res.ok) throw new Error(`Failed to load taxonomy: HTTP ${res.status}`);
  return res.json();
}

/**
 * Fetch a paginated list of imported documents, optionally filtered by category.
 * @param {{categoryLevel1?: string, categoryLevel2?: string, categoryLevel3?: string, page?: number, pageSize?: number}} opts
 * @returns {Promise<object>} DocumentListResponse {items, total, page, page_size}
 */
export async function listDocuments({ categoryLevel1, categoryLevel2, categoryLevel3, page = 1, pageSize = 20 } = {}) {
  const params = new URLSearchParams();
  if (categoryLevel1) params.set("category_level_1", categoryLevel1);
  if (categoryLevel2) params.set("category_level_2", categoryLevel2);
  if (categoryLevel3) params.set("category_level_3", categoryLevel3);
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  const res = await fetch(`/api/documents?${params.toString()}`);
  const body = await res.json();
  if (!res.ok) {
    const msg = body?.detail?.message || `HTTP ${res.status}`;
    const err = new Error(msg);
    err.code = body?.detail?.code || "UNKNOWN";
    throw err;
  }
  return body;
}

/**
 * Fetch the full extracted text of one document (preview).
 * @param {string} docId
 * @returns {Promise<object>} DocumentPreviewResponse
 */
export async function getDocumentPreview(docId) {
  const res = await fetch(`/api/documents/${docId}/preview`);
  const body = await res.json();
  if (!res.ok) {
    const msg = body?.detail?.message || `HTTP ${res.status}`;
    const err = new Error(msg);
    err.code = body?.detail?.code || "UNKNOWN";
    throw err;
  }
  return body;
}
