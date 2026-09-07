import UploadArea from "./UploadArea.jsx";
import BatchUploadArea from "./BatchUploadArea.jsx";

export default function ImportPage({ onOpenTasks }) {
  return (
    <div className="import-page">
      {/* Page header */}
      <header className="import-page__header">
        <div className="import-page__header-inner">
          <div>
            <h1 className="import-page__title">Document Import</h1>
            <p className="import-page__subtitle">
              Upload documents. AI automatically classifies them for knowledge base import.
            </p>
          </div>
          <div className="import-page__legend">
            <span className="badge badge--pending">Pending</span>
            <span className="badge badge--imported">Imported</span>
            <span className="badge badge--unknown">Unclassified</span>
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="import-page__body">
        <BatchUploadArea onOpenTasks={onOpenTasks} />
        <UploadArea />
      </div>
    </div>
  );
}
