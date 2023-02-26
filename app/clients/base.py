from abc import ABC, abstractmethod
from typing import Any, Generator, TypedDict


class InsertMapping(TypedDict):
    """Required data from a client source to save in the database"""

    source_uri: str
    source_id: str
    source_type: str
    image_type: str
    analyzed: bool


class Client(ABC):
    """
    Abstract class for client instances.
    Allows for consistent usage, limiting control and canceling functionality.
    """

    @abstractmethod
    def to_db(self, obj: Any) -> InsertMapping:
        """Subclass this function. Transform data from client to a db friendly dict"""
        return InsertMapping()

    @abstractmethod
    def images(self) -> Generator[Any, None, None]:
        """Subclass this function. Navigate the client service to generate new image entries"""
        for obj in [InsertMapping()]:
            yield obj

    def cancel(self):
        self.cancel = True

    def fetch(self, limit: int) -> Generator[InsertMapping, None, None]:
        """Main entrypoint. Generate new image entries up to a limit or until canceled"""
        count = 0
        self.cancel = False
        for image in self.images():
            if count > limit or self.cancel:
                break
            data = self.to_db(image)
            if data is None:
                continue
            count += 1
            yield data
