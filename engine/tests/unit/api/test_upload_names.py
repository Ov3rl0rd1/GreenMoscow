import base64
import io
import zipfile
from pathlib import Path

import pytest

from greenplan.api.upload_names import upload_file_name
from greenplan.api.upload_storage import UploadStorage

CYRILLIC_NAME = "Багрицкого ГП и ПБ.zip"


def encoded_word(text: str) -> str:
    return f"=?utf-8?B?{base64.b64encode(text.encode('utf-8')).decode('ascii')}?="


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (CYRILLIC_NAME, CYRILLIC_NAME),
        (encoded_word(CYRILLIC_NAME), CYRILLIC_NAME),
        ("=?utf-8?Q?=D0=93=D0=9F.zip?=", "ГП.zip"),
        ("C:\\fakepath\\Объект 5\\план.dxf", "план.dxf"),
        ("объект/подоснова 1.dwg", "подоснова 1.dwg"),
        ("  plan.dxf ", "plan.dxf"),
        ("=?broken", "=?broken"),
    ],
)
def test_upload_names_are_decoded_to_the_plain_file_name(raw: str, expected: str) -> None:
    assert upload_file_name(raw) == expected


class DosZipInfo(zipfile.ZipInfo):
    def _encodeFilenameFlags(self):
        return self.filename.encode("cp866"), self.flag_bits


def dos_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(DosZipInfo(name), content)
    return buffer.getvalue()


def test_archive_with_dos_encoded_names_and_spaces_is_extracted(tmp_path: Path) -> None:
    archive = dos_zip({"Объект 5/ГП и ПБ ул Багрицкого.dxf": b"0\nEOF\n", "Объект 5/readme.txt": b""})
    drawings = UploadStorage().store(tmp_path, "Объект 5 (копия).zip", archive)
    assert [path.relative_to(tmp_path).as_posix() for path in drawings] == [
        "Объект 5/ГП и ПБ ул Багрицкого.dxf"
    ]
