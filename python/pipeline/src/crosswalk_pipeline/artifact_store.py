from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import PATHS


class ArtifactStore(Protocol):
    def write_crop(self, candidate_id: str, data: bytes) -> str:
        ...

    def write_thumbnail(self, candidate_id: str, data: bytes) -> str:
        ...

    def write_export(self, file_name: str, data: bytes) -> None:
        ...


@dataclass
class LocalArtifactStore:
    export_dir: Path = PATHS.export_dir
    web_images_dir: Path = PATHS.web_images_dir
    web_data_dir: Path = PATHS.web_data_dir

    def write_crop(self, candidate_id: str, data: bytes, *, ext: str = "png") -> str:
        file_name = f"{candidate_id}.{ext.lstrip('.')}"
        self._write_bytes(self.export_dir / "images" / file_name, data)
        self._write_bytes(self.web_images_dir / file_name, data)
        return f"/images/{file_name}"

    def write_thumbnail(self, candidate_id: str, data: bytes, *, ext: str = "png") -> str:
        file_name = f"{candidate_id}-thumb.{ext.lstrip('.')}"
        self._write_bytes(self.export_dir / "images" / file_name, data)
        self._write_bytes(self.web_images_dir / file_name, data)
        return f"/images/{file_name}"

    def write_export(self, file_name: str, data: bytes) -> None:
        self._write_bytes(self.export_dir / file_name, data)
        self._write_bytes(self.web_data_dir / file_name, data)

    @staticmethod
    def _write_bytes(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
