import tempfile
import unittest
from pathlib import Path

from snapchat_memories_downloader.parser import parse_html_file


class TestParser(unittest.TestCase):
    def test_parses_basic_row_with_single_quotes(self):
        html = """
        <html><body>
          <table><tr>
            <td>2024-01-02 03:04:05 UTC</td>
            <td>Image</td>
            <td>Latitude, Longitude: 12.3, 45.6</td>
            <td><a onclick="downloadMemories('https://example.com/a', 'x')">Download</a></td>
          </tr></table>
        </body></html>
        """
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "memories_history.html"
            html_path.write_text(html, encoding="utf-8")
            memories = parse_html_file(str(html_path))

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["url"], "https://example.com/a")
        self.assertEqual(memories[0]["media_type"], "Image")
        self.assertEqual(memories[0]["latitude"], "12.3")
        self.assertEqual(memories[0]["longitude"], "45.6")

    def test_parses_download_url_with_double_quotes(self):
        html = """
        <html><body>
          <table><tr>
            <td>2024-01-02 03:04:05 UTC</td>
            <td>Video</td>
            <td><a onclick='downloadMemories("https://example.com/b", "x")'>Download</a></td>
          </tr></table>
        </body></html>
        """
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "memories_history.html"
            html_path.write_text(html, encoding="utf-8")
            memories = parse_html_file(str(html_path))

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["url"], "https://example.com/b")
        self.assertEqual(memories[0]["media_type"], "Video")


if __name__ == "__main__":
    unittest.main()
