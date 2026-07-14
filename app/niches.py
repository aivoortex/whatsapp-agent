import json
from pathlib import Path


class NicheRegistry:
    def __init__(self, directory=Path("niches")):
        self.directory = directory

    def all(self):
        return [self._read(path) for path in sorted(self.directory.glob("*.json"))]

    def get(self, slug):
        path = self.directory / f"{slug}.json"
        return self._read(path) if path.is_file() else None

    @staticmethod
    def _read(path):
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
        return {**data, "slug": path.stem}
