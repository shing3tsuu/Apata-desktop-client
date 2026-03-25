from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QScrollArea
)
from PyQt6.QtCore import Qt, QRect, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QFontMetrics, QPixmap


# Заглушка — потом заменишь на данные из БД
STUB_MESSAGES = [
    {"from": "me",       "text": "hey, you there?",                              "time": "12:00", "status": "read"},
    {"from": "contact",  "text": "yeah whats up",                                "time": "12:01", "status": "read"},
    {"from": "me",       "text": "did you get the keys working?",                 "time": "12:02", "status": "read"},
    {"from": "contact",  "text": "almost. ecdsa still throwing errors on my end", "time": "12:03", "status": "read"},
    {"from": "me",       "text": "try regenerating with the new salt, worked for me", "time": "12:04", "status": "read"},
    {"from": "contact",  "text": "oh nice that fixed it",                         "time": "12:05", "status": "read"},
    {"from": "contact",  "text": "also server is back up btw",                    "time": "12:06", "status": "read"},
    {"from": "me",       "text": "finally",                                        "time": "12:07", "status": "sent"},
]


class MessageBubble(QWidget):
    def __init__(
        self,
        text: str,
        is_mine: bool,
        color_primary: str,
        color_inactive: str,
        time: str = "",
        status: str = "",
        parent=None
    ):
        super().__init__(parent)
        self.text = text
        self.is_mine = is_mine
        self.color_primary = color_primary
        self.color_inactive = color_inactive
        self.time = time
        self.status = status

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._font = QFont("Roboto", 11)
        self._meta_font = QFont("Roboto", 8)
        self._padding_x = 18
        self._padding_y = 10
        self._bubble_max_width = 420
        self._tw = 8
        self._meta_h = 20

        fm = QFontMetrics(self._font)
        text_width = min(fm.horizontalAdvance(text), self._bubble_max_width - self._padding_x * 2)
        text_height = fm.boundingRect(
            QRect(0, 0, text_width, 9999),
            Qt.TextFlag.TextWordWrap,
            text
        ).height()

        bubble_h = text_height + self._padding_y * 2 + self._meta_h
        self.setFixedHeight(bubble_h + 20)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self._font)

        fm = QFontMetrics(self._font)
        text_width = min(
            fm.horizontalAdvance(self.text),
            self._bubble_max_width - self._padding_x * 2
        )
        text_height = fm.boundingRect(
            QRect(0, 0, text_width, 9999),
            Qt.TextFlag.TextWordWrap,
            self.text
        ).height()

        bubble_w = text_width + self._padding_x * 2
        bubble_h = text_height + self._padding_y * 2 + self._meta_h
        tw = self._tw
        margin = 16

        if self.is_mine:
            bx = self.width() - bubble_w - margin
        else:
            bx = margin

        by = 4

        path = QPainterPath()
        path.moveTo(bx + tw,            by)
        path.lineTo(bx,                 by + bubble_h / 2)
        path.lineTo(bx + tw,            by + bubble_h)
        path.lineTo(bx + bubble_w - tw, by + bubble_h)
        path.lineTo(bx + bubble_w,      by + bubble_h / 2)
        path.lineTo(bx + bubble_w - tw, by)
        path.closeSubpath()

        fill_color = self.color_primary if self.is_mine else self.color_inactive
        painter.fillPath(path, QColor(fill_color))
        pen = QPen(QColor(fill_color))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)

        if self.is_mine:
            painter.setPen(QColor("#000000"))
        else:
            painter.setPen(QColor("#FFFFFF"))
        painter.setFont(self._font)
        painter.drawText(
            QRect(bx + self._padding_x, by + self._padding_y, text_width, text_height),
            Qt.TextFlag.TextWordWrap,
            self.text
        )

        painter.setFont(self._meta_font)
        meta_y = by + self._padding_y + text_height + 2
        meta_rect = QRect(bx + tw, meta_y, bubble_w - tw * 2, self._meta_h)

        time_color = QColor("#000000" if self.is_mine else "#FFFFFF")
        time_color.setAlphaF(0.75)
        painter.setPen(time_color)
        painter.drawText(
            meta_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"   {self.time}"
        )

        if self.is_mine and self.status:
            if self.status == "read":
                checkmark = "◢︎◢︎︎"
            elif self.status == "sent":
                checkmark = "◢︎"
            elif self.status == "failed":
                checkmark = "✗"
            else:
                checkmark = ""

            if checkmark:
                check_color = QColor("#000000")
                painter.setPen(check_color)
                painter.setFont(QFont("Roboto", 13))
                painter.drawText(
                    meta_rect,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    checkmark
                )

