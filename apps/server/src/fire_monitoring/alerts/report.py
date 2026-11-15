from __future__ import annotations

import csv
import json
from io import BytesIO, StringIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import iso
from ..models import Alert, AlertEvent, AlertFrame, Camera, Disposition, Room

FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "wqy-microhei.ttc"
FONT_NAME = "WenQuanYi"

STATUS_LABELS = {
    "OPEN": "待处置",
    "ACKNOWLEDGED": "已确认",
    "FALSE_ALARM": "误报",
    "CLOSED": "已结案",
}
TYPE_LABELS = {
    "FIRE": "火焰",
    "SMOKE": "烟雾",
    "FIRE_AND_SMOKE": "火焰和烟雾",
}
EVENT_LABELS = {
    "CONFIRMED": "告警生成",
    "LOCALIZED": "完成定位",
    "UNOBSERVABLE": "无法定位",
    "ANALYSIS": "完成研判",
    "SMS": "发送短信",
    "PUMP": "联动水泵",
    "ACKNOWLEDGED": "值班确认",
    "FALSE_ALARM": "标记误报",
    "CLOSED": "结案",
    "CLIP": "保存视频",
}


def build_alerts_csv(session: Session, alerts: list[Alert]) -> bytes:
    rooms = {
        room.id: room.name
        for room in session.scalars(select(Room).where(Room.id.in_({item.room_id for item in alerts})))
    } if alerts else {}
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(["编号", "教室", "类型", "开始时间", "等级", "火灾类别", "处置状态"])
    for alert in alerts:
        writer.writerow(
            [
                alert.id,
                rooms.get(alert.room_id, ""),
                TYPE_LABELS.get(alert.alert_type, alert.alert_type),
                iso(alert.started_at),
                alert.level or "",
                alert.fire_classes or "",
                STATUS_LABELS.get(alert.status, alert.status),
            ]
        )
    return buf.getvalue().encode("utf-8-sig")


def build_alert_pdf(session: Session, evidence, alert: Alert) -> bytes:
    font = _font()
    body = ParagraphStyle("body", fontName=font, fontSize=10.5, leading=16, textColor=colors.HexColor("#1f2933"))
    title = ParagraphStyle("title", fontName=font, fontSize=16, leading=22, spaceAfter=8)
    heading = ParagraphStyle(
        "heading", fontName=font, fontSize=12, leading=18, spaceBefore=8, spaceAfter=6
    )
    room = session.get(Room, alert.room_id)
    room_name = room.name if room is not None else ""
    analysis = json.loads(alert.analysis_json) if alert.analysis_json else None
    position = json.loads(alert.position_json) if alert.position_json else None
    story: list = [
        Paragraph(f"火情告警报告 {alert.id}", title),
        _table(
            font,
            body,
            [
                ("教室", room_name),
                ("类型", TYPE_LABELS.get(alert.alert_type, alert.alert_type)),
                ("开始时间", iso(alert.started_at)),
                ("处置状态", STATUS_LABELS.get(alert.status, alert.status)),
                ("等级", "" if analysis is None else analysis["level"]["grade"]),
                ("火灾类别", "" if alert.fire_classes is None else alert.fire_classes),
            ],
        ),
        Paragraph("关键帧", heading),
    ]
    frames = session.scalars(select(AlertFrame).where(AlertFrame.alert_id == alert.id).order_by(AlertFrame.camera_id)).all()
    images = []
    for frame in frames:
        camera = session.get(Camera, frame.camera_id)
        name = camera.name if camera is not None else str(frame.camera_id)
        data, _content_type = evidence.get(frame.object_key)
        images.append([_picture(data, 78 * mm), Paragraph(xml(name), body)])
    if images:
        row_size = 2
        rows = [images[index : index + row_size] for index in range(0, len(images), row_size)]
        flat = []
        for row in rows:
            while len(row) < row_size:
                row.append("")
            flat.append([item[0] for item in row])
            flat.append([item[1] if item else "" for item in row])
        grid = Table(flat, colWidths=[85 * mm, 85 * mm])
        grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
        story.append(grid)
    else:
        story.append(Paragraph("无关键帧", body))
    story.append(Paragraph("平面图", heading))
    plan = _plan_image(evidence, room, position, analysis)
    if plan is None:
        story.append(Paragraph("未上传平面图", body))
    else:
        story.append(_picture(plan, 160 * mm))
        story.append(Paragraph("红点为火点，红线为当前范围，橙线为 30 秒外推，灰线为 60 秒外推。", body))
    story.append(Paragraph("事件时间轴", heading))
    events = session.scalars(
        select(AlertEvent).where(AlertEvent.alert_id == alert.id).order_by(AlertEvent.occurred_at, AlertEvent.id)
    ).all()
    if not events:
        story.append(Paragraph("无事件", body))
    for event in events:
        detail = json.loads(event.detail_json)
        label = EVENT_LABELS.get(event.kind, event.kind)
        extra = ""
        if detail.get("actor"):
            extra += f" {detail['actor']}"
        if detail.get("note"):
            extra += f" {detail['note']}"
        story.append(Paragraph(xml(f"{iso(event.occurred_at)} {label}{extra}"), body))
    story.append(Paragraph("研判结论", heading))
    story.extend(_conclusion(body, analysis))
    dispositions = session.scalars(
        select(Disposition).where(Disposition.alert_id == alert.id).order_by(Disposition.id)
    ).all()
    if dispositions:
        story.append(Paragraph("处置记录", heading))
        for item in dispositions:
            note = f" {item.note}" if item.note else ""
            story.append(Paragraph(xml(f"{iso(item.occurred_at)} {item.actor} {item.action}{note}"), body))
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"告警{alert.id}",
    )
    doc.build(story)
    return buf.getvalue()


