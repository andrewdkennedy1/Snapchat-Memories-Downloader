import json
import tempfile
import unittest
from pathlib import Path

from snapchat_memories_downloader.metadata_store import initialize_metadata


class TestMetadataStore(unittest.TestCase):
    def test_rebuilds_and_preserves_progress_by_url(self):
        memories = [
            {"url": "https://example.com/1", "date": "2024-01-01 00:00:00 UTC", "media_type": "Image"},
            {"url": "https://example.com/2", "date": "2024-01-02 00:00:00 UTC", "media_type": "Video"},
            {"url": "https://example.com/3", "date": "2024-01-03 00:00:00 UTC", "media_type": "Image"},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "metadata.json").write_text(
                json.dumps(
                    [
                        {
                            "number": 1,
                            "date": memories[0]["date"],
                            "media_type": memories[0]["media_type"],
                            "latitude": "Unknown",
                            "longitude": "Unknown",
                            "url": memories[0]["url"],
                            "status": "success",
                            "files": [{"path": "existing.jpg", "size": 123, "type": "single"}],
                        }
                    ],
                    indent=2,
                ),
                encoding="utf-8",
            )

            merged = initialize_metadata(memories, out)

            self.assertEqual(len(merged), 3)
            self.assertEqual(merged[0]["url"], memories[0]["url"])
            self.assertEqual(merged[0]["status"], "success")
            self.assertTrue(merged[0]["files"])
            self.assertEqual(merged[1]["status"], "pending")

            on_disk = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(len(on_disk), 3)

    def test_rebuilds_unknown_format(self):
        memories = [{"url": "https://example.com/1", "date": "2024-01-01 00:00:00 UTC", "media_type": "Image"}]

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "metadata.json").write_text(json.dumps({"memories": []}), encoding="utf-8")
            merged = initialize_metadata(memories, out)
            self.assertEqual(len(merged), 1)
            self.assertEqual(merged[0]["url"], memories[0]["url"])

    def test_corrupt_metadata_is_backed_up_and_rebuilt(self):
        memories = [
            {"url": "https://example.com/1", "date": "2024-01-01 00:00:00 UTC", "media_type": "Image"}
        ]

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "metadata.json").write_text('{"bad_json": [1,2,}', encoding="utf-8")
            merged = initialize_metadata(memories, out)
            self.assertEqual(len(merged), 1)
            backups = list(out.glob("metadata.corrupt-*.json"))
            self.assertTrue(backups, "Expected a metadata.json corrupt backup file")
            rebuilt = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(len(rebuilt), 1)


if __name__ == "__main__":
    unittest.main()
