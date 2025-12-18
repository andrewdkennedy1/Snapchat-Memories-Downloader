import unittest

from snapchat_memories_downloader.files import generate_filename


class TestFiles(unittest.TestCase):
    def test_generate_filename_timestamp_is_windows_safe(self):
        filename = generate_filename(
            "2024-11-30 14:30:45 UTC",
            ".mp4",
            use_timestamp=True,
            fallback_num="01",
        )
        self.assertEqual(filename, "2024.11.30-14.30.45.mp4")
        for ch in '<>:"/\\\\|?*':
            self.assertNotIn(ch, filename)

    def test_generate_filename_timestamp_invalid_date_falls_back(self):
        filename = generate_filename("not a date", ".jpg", use_timestamp=True, fallback_num="01")
        self.assertEqual(filename, "01.jpg")


if __name__ == "__main__":
    unittest.main()

