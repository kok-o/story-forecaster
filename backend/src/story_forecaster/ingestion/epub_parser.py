import os
import zipfile
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from html.parser import HTMLParser

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lines = []
        self._current_tag = None

    def handle_starttag(self, tag, attrs):
        self._current_tag = tag.lower()
        if tag.lower() in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br', 'li'):
            self.lines.append("\n")

    def handle_data(self, data):
        cleaned = data.strip()
        if cleaned:
            self.lines.append(data)

    def get_text(self) -> str:
        raw = "".join(self.lines)
        return re.sub(r'\n{3,}', '\n\n', raw).strip()

class EpubParser:
    """Zero-dependency EPUB parser using standard library zipfile and xml.etree."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"EPUB file not found: {filepath}")

    def parse(self) -> List[Dict[str, Any]]:
        """Parses EPUB and returns an ordered list of chapters with title and content."""
        chapters = []
        with zipfile.ZipFile(self.filepath, 'r') as z:
            # 1. Locate rootfile in container.xml
            container_xml = z.read("META-INF/container.xml")
            root = ET.fromstring(container_xml)
            rootfile_elem = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
            if rootfile_elem is None:
                raise ValueError("Invalid EPUB: container.xml missing rootfile element")

            opf_path = rootfile_elem.attrib.get("full-path", "")
            opf_dir = os.path.dirname(opf_path)
            opf_content = z.read(opf_path)
            opf_root = ET.fromstring(opf_content)

            # Namespace handling
            ns = {
                'opf': 'http://www.idpf.org/2007/opf',
                'dc': 'http://purl.org/dc/elements/1.1/'
            }

            # 2. Extract manifest items
            manifest = {}
            for item in opf_root.findall(".//opf:manifest/opf:item", ns) or opf_root.findall(".//{http://www.idpf.org/2007/opf}item"):
                item_id = item.attrib.get("id")
                href = item.attrib.get("href")
                mtype = item.attrib.get("media-type")
                if item_id and href:
                    manifest[item_id] = {
                        "href": os.path.normpath(os.path.join(opf_dir, href)).replace("\\", "/"),
                        "media_type": mtype
                    }

            # 3. Read spine order
            spine_ids = []
            for itemref in opf_root.findall(".//opf:spine/opf:itemref", ns) or opf_root.findall(".//{http://www.idpf.org/2007/opf}itemref"):
                idref = itemref.attrib.get("idref")
                if idref:
                    spine_ids.append(idref)

            # 4. Extract HTML/XHTML content in spine order
            ordinal = 1
            for sid in spine_ids:
                if sid not in manifest:
                    continue
                file_info = manifest[sid]
                path_in_zip = file_info["href"]
                if path_in_zip not in z.namelist():
                    continue

                raw_bytes = z.read(path_in_zip)
                try:
                    html_str = raw_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    html_str = raw_bytes.decode('cp1251', errors='replace')

                parser = TextExtractor()
                parser.feed(html_str)
                text = parser.get_text()

                if len(text.strip()) > 100:  # Skip tiny front-matter/blank pages
                    # Extract title from first line or h1
                    title_match = re.search(r'<h[1-2][^>]*>(.*?)</h[1-2]>', html_str, re.IGNORECASE | re.DOTALL)
                    if title_match:
                        title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
                    else:
                        title = f"Глава {ordinal}"

                    chapters.append({
                        "ordinal": ordinal,
                        "title": title,
                        "content": text,
                        "char_count": len(text)
                    })
                    ordinal += 1

        return chapters
