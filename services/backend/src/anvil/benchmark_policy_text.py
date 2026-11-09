"""Bounded document extraction child; original bytes remain authoritative."""

import io
import json
import sys
import zipfile
from xml.etree import ElementTree


def extract(media, raw):
    if media == "application/pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted or len(reader.pages) > 100:
            raise ValueError("Unsupported PDF")
        text = "\n".join((p.extract_text() or "")[:10000] for p in reader.pages)
    else:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if any("vbaproject" in n.casefold() for n in archive.namelist()):
                raise ValueError("Macros unsupported")
            if archive.getinfo("word/document.xml").file_size > 2 * 1024 * 1024:
                raise ValueError("Document too large")
            xml = archive.read("word/document.xml")
            if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                raise ValueError("Entities unsupported")
            tree = ElementTree.fromstring(xml)
            text = " ".join(n.text or "" for n in tree.iter() if n.tag.endswith("}t"))
    if len(text) > 100000 or "\x00" in text:
        raise ValueError("Text exceeds bounds")
    return text


if __name__ == "__main__":
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    raw = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("Source too large")
    print(json.dumps({"text": extract(sys.argv[1], raw)}))
