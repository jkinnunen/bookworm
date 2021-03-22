# coding: utf-8

import zipfile
import fitz
import ftfy
from functools import cached_property
from hashlib import md5
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from pathlib import Path
from bookworm.paths import home_data_path
from bookworm.image_io import ImageIO
from bookworm.utils import recursively_iterdir
from bookworm.document_formats.base import (
    BaseDocument,
    BasePage,
    Section,
    BookMetadata,
    Pager,
    DocumentCapability as DC,
    ChangeDocument,
    DocumentError,
    DocumentEncryptedError,
)
from bookworm.logger import logger
from .fitz_document import FitzPage, FitzDocument


log = logger.getChild(__name__)


class FitzEPUBDocument(FitzDocument):

    __internal__ = True
    format = "epub"

    def read(self, filetype=None):
        try:
            super().read(filetype)
        except DocumentEncryptedError:
            log.debug("Got an encrypted file, will try to decrypt it...")
            raise ChangeDocument(
                old_uri=self.uri,
                new_uri=self.uri.create_copy(format="drm_epub"),
                reason="Document is encrypted with DRM",
            )


class _DrmFitzEpubDocument(FitzEPUBDocument):
    """Fixes DRM encrypted epub documents."""

    __internal__ = True
    format = "drm_epub"
    capabilities = FitzDocument.capabilities

    def read(self, filetype=None):
        self._original_filename = self.get_file_system_path()
        try:
            self.filename = self.make_unrestricted_file(self._original_filename)
            self.uri = self.uri.create_copy(
                path=self.filename,
            )
            super().read(filetype="epub")
        except Exception as e:
            raise DocumentError("Could not open DRM encrypted epub document") from e

    def _get_section_text(self, section):
        html_file = section.data["html_file"]
        if html_file is None:
            return ""
        html_file, content_id = html_file.split("#")
        parents = PosixPath(html_file).parts[:-1]
        html_doc = html.document_fromstring(self._book_zip.read(html_file))
        if content_id is not None:
            html_doc = html_doc.get_element_by_id(content_id)

    @staticmethod
    def make_unrestricted_file(filename):
        """Try to remove digital restrictions from the EPUB document."""
        filepath = Path(filename)
        content_hash = md5(filepath.read_bytes()).hexdigest()
        processed_book = home_data_path(content_hash)
        if processed_book.exists():
            return str(processed_book)
        _temp = TemporaryDirectory()
        temp_path = Path(_temp.name)
        ZipFile(filename).extractall(temp_path)
        with ZipFile(processed_book, "w") as book:
            for file in recursively_iterdir(temp_path):
                if "encryption.xml" in file.name.lower():
                    continue
                book.write(file, file.relative_to(temp_path))
        _temp.cleanup()
        return str(processed_book)


class FitzFB2Document(FitzDocument):

    format = "fb2"
    # Translators: the name of a document file format
    name = _("Fiction Book (FB2)")
    extensions = ("*.fb2",)
