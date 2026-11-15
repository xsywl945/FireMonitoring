"""生成手册 PDF、软著源程序节选和填表信息。"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    Image,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors

ROOT = Path(__file__).resolve().parents[2]
DROID = Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf")
WQY = ROOT / "apps/server/src/fire_monitoring/assets/wqy-microhei.ttc"
DEJAVU = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
DEJAVU_MONO = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
SOFTWARE = "校园智能火情预警与辅助决策系统 V2.0"
SOURCE_ROOTS = (
    ("apps/server/src", {".py"}),
    ("apps/inference/src", {".py"}),
    ("apps/web/src", {".vue", ".ts", ".css"}),
    ("firmware/esp32_actuator/src", {".cpp", ".h", ".hpp", ".ino"}),
    ("firmware/esp32_panel/src", {".cpp", ".h", ".hpp", ".ino"}),
)
MANUALS = (
    "docs/manuals/部署手册.md",
    "docs/manuals/用户手册.md",
    "docs/manuals/测试报告.md",
    "docs/manuals/系统设计说明.md",
    "docs/copyright/软件说明书.md",
)
FORM = ROOT / "docs/copyright/填表信息.md"
SOURCE_PDF = ROOT / "docs/copyright/源代码节选.pdf"
LINES_PER_PAGE = 50
EXCERPT_PAGES = 60


def _ttfont(name: str, path: Path) -> None:
    if path.suffix.lower() == ".ttc":
        pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=0))
    else:
        pdfmetrics.registerFont(TTFont(name, str(path)))


def register_font() -> tuple[str, str, str]:
    """中文用 Droid Sans Fallback，拉丁字母和数字用 DejaVu。没有 Droid 时整页改用文泉驿微米黑。"""
    if DROID.is_file() and DEJAVU.is_file():
        _ttfont("ManualCjk", DROID)
        _ttfont("ManualLatin", DEJAVU)
        _ttfont("ManualMono", DEJAVU_MONO if DEJAVU_MONO.is_file() else DEJAVU)
        return "ManualCjk", "ManualLatin", "ManualMono"
    if not WQY.is_file():
        raise SystemExit("没有可用的中文字体")
    _ttfont("ManualCjk", WQY)
    return "ManualCjk", "ManualCjk", "ManualCjk"


def source_files() -> list[Path]:
    found: list[Path] = []
    for relative, suffixes in SOURCE_ROOTS:
        base = ROOT / relative
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix.lower() in suffixes:
                found.append(path)
    return found


def source_lines() -> list[str]:
    lines: list[str] = []
    for path in source_files():
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.strip():
                lines.append(line)
    return lines


def excerpt(lines: list[str]) -> list[str]:
    if len(lines) <= LINES_PER_PAGE * EXCERPT_PAGES:
        return lines
    half = LINES_PER_PAGE * (EXCERPT_PAGES // 2)
    return lines[:half] + lines[-half:]


def chunks(lines: list[str]) -> list[list[str]]:
    pages = [lines[index : index + LINES_PER_PAGE] for index in range(0, len(lines), LINES_PER_PAGE)]
    if not pages:
        raise SystemExit("没有源程序行")
    return pages


def _runs(text: str) -> list[tuple[bool, str]]:
    runs: list[tuple[bool, str]] = []
    latin: bool | None = None
    buf: list[str] = []
    for char in text:
        is_latin = ord(char) < 128
        if latin is None:
            latin = is_latin
        elif is_latin != latin:
            runs.append((latin, "".join(buf)))
            buf = []
            latin = is_latin
        buf.append(char)
    if latin is not None:
        runs.append((latin, "".join(buf)))
    return runs


def _draw_mixed(pdf, text: str, x: float, y: float, size: float, cjk: str, latin: str) -> None:
    cursor = x
    for is_latin, run in _runs(text):
        face = latin if is_latin else cjk
        pdf.setFont(face, size)
        pdf.drawString(cursor, y, run)
        cursor += pdf.stringWidth(run, face, size)


def _mixed_width(pdf, text: str, size: float, cjk: str, latin: str) -> float:
    total = 0.0
    for is_latin, run in _runs(text):
        total += pdf.stringWidth(run, latin if is_latin else cjk, size)
    return total


def write_source_pdf(lines: list[str], destination: Path, fonts: tuple[str, str, str]) -> None:
    cjk, latin, _mono = fonts
    pages = chunks(excerpt(lines))
    destination.parent.mkdir(parents=True, exist_ok=True)
    pdf = pdfcanvas.Canvas(str(destination), pagesize=A4)
    width, height = A4
    left = 12 * mm
    right = 12 * mm
    usable = width - left - right
    top = height - 14 * mm
    bottom = 12 * mm
    leading = (top - bottom) / LINES_PER_PAGE
    for number, page in enumerate(pages, start=1):
        _draw_mixed(pdf, SOFTWARE, left, height - 8 * mm, 9, cjk, latin)
        pdf.setFont(latin, 9)
        pdf.drawRightString(width - right, 7 * mm, str(number))
        y = top - leading + 2
        for line in page:
            size = 8.0
            while size > 4 and _mixed_width(pdf, line, size, cjk, latin) > usable:
                size -= 0.25
            _draw_mixed(pdf, line, left, y, size, cjk, latin)
            y -= leading
        pdf.showPage()
    pdf.save()


def form_text(count: int) -> str:
    rule = (
        "统计口径：apps/server/src 与 apps/inference/src 的 .py，"
        "apps/web/src 的 .vue、.ts、.css，"
        "firmware/esp32_actuator/src 与 firmware/esp32_panel/src 的源文件。"
        "去掉空行和只含空白的行，保留注释。不含测试、第三方依赖和构建产物。"
    )
    return f"""# 软件著作权登记填表信息草稿

