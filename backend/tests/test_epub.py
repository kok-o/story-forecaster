import os
import zipfile
import tempfile
from story_forecaster.ingestion.epub_parser import EpubParser

def test_epub_parser_synthetic():
    container_xml = """<?xml version="1.0"?>
    <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
        <rootfiles>
            <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
        </rootfiles>
    </container>
    """

    content_opf = """<?xml version="1.0" encoding="utf-8"?>
    <package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookID" version="2.0">
        <manifest>
            <item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
            <item id="ch2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
        </manifest>
        <spine>
            <itemref idref="ch1"/>
            <itemref idref="ch2"/>
        </spine>
    </package>
    """

    chapter1_xhtml = """<!DOCTYPE html>
    <html xmlns="http://www.w3.org/1999/xhtml">
    <head><title>Глава 1</title></head>
    <body>
        <h1>Глава 1: Пробуждение в Фудзими</h1>
        <p>Хатиман Хикигая открыл глаза и осознал, что находится в незнакомом школьном классе.</p>
        <p>Система З.Л.А. мерцала алыми символами перед его взором, уведомляя о смене реальности.</p>
    </body>
    </html>
    """

    chapter2_xhtml = """<!DOCTYPE html>
    <html xmlns="http://www.w3.org/1999/xhtml">
    <head><title>Глава 2</title></head>
    <body>
        <h1>Глава 2: Контракт с феей</h1>
        <p>Мэрон нагло потребовала сладостей в обмен на активацию скрытых функций интерфейса.</p>
        <p>Хикигая холодно усмехнулся, прикинув стоимость сушеной феи на черном рынке.</p>
    </body>
    </html>
    """

    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tf:
        epub_path = tf.name

    try:
        with zipfile.ZipFile(epub_path, "w") as z:
            z.writestr("mimetype", "application/epub+zip")
            z.writestr("META-INF/container.xml", container_xml)
            z.writestr("OEBPS/content.opf", content_opf)
            z.writestr("OEBPS/chapter1.xhtml", chapter1_xhtml)
            z.writestr("OEBPS/chapter2.xhtml", chapter2_xhtml)

        parser = EpubParser(epub_path)
        chapters = parser.parse()

        assert len(chapters) == 2
        assert chapters[0]["ordinal"] == 1
        assert "Глава 1: Пробуждение в Фудзими" in chapters[0]["title"]
        assert "Хатиман Хикигая" in chapters[0]["content"]

        assert chapters[1]["ordinal"] == 2
        assert "Глава 2: Контракт с феей" in chapters[1]["title"]
        assert "Мэрон нагло потребовала" in chapters[1]["content"]

    finally:
        if os.path.exists(epub_path):
            os.remove(epub_path)
