"""ARA document retrieval proof of concept.

Fetch an official Federal Register document and produce a reviewable JSON
artifact. No database writes, applicability determinations, or AI calls.
"""

import json
import re
import sys
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests

API_BASE = "https://www.federalregister.gov/api/v1/documents"
DEFAULT_DOCUMENT = "2026-00449"
MAX_DOCUMENT_BYTES = 5_000_000


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip_depth += 1
        elif not self.skip_depth and tag in {"p", "div", "br", "li", "h1", "h2", "h3", "pre", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag in {"p", "div", "li", "h1", "h2", "h3", "pre", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)

    def text(self):
        return "".join(self.parts)


def clean_text(raw):
    if re.search(r"<\s*(?:html|body|pre|p|div)\b", raw, flags=re.I):
        parser = TextExtractor()
        parser.feed(raw)
        raw = parser.text()
    raw = unescape(raw)
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"[ \t]+", " ", raw)
    return re.sub(r"\n{3,}", "\n\n", raw).strip()


def get_json(session, url):
    response = session.get(url, timeout=(10, 40), headers={"Accept": "application/json"})
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Document API returned an unexpected JSON structure")
    return data


def get_document_text(session, url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"www.federalregister.gov", "federalregister.gov"}:
        raise ValueError("Untrusted full-text URL; expected federalregister.gov HTTPS")
    with session.get(url, timeout=(10, 60), stream=True, allow_redirects=False) as response:
        response.raise_for_status()
        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > MAX_DOCUMENT_BYTES:
                raise ValueError("Document exceeds permitted size")
            chunks.append(chunk)
        encoding = response.encoding or "utf-8"
        return b"".join(chunks).decode(encoding, errors="replace")


def retrieve(document_number):
    if not re.fullmatch(r"\d{4}-\d{4,6}", document_number):
        raise ValueError("Invalid Federal Register document number")
    with requests.Session() as session:
        metadata = get_json(session, f"{API_BASE}/{document_number}.json")
        if metadata.get("document_number") != document_number:
            raise ValueError("Document number mismatch")
        text_url = metadata.get("raw_text_url")
        if not text_url:
            raise ValueError("No raw_text_url available for this document")
        document_text = clean_text(get_document_text(session, text_url))
        if len(document_text) < 200:
            raise ValueError("Retrieved text is unexpectedly short")
        return {
            "document_number": document_number,
            "title": metadata.get("title"),
            "document_type": metadata.get("type"),
            "citation": metadata.get("citation"),
            "publication_date": metadata.get("publication_date"),
            "effective_on": metadata.get("effective_on"),
            "agencies": [a.get("name") for a in metadata.get("agencies", []) if isinstance(a, dict)],
            "official_url": metadata.get("html_url"),
            "raw_text_url": text_url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "full_text": document_text,
            "review_status": "not_assessed",
            "applicability_determined": False,
        }


def main():
    document_number = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DOCUMENT
    result = retrieve(document_number)
    path = Path(f"federal_register_{document_number}.json")
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Retrieved {document_number}; {len(result['full_text'])} characters; saved {path}")
    print(f"Citation: {result['citation']}; effective: {result['effective_on']}")
    print("No database changes or applicability determinations were made.")


if __name__ == "__main__":
    main()