本页是草稿。申请人、证件、地址、电话和邮箱留空，由申请人填写。

| 项目 | 内容 |
|---|---|
| 软件全称 | 校园智能火情预警与辅助决策系统 |
| 版本号 | V2.0 |
| 软件简称 | （空） |
| 开发完成日期 | 2026-11-16。取 P8 合并提交 1a80bbc 的提交时间（东八区）。P9 是文档和打包，不改变该日期。申请人可按实际完成日修改 |
| 首次发表 | 未发表。发表日期留空。若仓库公开被认定为发表，由申请人改正并填写日期 |
| 开发方式 | 待申请人确认。选项为独立开发、合作开发、委托开发、下达任务开发。提交记录不能代替这项声明 |
| 权利取得方式 | 待申请人确认 |
| 权利范围 | 待申请人确认 |
| 运行环境 | 64 位 Windows 10/11；Python 3.11–3.13；MySQL 8.4；MinIO；MediaMTX；FFmpeg；浏览器。可选 ESP32 执行节点和报警节点 |
| 编程语言 | Python、TypeScript、C++ |
| 源程序量 | {count} 行 |
| 开发的硬件环境 | 待申请人确认 |
| 运行的硬件环境 | 通用 x64 计算机。摄像头和 ESP32 为可选外设 |
| 软件用途 | 校园房间的火情监视、告警研判和灭火联锁辅助。现场出水试验尚未做 |

源程序量：{count} 行（非空行）。{rule}

申请人：

证件号码：

地址：

联系人：

电话：

