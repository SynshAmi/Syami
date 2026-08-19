from abc import ABC, abstractmethod

from syami.domain.document import ProcessedDocument


class DocumentProcessor(ABC):

    @abstractmethod
    def process(
        self,
        document_id: int,
        source_path: str,
    ) -> ProcessedDocument:
        pass