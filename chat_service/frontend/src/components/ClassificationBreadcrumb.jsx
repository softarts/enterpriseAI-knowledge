// Classification breadcrumb component.
// Shows "A › B › C" for classified docs.
// Shows a special pill for UNKNOWN status.

export default function ClassificationBreadcrumb({ classification, status }) {
  if (status === "unknown" || !classification) {
    return (
      <span className="breadcrumb breadcrumb--unknown" title="Taxonomy classifier could not determine a category">
        <span className="breadcrumb__unknown-icon">?</span>
        Unclassified
      </span>
    );
  }

  const parts = [
    classification.level_1,
    classification.level_2,
    classification.level_3,
  ].filter(Boolean);

  return (
    <span className="breadcrumb" title={classification.breadcrumb}>
      {parts.map((part, i) => (
        <span key={i}>
          {i > 0 && <span className="breadcrumb__sep">›</span>}
          <span className="breadcrumb__part">{part}</span>
        </span>
      ))}
    </span>
  );
}
