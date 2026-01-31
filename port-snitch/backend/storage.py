"""JSON file storage for port-snitch data."""

import json
from pathlib import Path

from .models import Label, PortEntry, Snapshot


class LocalStorage:
    """Persists labels and snapshots to ~/.port-snitch/ as JSON files."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path.home() / ".port-snitch"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._labels_file = self.base_dir / "labels.json"
        self._snapshots_dir = self.base_dir / "snapshots"
        self._snapshots_dir.mkdir(exist_ok=True)

    def save_labels(self, labels: dict[int, Label]) -> None:
        """Save port-to-label mappings."""
        data = {str(port): label.model_dump() for port, label in labels.items()}
        self._labels_file.write_text(json.dumps(data, indent=2))

    def load_labels(self) -> dict[int, Label]:
        """Load port-to-label mappings."""
        if not self._labels_file.exists():
            return {}
        data = json.loads(self._labels_file.read_text())
        return {int(port): Label(**label) for port, label in data.items()}

    def save_snapshot(self, snapshot: Snapshot) -> None:
        """Save a snapshot to disk."""
        path = self._snapshots_dir / f"{snapshot.name}.json"
        path.write_text(snapshot.model_dump_json(indent=2))

    def load_snapshot(self, name: str) -> Snapshot | None:
        """Load a snapshot by name."""
        path = self._snapshots_dir / f"{name}.json"
        if not path.exists():
            return None
        return Snapshot.model_validate_json(path.read_text())

    def list_snapshots(self) -> list[str]:
        """List all snapshot names."""
        return [p.stem for p in self._snapshots_dir.glob("*.json")]

    def diff_snapshots(
        self, old_name: str, new_name: str
    ) -> dict[str, list[PortEntry]] | None:
        """Compare two snapshots, returning added/removed/changed entries."""
        old = self.load_snapshot(old_name)
        new = self.load_snapshot(new_name)
        if old is None or new is None:
            return None

        old_by_port = {e.port: e for e in old.entries}
        new_by_port = {e.port: e for e in new.entries}

        old_ports = set(old_by_port.keys())
        new_ports = set(new_by_port.keys())

        added = [new_by_port[p] for p in new_ports - old_ports]
        removed = [old_by_port[p] for p in old_ports - new_ports]
        changed = [
            new_by_port[p]
            for p in old_ports & new_ports
            if old_by_port[p] != new_by_port[p]
        ]

        return {"added": added, "removed": removed, "changed": changed}
