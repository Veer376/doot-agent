from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, ForwardRef

from pydantic import BaseModel

# Forward reference to avoid circular imports
if TYPE_CHECKING:
    from ..types import BoundingBox


@dataclass
class HashedDomElement:
    """
    Hash of the dom element to be used as a unique identifier
    """

    branch_path_hash: str
    attributes_hash: str
    xpath_hash: str
    # text_hash: str


# These classes have been replaced by the BoundingBox class


@dataclass
class DOMHistoryElement:
    tag_name: str
    xpath: str
    highlight_index: int | None
    entire_parent_branch_path: list[str]
    attributes: dict[str, str]
    shadow_root: bool = False
    css_selector: Optional[str] = None
    bbox: Optional['BoundingBox'] = None  # Forward reference to BoundingBox

    def to_dict(self) -> dict:
        bb_data = self.bbox.to_dict() if self.bbox else None

        return {
            "tag_name": self.tag_name,
            "xpath": self.xpath,
            "highlight_index": self.highlight_index,
            "entire_parent_branch_path": self.entire_parent_branch_path,
            "attributes": self.attributes,
            "shadow_root": self.shadow_root,
            "css_selector": self.css_selector,
            "bounding_box": bb_data,
        }
