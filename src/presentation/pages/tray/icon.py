"""Create the APATA application and system-tray icon."""

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap


def create_apata_icon(size: int = 64) -> QIcon:
    scale = size / 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    font = QFont("Roboto Condensed")
    font.setPixelSize(round(56 * scale))
    font.setWeight(QFont.Weight.Medium)

    symbol = QPainterPath()
    symbol.addText(QPointF(0, 0), font, "Ʌ")
    bounds = symbol.boundingRect()
    symbol.translate(
        (size - bounds.width()) / 2 - bounds.left(),
        (size - bounds.height()) / 2 - bounds.top(),
    )

    outline = QPen(QColor("#18181B"), max(1.5, 2.5 * scale))
    outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(outline)
    painter.setBrush(QColor("#E31319"))
    painter.drawPath(symbol)
    painter.end()
    return QIcon(pixmap)