def _conclusion(style: ParagraphStyle, analysis: dict | None) -> list:
    if analysis is None:
        return [Paragraph("未研判", style)]
    evidence = analysis.get("evidence") or {}
    objects = "、".join(item["name"] for item in evidence.get("burning_objects") or []) or "无"
    rules = analysis["rules"]
    classes = "、".join(f"{item['id']} {item['name']}" for item in rules.get("details") or []) or "未定"
    recommended = "、".join(rules.get("recommended") or []) or "无"
    forbidden = "、".join(rules.get("forbidden") or []) or "无"
    reasons = "；".join(analysis["level"]["reasons"])
    lines = [
        f"燃烧物：{objects}",
        f"火灾类别：{classes}",
        f"推荐灭火剂：{recommended}",
        f"禁止灭火剂：{forbidden}",
        f"等级：{analysis['level']['grade']}",
        f"等级原因：{reasons}",
    ]
    return [Paragraph(xml(line), style) for line in lines]


def _plan_image(evidence, room: Room | None, position: dict | None, analysis: dict | None) -> bytes | None:
    if room is None or not room.floor_plan_json:
        return None
    meta = json.loads(room.floor_plan_json)
    data, _content_type = evidence.get(meta["object_key"])
    spread = None if analysis is None else analysis.get("spread")
    return _annotate_plan(data, meta, position, spread)


def _annotate_plan(image_bytes: bytes, meta: dict, position: dict | None, spread: dict | None) -> bytes:
    import cv2
    import numpy as np

    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("平面图无法解码")
    origin = meta["origin_px"]
    world = meta["origin_world_m"]
    scale = meta["meters_per_pixel"]

    def to_px(x: float, y: float) -> tuple[int, int]:
        u = origin[0] + (x - world[0]) / scale
        v = origin[1] - (y - world[1]) / scale
        return int(round(u)), int(round(v))

    if spread and spread.get("status") == "ESTIMATED":
        colors_bgr = {
            "horizon_60s": (180, 180, 180),
            "horizon_30s": (8, 140, 181),
            "now": (32, 45, 159),
        }
        for key, color in colors_bgr.items():
            points = spread.get(key) or []
            if len(points) < 2:
                continue
            poly = np.array([to_px(point[0], point[1]) for point in points], np.int32)
            cv2.polylines(image, [poly], True, color, 2)
    if position and position.get("status") == "ESTIMATED" and position.get("xyz"):
        cv2.circle(image, to_px(position["xyz"][0], position["xyz"][1]), 6, (32, 45, 159), -1)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("平面图编码失败")
    return encoded.tobytes()


def _picture(data: bytes, width: float) -> Image:
    stream = BytesIO(data)
    pixel_w, pixel_h = ImageReader(stream).getSize()
    stream.seek(0)
    return Image(stream, width=width, height=width * pixel_h / pixel_w)


def _table(font: str, style: ParagraphStyle, rows: list[tuple[str, str]]) -> Table:
    table = Table(
        [[Paragraph(xml(label), style), Paragraph(xml(value), style)] for label, value in rows],
        colWidths=[28 * mm, 144 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e6e8eb")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f5f8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _font() -> str:
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_PATH), subfontIndex=0))
    return FONT_NAME


def xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
