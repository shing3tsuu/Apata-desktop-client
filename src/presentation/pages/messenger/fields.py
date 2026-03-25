import os
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QSizePolicy, QLineEdit
)
from PyQt6.QtCore import Qt, QTimer, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QPixmap

from .buttons import SendButton, AttachButton


class AttachPreview(QWidget):
    removed = pyqtSignal()

    def __init__(self, path: str, color_primary: str, color_border: str, color_fourth: str, parent=None):
        super().__init__(parent)
        self.path = path
        self.color_primary = color_primary
        self.color_border = color_border
        self.color_fourth = color_fourth

        self._thumb_size = 200
        self._is_image = path.lower().endswith(
            ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
        )

        if self._is_image:
            self._pixmap = QPixmap(path).scaled(
                self._thumb_size, self._thumb_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        else:
            self._pixmap = None

        self._filename = os.path.basename(path)
        # if len(self._filename) > 14:
        #     self._filename = self._filename[:12] + "..."

        self.setFixedSize(230, 160)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        tw = 0
        bg_path = QPainterPath()
        bg_path.moveTo(tw, 0)
        bg_path.lineTo(0, self.height() / 2)
        bg_path.lineTo(tw, self.height())
        bg_path.lineTo(self.width() - tw, self.height())
        bg_path.lineTo(self.width(), self.height() / 2)
        bg_path.lineTo(self.width() - tw, 0)
        bg_path.closeSubpath()

        painter.fillPath(bg_path, QColor("#0a0a0a"))
        pen = QPen(QColor(self.color_border))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(bg_path)

        if self._is_image and self._pixmap and not self._pixmap.isNull():
            pw = self._pixmap.width()
            ph = self._pixmap.height()
            px = (self.width() - pw) // 2
            py = 8
            painter.drawPixmap(px, py, self._pixmap)
        else:
            # Иконка файла
            font_icon = QFont("Roboto", 28)
            painter.setFont(font_icon)
            painter.setPen(QColor(self.color_border))
            painter.drawText(
                QRect(0, 8, self.width(), self._thumb_size),
                Qt.AlignmentFlag.AlignCenter,
                "⎙"
            )

        font_name = QFont("Roboto", 8)
        painter.setFont(font_name)
        painter.setPen(QColor(self.color_primary))
        painter.drawText(
            QRect(6, self.height() - 26, self.width() - 12, 20),
            Qt.AlignmentFlag.AlignCenter,
            self._filename
        )

        font_x = QFont("Roboto", 9)
        painter.setFont(font_x)
        painter.setPen(QColor(self.color_primary))
        painter.drawText(
            QRect(self.width() - 22, 4, 16, 16),
            Qt.AlignmentFlag.AlignCenter,
            "✕"
        )

    def mousePressEvent(self, event):
        # Клик на зону ✕ — удалить прикреплённый файл
        if event.pos().x() > self.width() - 24 and event.pos().y() < 20:
            self.removed.emit()
            self.hide()
            self.deleteLater()
        super().mousePressEvent(event)


class MessageInputField(QLineEdit):
    def __init__(
        self, color_primary: str, color_border: str, color_fourth: str, parent=None
    ):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_border = color_border
        self.current_border_color = color_border
        self.color_fourth = color_fourth
        self.is_focused = False

        self.setPlaceholderText("")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: transparent; border: none; color: #ffffff;")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

        font = QFont("Roboto", 11)
        self.setFont(font)

    def focusInEvent(self, event):
        self.is_focused = True
        self._animate_border(self.color_primary)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.is_focused = False
        self._animate_border(self.color_border)
        super().focusOutEvent(event)

    def _animate_border(self, target: str):
        self._anim_start = QColor(self.color_fourth)
        self._anim_end = QColor(target)
        self._anim_step = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick_border)
        self._timer.start(30)

    def _tick_border(self):
        if self._anim_step >= 20:
            self._timer.stop()
            return
        ratio = self._anim_step / 20
        r = int(self._anim_start.red()   + (self._anim_end.red()   - self._anim_start.red())   * ratio)
        g = int(self._anim_start.green() + (self._anim_end.green() - self._anim_start.green()) * ratio)
        b = int(self._anim_start.blue()  + (self._anim_end.blue()  - self._anim_start.blue())  * ratio)
        self.current_border_color = QColor(r, g, b).name()
        self.update()
        self._anim_step += 1

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        tw = 8
        path = QPainterPath()
        path.moveTo(tw, 0)
        path.lineTo(0, self.height() / 2)
        path.lineTo(tw, self.height())
        path.lineTo(self.width() - tw, self.height())
        path.lineTo(self.width(), self.height() / 2)
        path.lineTo(self.width() - tw, 0)
        path.closeSubpath()

        painter.fillPath(path, QColor("#000000"))

        pen = QPen(QColor(self.current_border_color))
        pen.setWidth(2 if self.is_focused else 1)
        painter.setPen(pen)
        painter.drawPath(path)

        painter.end()
        super().paintEvent(event)


class MessageField(QWidget):
    message_sent = pyqtSignal(str)
    file_sent = pyqtSignal(str)

    def __init__(self, color_primary: str, color_border: str, color_fourth: str = "#6115ff", parent=None):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_border = color_border
        self.color_fourth = color_fourth
        self.attached_file = None
        self._preview = None

        self.setFixedHeight(50)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(200, 8, 200, 6)
        layout.setSpacing(8)

        self.attach_button = AttachButton(self.color_primary, self.color_border)
        self.attach_button.file_selected.connect(self._on_file_selected)
        layout.addWidget(self.attach_button)

        self.input_field = MessageInputField(self.color_primary, self.color_border, self.color_fourth)
        self.input_field.returnPressed.connect(self._on_send)
        layout.addWidget(self.input_field, stretch=1)

        self.send_button = SendButton(self.color_primary, "#000000")
        self.send_button.mousePressEvent = self._send_button_pressed
        layout.addWidget(self.send_button)

        self.setLayout(layout)

    def _on_file_selected(self, path: str):
        self.attached_file = path

        # Удаляем старое превью если есть
        if self._preview:
            self._preview.hide()
            self._preview.deleteLater()

        # Создаём превью как дочерний виджет родителя (панели)
        parent_widget = self.parent() or self
        self._preview = AttachPreview(path, self.color_primary, self.color_border, self.color_fourth, parent_widget)
        self._preview.removed.connect(self._on_preview_removed)
        self._reposition_preview()
        self._preview.raise_()
        self._preview.show()

    def _reposition_preview(self):
        if not self._preview:
            return
        # Позиция кнопки attach в координатах родителя
        btn_pos = self.attach_button.mapTo(self._preview.parent(), self.attach_button.rect().topLeft())
        pw = self._preview.width()
        ph = self._preview.height()
        x = btn_pos.x() + (self.attach_button.width() - pw) // 2
        y = btn_pos.y() - ph - 6
        self._preview.move(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_preview()

    def _on_preview_removed(self):
        self.attached_file = None
        self._preview = None

    def _send_button_pressed(self, event):
        SendButton.mousePressEvent(self.send_button, event)
        self._on_send()

    def _on_send(self):
        text = self.input_field.text().strip()
        file = self.attached_file

        if not text and not file:
            return

        if text:
            self.message_sent.emit(text)

        if file:
            self.file_sent.emit(file)
            self.attached_file = None
            if self._preview:
                self._preview.hide()
                self._preview.deleteLater()
                self._preview = None

        self.input_field.clear()

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(QColor(self.color_border))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(0, 0, self.width(), 0)