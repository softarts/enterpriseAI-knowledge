"""Abstract repository protocol for document access."""

from typing import List, Optional, Protocol

from doc_service.domain.document import DocumentRecord


class DocumentRepository(Protocol):
    """
    Protocol defining the contract for document repositories.

    Current implementation: OKFDocumentRepository (reads OKF files)
    Future implementations: DatabaseDocumentRepository, MilvusDocumentRepository
    """

    def list_documents(
        self,
        keyword: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[DocumentRecord]:
        """
        List documents, optionally filtered by keyword or tag.

        Args:
            keyword: Filter documents whose title contains this keyword.
            tag: Filter documents that have this tag.

        Returns:
            List of DocumentRecord matching the filters.
        """
        ...

    def get_document(self, document_id: str) -> Optional[DocumentRecord]:
        """
        Get a single document by its stable ID.

        Args:
            document_id: The deterministic document identifier.

        Returns:
            DocumentRecord if found, None otherwise.
        """
        ...
