# src/modules/misc/simple_docx.py
"""Write a simple Word (.docx) document -- headings, paragraphs and a
table -- without any extra library.

A .docx file is a ZIP archive of a few XML files (Office Open XML). Writing
the handful needed for plain text and one table directly keeps the
installer free of a new dependency (python-docx would also need its
template files bundled by PyInstaller). Word, LibreOffice and Google Docs
open the result normally.

blocks: list of
    ('heading', text, level)          level 1 or 2
    ('paragraph', text)
    ('table', header_cells, rows[, widths])
                                      rows: list of lists of str; widths:
                                      optional relative column widths
"""

import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape

_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

_STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{_W}">
<w:docDefaults>
<w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri" w:eastAsia="Calibri"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="en-GB"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="200" w:after="80"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:style>
<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/><w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>
</w:styles>"""


def _run(text: str, bold: bool = False, size_half_points: int = 0) -> str:
    props = ''
    if bold or size_half_points:
        props = '<w:rPr>' + ('<w:b/>' if bold else '') + (
            f'<w:sz w:val="{size_half_points}"/><w:szCs w:val="{size_half_points}"/>'
            if size_half_points else '') + '</w:rPr>'
    # Line breaks inside one paragraph -> <w:br/>
    parts = str(text).split('\n')
    inner = '<w:br/>'.join(f'<w:t xml:space="preserve">{escape(p)}</w:t>' for p in parts)
    return f'<w:r>{props}{inner}</w:r>'


def _paragraph(text: str, style: str = '', bold: bool = False, size: int = 0, spacing_after=None) -> str:
    ppr = ''
    if style or spacing_after is not None:
        ppr = '<w:pPr>' + (f'<w:pStyle w:val="{style}"/>' if style else '') + (
            f'<w:spacing w:after="{spacing_after}"/>' if spacing_after is not None else '') + '</w:pPr>'
    return f'<w:p>{ppr}{_run(text, bold, size)}</w:p>'


_TEXT_WIDTH = 9070       # twips between the margins of an A4 page (below)


def _table(header, rows, widths=None) -> str:
    border = '<w:{0} w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
    borders = ''.join(border.format(side) for side in
                      ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))
    weights = list(widths) if widths and len(widths) == len(header) else [1] * len(header)
    cols = [int(_TEXT_WIDTH * w / sum(weights)) for w in weights]
    out = [f'<w:tbl><w:tblPr><w:tblW w:w="{sum(cols)}" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
           f'<w:tblBorders>{borders}</w:tblBorders>'
           '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" '
           'w:noHBand="0" w:noVBand="1"/></w:tblPr><w:tblGrid>']
    out += [f'<w:gridCol w:w="{w}"/>' for w in cols]
    out.append('</w:tblGrid>')

    def row(cells, is_header=False):
        tr = ['<w:tr>' + ('<w:trPr><w:tblHeader/></w:trPr>' if is_header else '')]
        for c, width in zip(cells, cols):
            shade = '<w:shd w:val="clear" w:color="auto" w:fill="E7E7E7"/>' if is_header else ''
            tr.append(f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shade}</w:tcPr>'
                      f'{_paragraph(c, bold=is_header, size=18, spacing_after=0)}</w:tc>')
        tr.append('</w:tr>')
        return ''.join(tr)

    out.append(row(header, True))
    for r in rows:
        cells = list(r) + [''] * (len(header) - len(r))
        out.append(row(cells[:len(header)]))
    out.append('</w:tbl>')
    return ''.join(out)


def document_xml(blocks) -> str:
    body = []
    for block in blocks:
        kind = block[0]
        if kind == 'heading':
            body.append(_paragraph(block[1], style='Heading1' if block[2] <= 1 else 'Heading2'))
        elif kind == 'paragraph':
            body.append(_paragraph(block[1]))
        elif kind == 'table':
            body.append(_table(block[1], block[2], block[3] if len(block) > 3 else None))
            body.append('<w:p/>')            # Word needs a paragraph after a table
        else:
            raise ValueError(f"unknown block type {kind!r}")
    sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1418" w:right="1418" w:bottom="1418" w:left="1418" '
            'w:header="709" w:footer="709" w:gutter="0"/></w:sectPr>')
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<w:document xmlns:w="{_W}"><w:body>{"".join(body)}{sect}</w:body></w:document>')


def _core_xml(title: str) -> str:
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{escape(title)}</dc:title><dc:creator>SpecAnalytiXBase</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
            '</cp:coreProperties>')


def write_docx(path: str, blocks, title: str = '') -> None:
    """Write *blocks* (see module docstring) to *path* as a .docx file."""
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', _CONTENT_TYPES)
        z.writestr('_rels/.rels', _ROOT_RELS)
        z.writestr('word/_rels/document.xml.rels', _DOC_RELS)
        z.writestr('word/styles.xml', _STYLES)
        z.writestr('word/document.xml', document_xml(blocks))
        z.writestr('docProps/core.xml', _core_xml(title))
