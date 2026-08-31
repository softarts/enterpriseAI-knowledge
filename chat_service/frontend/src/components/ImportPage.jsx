import UploadArea from "./UploadArea.jsx";

export default function ImportPage() {
  return (
    <div className="import-page">
      {/* Page header */}
      <header className="import-page__header">
        <div className="import-page__header-inner">
          <div>
            <h1 className="import-page__title">文档导入</h1>
            <p className="import-page__subtitle">
              上传文档，AI 自动识别分类，确认后写入知识库
            </p>
          </div>
          <div className="import-page__legend">
            <span className="badge badge--pending">待确认</span>
            <span className="badge badge--imported">已导入</span>
            <span className="badge badge--unknown">未分类</span>
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="import-page__body">
        <UploadArea />
      </div>
    </div>
  );
}