class ImageViewer(QWidget):
    def __init__(self, color_primary: str, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.color_primary = color_primary
        self._pixmap = pixmap

        self.setGeometry(parent.rect())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.raise_()
        self.show()

    def resizeEvent(self, event):
        if self.parent():
            self.setGeometry(self.parent().rect())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 210))

        if self._pixmap.isNull():
            return

        margin = 60
        target = self.rect().adjusted(margin, margin, -margin, -margin)
        scaled = self._pixmap.scaled(
            target.width(), target.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

        font = QFont("Roboto", 10)
        painter.setFont(font)
        painter.setPen(QColor(self.color_primary))
        painter.drawText(
            self.rect().adjusted(0, 0, -16, -12),
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
            "‹ C L I C K  T O  C L O S E ›"
        )

    def mousePressEvent(self, event):
        self.close()
        self.deleteLater()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.deleteLater()


class ImageBubble(QWidget):
    def __init__(
        self,
        path: str,
        is_mine: bool,
        color_primary: str,
        color_inactive: str,
        parent=None
    ):
        super().__init__(parent)
        self.color_primary = color_primary

        self.is_mine = is_mine
        self._margin = 16
        self._max_w = 320
        self._max_h = 240
        self._path = path

        self._pixmap = QPixmap(path)
        if not self._pixmap.isNull():
            self._pixmap = self._pixmap.scaled(
                self._max_w, self._max_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        img_h = self._pixmap.height() if not self._pixmap.isNull() else 100
        self.setFixedHeight(img_h + 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            top = self.window()
            full_pixmap = QPixmap(self._path)
            viewer = ImageViewer(self.color_primary, full_pixmap, top)
            viewer.setFocus()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        if self._pixmap.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        pw = self._pixmap.width()

        if self.is_mine:
            bx = self.width() - pw - self._margin
        else:
            bx = self._margin

        painter.drawPixmap(bx, 4, self._pixmap)


class MessageList(QWidget):
    def __init__(self, color_primary: str, color_inactive: str, parent=None):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_inactive = color_inactive

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 8, 0, 8)
        self._layout.setSpacing(2)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(self._layout)

        for msg in STUB_MESSAGES:
            self.add_message(
                f"‹ {msg['text'].upper()} ›",
                msg["from"] == "me",
                time=msg.get("time", ""),
                status=msg.get("status", "")
            )

    def add_message(self, text: str, is_mine: bool, time: str = "", status: str = ""):
        bubble = MessageBubble(text, is_mine, self.color_primary, self.color_inactive, time, status)
        self._layout.addWidget(bubble)

    def add_image(self, path: str, is_mine: bool):
        bubble = ImageBubble(path, is_mine, self.color_primary, self.color_inactive)
        self._layout.addWidget(bubble)

    def clear_messages(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class MessagesView(QWidget):
    def __init__(self, color_primary: str, color_inactive: str, parent=None):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_inactive = color_inactive

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: #000000; }
            QScrollBar:vertical { background: #000000; width: 4px; }
            QScrollBar::handle:vertical { background: #45464C; border-radius: 2px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        self.message_list = MessageList(self.color_primary, self.color_inactive)
        scroll.setWidget(self.message_list)
        self._scroll = scroll

        layout.addWidget(scroll)
        self.setLayout(layout)

        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())