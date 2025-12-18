from __future__ import annotations

import io
from datetime import datetime

from .deps import Image, piexif


def decimal_to_dms(decimal: float) -> tuple:
    decimal = abs(decimal)
    degrees = int(decimal)
    minutes_decimal = (decimal - degrees) * 60
    minutes = int(minutes_decimal)
    seconds = (minutes_decimal - minutes) * 60
    return ((degrees, 1), (minutes, 1), (int(seconds * 100), 100))


def add_exif_metadata(
    image_data: bytes,
    date_str: str,
    latitude: str,
    longitude: str,
) -> bytes:
    if piexif is None or Image is None:
        return image_data

    try:
        lat = float(latitude) if latitude != "Unknown" else None
        lon = float(longitude) if longitude != "Unknown" else None

        img = Image.open(io.BytesIO(image_data))
        original_format = img.format

        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}}

        if date_str and date_str != "Unknown":
            date_clean = date_str.replace(" UTC", "")
            try:
                dt = datetime.strptime(date_clean, "%Y-%m-%d %H:%M:%S")
                exif_date = dt.strftime("%Y:%m:%d %H:%M:%S")
                exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = exif_date.encode()
                exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = exif_date.encode()
                exif_dict["0th"][piexif.ImageIFD.DateTime] = exif_date.encode()
            except ValueError:
                pass

        if lat is not None and lon is not None:
            lat_dms = decimal_to_dms(lat)
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = lat_dms
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b"N" if lat >= 0 else b"S"

            lon_dms = decimal_to_dms(lon)
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = lon_dms
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b"E" if lon >= 0 else b"W"

        exif_bytes = piexif.dump(exif_dict)
        output = io.BytesIO()

        if original_format in ["JPEG", "JPG"]:
            if img.mode == "RGBA":
                img = img.convert("RGB")
            img.save(output, format="JPEG", quality=95, exif=exif_bytes)
        elif original_format == "PNG":
            try:
                img.save(output, format="PNG", exif=exif_bytes)
            except Exception:
                img.save(output, format="PNG")
        elif original_format == "WEBP":
            img.save(output, format="WEBP", quality=95, exif=exif_bytes)
        else:
            return image_data

        return output.getvalue()

    except Exception as e:
        print(f"    Warning: Could not add EXIF metadata: {e}")
        return image_data

