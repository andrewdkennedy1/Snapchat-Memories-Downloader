import unittest

from snapchat_memories_downloader.magic_bytes import detect_file_kind, extension_for_kind


class TestMagicBytes(unittest.TestCase):
    def test_detect_zip(self):
        self.assertEqual(detect_file_kind(b"PK\x03\x04rest"), "zip")

    def test_detect_jpeg(self):
        self.assertEqual(detect_file_kind(b"\xff\xd8\xff\xe0rest"), "jpeg")

    def test_detect_png(self):
        self.assertEqual(detect_file_kind(b"\x89PNG\r\n\x1a\nrest"), "png")

    def test_detect_webp(self):
        self.assertEqual(detect_file_kind(b"RIFFxxxxWEBPrest"), "webp")

    def test_detect_mp4_ftyp(self):
        # size(4) + ftyp(4) + brand(4) + minor(4)
        data = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"
        self.assertEqual(detect_file_kind(data), "mp4")

    def test_extension_mapping(self):
        self.assertEqual(extension_for_kind("jpeg", ".bin"), ".jpg")
        self.assertEqual(extension_for_kind("unknown", ".bin"), ".bin")


if __name__ == "__main__":
    unittest.main()