电子邮箱：
"""


def styles(cjk: str) -> dict[str, ParagraphStyle]:
    return {
        "h1": ParagraphStyle("h1", fontName=cjk, fontSize=16, leading=22, spaceAfter=8),
        "h2": ParagraphStyle("h2", fontName=cjk, fontSize=13, leading=18, spaceBefore=8, spaceAfter=4),
        "h3": ParagraphStyle("h3", fontName=cjk, fontSize=11, leading=15, spaceBefore=6, spaceAfter=3),
        "body": ParagraphStyle("body", fontName=cjk, fontSize=10, leading=15, spaceAfter=4),
        "code": ParagraphStyle("code", fontName=cjk, fontSize=8, leading=11),
        "cell": ParagraphStyle("cell", fontName=cjk, fontSize=8, leading=11),
    }


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(text: str, latin: str, cjk: str, *, preserve_spaces: bool = False) -> str:
    text = escape(text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    if preserve_spaces:
        text = text.replace(" ", "&nbsp;")
    parts: list[str] = []
    for is_latin, run in _runs(text):
        if is_latin and latin != cjk:
            parts.append(f'<font name="{latin}">{run}</font>')
        else:
            parts.append(run)
    return "".join(parts)


def render_markdown(path: Path, destination: Path, fonts: tuple[str, str, str]) -> None:
    cjk, latin, mono = fonts
    sheet = styles(cjk)
    story: list = []
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("```"):
            block: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            coded = "<br/>".join(inline(item, mono, cjk, preserve_spaces=True) for item in block)
            story.append(Paragraph(coded, sheet["code"]))
            story.append(Spacer(1, 2 * mm))
            continue
        image = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", line.strip())
        if image:
            image_path = (path.parent / image.group(2)).resolve()
            if not image_path.is_file():
                raise SystemExit(f"缺少截图：{image_path}")
            flow = Image(str(image_path))
            scale = min(170 * mm / flow.imageWidth, 95 * mm / flow.imageHeight, 1)
            flow.drawWidth = flow.imageWidth * scale
            flow.drawHeight = flow.imageHeight * scale
            story.append(flow)
            story.append(Paragraph(inline(image.group(1), latin, cjk), sheet["body"]))
            index += 1
            continue
        if line.startswith("|"):
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].startswith("|"):
                cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if not all(set(cell) <= set("-: ") for cell in cells):
                    rows.append(cells)
                index += 1
            data = [[Paragraph(inline(cell, latin, cjk), sheet["cell"]) for cell in row] for row in rows]
            table = Table(data, hAlign="LEFT")
            table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), cjk),
                        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#666666")),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 3),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 2 * mm))
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            story.append(Paragraph(inline(line[level:].strip(), latin, cjk), sheet["h1" if level == 1 else "h2" if level == 2 else "h3"]))
            index += 1
            continue
        if line.startswith("- "):
            items = []
            while index < len(lines) and lines[index].startswith("- "):
                items.append(ListItem(Paragraph(inline(lines[index][2:].strip(), latin, cjk), sheet["body"])))
                index += 1
            story.append(ListFlowable(items, bulletType="bullet", start="•", leftIndent=12))
            continue
        paragraph = [line.strip()]
        index += 1
        while (
            index < len(lines)
            and lines[index].strip()
            and not lines[index].startswith(("#", "-", "|", "```", "!"))
            and not re.match(r"\d+\. ", lines[index])
        ):
            paragraph.append(lines[index].strip())
            index += 1
        story.append(Paragraph(inline("".join(paragraph), latin, cjk), sheet["body"]))
    title = path.stem

    def draw(pdf, doc) -> None:
        pdf.setFont(cjk, 8)
        pdf.drawString(18 * mm, A4[1] - 10 * mm, title)
        pdf.drawRightString(A4[0] - 18 * mm, 8 * mm, str(doc.page))

    destination.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(destination),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=14 * mm,
        title=title,
    )
    document.build(story, onFirstPage=draw, onLaterPages=draw)


def page_count(path: Path) -> int:
    return len(PdfReader(str(path)).pages)


def write_all(fonts: tuple[str, str, str]) -> int:
    lines = source_lines()
    FORM.write_text(form_text(len(lines)), encoding="utf-8")
    write_source_pdf(lines, SOURCE_PDF, fonts)
    for relative in (*MANUALS, "docs/copyright/填表信息.md"):
        source = ROOT / relative
        render_markdown(source, source.with_suffix(".pdf"), fonts)
    return len(lines)


def check(fonts: tuple[str, str, str]) -> None:
    count = len(source_lines())
    recorded = FORM.read_text(encoding="utf-8")
    match = re.search(r"源程序量：(\d+) 行", recorded)
    if match is None or int(match.group(1)) != count:
        raise SystemExit(f"填表信息中的源程序量不是 {count}。请重新运行 build_materials.py。")
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        selected = excerpt(source_lines())
        pages = chunks(selected)
        if count > LINES_PER_PAGE * EXCERPT_PAGES:
            if len(pages) != EXCERPT_PAGES or any(len(page) != LINES_PER_PAGE for page in pages):
                raise SystemExit("源程序节选不是 60 页、每页 50 行")
        else:
            if any(len(page) < LINES_PER_PAGE for page in pages[:-1]):
                raise SystemExit("除最后一页外，源程序页不足 50 行")
        sample = folder / "source.pdf"
        write_source_pdf(source_lines(), sample, fonts)
        if page_count(sample) != len(pages):
            raise SystemExit("源程序 PDF 页数与行数不一致")
        form_pdf = folder / "form.pdf"
        render_markdown(FORM, form_pdf, fonts)
        if page_count(form_pdf) != 1:
            raise SystemExit(f"填表信息 PDF 不是 1 页，实际 {page_count(form_pdf)} 页")
        for relative in MANUALS:
            rendered = folder / Path(relative).name
            render_markdown(ROOT / relative, rendered.with_suffix(".pdf"), fonts)
            if page_count(rendered.with_suffix(".pdf")) < 1:
                raise SystemExit(f"手册 PDF 为空：{relative}")
    print(f"材料检查通过。源程序量：{count} 行")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    fonts = register_font()
    if args.check:
        check(fonts)
        return
    count = write_all(fonts)
    form_pages = page_count(FORM.with_suffix(".pdf"))
    source_pages = page_count(SOURCE_PDF)
    if form_pages != 1:
        raise SystemExit(f"填表信息 PDF 不是 1 页，实际 {form_pages} 页")
    print(f"源程序量：{count} 行")
    print(f"源代码节选：{source_pages} 页")
    print(f"字体：{fonts[0]} + {fonts[1]}")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
