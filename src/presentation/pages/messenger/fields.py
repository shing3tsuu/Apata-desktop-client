import os

from PyQt6.QtCore import QEvent, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QWidget

from .buttons import AttachButton, SendButton
from .theme import (
    COLOR_CONTACT_BACKGROUND,
    COLOR_INPUT_FOCUS,
    COLOR_PANEL_BACKGROUND,
    COLOR_SEARCH_BACKGROUND,
    COLOR_SEARCH_BORDER,
    COLOR_SEARCH_FOCUS,
    COLOR_SEARCH_PLACEHOLDER,
    COLOR_SEARCH_TEXT,
    COLOR_TEXT,
    COLOR_PREVIEW_BACKGROUND,
)


class ConversationSearchField(QWidget):
    text_changed = pyqtSignal(str)
    search_submitted = pyqtSignal(str)

    def __init__(
        self,
        placeholder: str = "SEARCH CONTACTS",
        color_background: str = COLOR_SEARCH_BACKGROUND,
        color_border: str = COLOR_SEARCH_BORDER,
        color_focus: str = COLOR_SEARCH_FOCUS,
        color_text: str = COLOR_SEARCH_TEXT,
        color_placeholder: str = COLOR_SEARCH_PLACEHOLDER,
        parent=None,
    ):
        super().__init__(parent)
        self.color_background = color_background
        self.color_border = color_border
        self.color_focus = color_focus
        self.current_border_color = color_border
        self.is_focused = False
        self._border_timer: QTimer | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            QLabel {{
                background: transparent;
                border: none;
            }}
            QLineEdit {{
                background: transparent;
                border: none;
                color: {color_text};
                placeholder-text-color: {color_placeholder};
                padding: 0px;
            }}
        """)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 1, 8, 1)
        self._layout.setSpacing(6)

        self.search_icon = QLabel("🔎")
        self.search_icon.setFixedWidth(24)
        self.search_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.search_icon.setFont(QFont("Segoe UI Emoji", 12))
        self._layout.addWidget(self.search_icon)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText(placeholder)
        self.input_field.setFont(QFont("Roboto", 10))
        self.input_field.installEventFilter(self)
        self.input_field.textChanged.connect(self.text_changed.emit)
        self.input_field.returnPressed.connect(self._submit_search)
        self._layout.addWidget(self.input_field, stretch=1)

        self._trailing_widget: QWidget | None = None

    def set_trailing_widget(self, widget: QWidget) -> None:
        if self._trailing_widget is not None:
            self._layout.removeWidget(self._trailing_widget)
            self._trailing_widget.setParent(None)
        self._trailing_widget = widget
        self._layout.addWidget(widget)

    def set_placeholder_text(self, text: str) -> None:
        self.input_field.setPlaceholderText(text)

    def text(self) -> str:
        return self.input_field.text()

    def set_text(self, text: str) -> None:
        self.input_field.setText(text)

    def _submit_search(self) -> None:
        self.search_submitted.emit(self.input_field.text())

    def eventFilter(self, watched, event):
        if watched is self.input_field:
            if event.type() == QEvent.Type.FocusIn:
                self.is_focused = True
                self._animate_border(self.color_focus)
            elif event.type() == QEvent.Type.FocusOut:
                self.is_focused = False
                self._animate_border(self.color_border)
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        self.input_field.setFocus()
        super().mousePressEvent(event)

    def _animate_border(self, target: str) -> None:
        if self._border_timer is not None and self._border_timer.isActive():
            self._border_timer.stop()
        self._border_start = QColor(self.current_border_color)
        self._border_end = QColor(target)
        self._border_step = 0
        self._border_timer = QTimer(self)
        self._border_timer.timeout.connect(self._tick_border)
        self._border_timer.start(15)

    def _tick_border(self) -> None:
        if self._border_step >= 12:
            if self._border_timer is not None:
                self._border_timer.stop()
            self.current_border_color = self._border_end.name()
            self.update()
            return
        ratio = self._border_step / 12
        red = int(
            self._border_start.red()
            + (self._border_end.red() - self._border_start.red()) * ratio
        )
        green = int(
            self._border_start.green()
            + (self._border_end.green() - self._border_start.green()) * ratio
        )
        blue = int(
            self._border_start.blue()
            + (self._border_end.blue() - self._border_start.blue()) * ratio
        )
        self.current_border_color = QColor(red, green, blue).name()
        self.update()
        self._border_step += 1

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        triangle_width = 8
        path = QPainterPath()
        path.moveTo(triangle_width, 0)
        path.lineTo(0, self.height() / 2)
        path.lineTo(triangle_width, self.height())
        path.lineTo(self.width() - triangle_width, self.height())
        path.lineTo(self.width(), self.height() / 2)
        path.lineTo(self.width() - triangle_width, 0)
        path.closeSubpath()

        painter.fillPath(path, QColor(self.color_background))
        pen = QPen(QColor(self.current_border_color))
        pen.setWidth(2 if self.is_focused else 1)
        painter.setPen(pen)
        painter.drawPath(path)


class ChatNameField(QLineEdit):
    submitted = pyqtSignal(str)

    def __init__(
        self,
        color_background: str,
        color_border: str,
        color_focus: str,
        color_text: str,
        parent=None,
    ):
        super().__init__(parent)
        self.color_background = color_background
        self.color_border = color_border
        self.color_focus = color_focus
        self.current_border_color = color_border
        self.is_focused = False
        self._border_timer: QTimer | None = None

        self.setFixedHeight(38)
        self.setMaxLength(100)
        self.setPlaceholderText("CHAT NAME")
        self.setFont(QFont("Roboto", 10))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"background: transparent; border: none; color: {color_text}; "
            "padding: 0 14px;"
        )
        self.returnPressed.connect(lambda: self.submitted.emit(self.text()))

    def focusInEvent(self, event):
        self.is_focused = True
        self._animate_border(self.color_focus)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.is_focused = False
        self._animate_border(self.color_border)
        super().focusOutEvent(event)

    def mark_invalid(self) -> None:
        self.setFocus()
        self._animate_border(self.color_focus)

    def _animate_border(self, target: str) -> None:
        if self._border_timer is not None and self._border_timer.isActive():
            self._border_timer.stop()
        self._border_start = QColor(self.current_border_color)
        self._border_end = QColor(target)
        self._border_step = 0
        self._border_timer = QTimer(self)
        self._border_timer.timeout.connect(self._tick_border)
        self._border_timer.start(15)

    def _tick_border(self) -> None:
        if self._border_step >= 12:
            if self._border_timer is not None:
                self._border_timer.stop()
            self.current_border_color = self._border_end.name()
            self.update()
            return

        ratio = self._border_step / 12
        self.current_border_color = QColor(
            int(
                self._border_start.red()
                + (self._border_end.red() - self._border_start.red()) * ratio
            ),
            int(
                self._border_start.green()
                + (self._border_end.green() - self._border_start.green()) * ratio
            ),
            int(
                self._border_start.blue()
                + (self._border_end.blue() - self._border_start.blue()) * ratio
            ),
        ).name()
        self.update()
        self._border_step += 1

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        triangle_width = 8
        path = QPainterPath()
        path.moveTo(triangle_width, 0)
        path.lineTo(0, self.height() / 2)
        path.lineTo(triangle_width, self.height())
        path.lineTo(self.width() - triangle_width, self.height())
        path.lineTo(self.width(), self.height() / 2)
        path.lineTo(self.width() - triangle_width, 0)
        path.closeSubpath()

        painter.fillPath(path, QColor(self.color_background))
        pen = QPen(QColor(self.current_border_color))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()
        super().paintEvent(event)


class AttachPreview(QWidget):
    removed = pyqtSignal()

    def __init__(
        self,
        path: str,
        color_primary: str,
        color_border: str,
        color_focus: str,
        parent=None,
    ):
        super().__init__(parent)
        self.path = path
        self.color_primary = color_primary
        self.color_border = color_border
        self.color_focus = color_focus

        self._thumb_size = 200
        self._is_image = path.lower().endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
        )

        self._pixmap: QPixmap | None
        if self._is_image:
            self._pixmap = QPixmap(path).scaled(
                self._thumb_size,
                self._thumb_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
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

        painter.fillPath(bg_path, QColor(COLOR_PREVIEW_BACKGROUND))
        pen = QPen(QColor(self.color_border))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(bg_path)

        if self._is_image and self._pixmap and not self._pixmap.isNull():
            pw = self._pixmap.width()
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
                "⎙",
            )

        font_name = QFont("Roboto", 8)
        painter.setFont(font_name)
        painter.setPen(QColor(self.color_primary))
        painter.drawText(
            QRect(6, self.height() - 26, self.width() - 12, 20),
            Qt.AlignmentFlag.AlignCenter,
            self._filename,
        )

        font_x = QFont("Roboto", 9)
        painter.setFont(font_x)
        painter.setPen(QColor(self.color_primary))
        painter.drawText(
            QRect(self.width() - 22, 4, 16, 16), Qt.AlignmentFlag.AlignCenter, "✕"
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
        self,
        color_primary: str,
        color_border: str,
        color_focus: str,
        color_background: str = COLOR_CONTACT_BACKGROUND,
        color_text: str = COLOR_TEXT,
        parent=None,
    ):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_border = color_border
        self.current_border_color = color_border
        self.color_focus = color_focus
        self.color_background = color_background
        self.color_text = color_text
        self.is_focused = False
        self._timer: QTimer | None = None

        self.setPlaceholderText("")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"background: transparent; border: none; color: {self.color_text};"
        )
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

        font = QFont("Roboto", 11)
        self.setFont(font)

    def focusInEvent(self, event):
        self.is_focused = True
        self._animate_border(self.color_focus)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.is_focused = False
        self._animate_border(self.color_border)
        super().focusOutEvent(event)

    def _animate_border(self, target: str):
        if self._timer is not None and self._timer.isActive():
            self._timer.stop()
        self._anim_start = QColor(self.current_border_color)
        self._anim_end = QColor(target)
        self._anim_step = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_border)
        self._timer.start(30)

    def _tick_border(self):
        if self._anim_step >= 20:
            if self._timer is not None:
                self._timer.stop()
            self.current_border_color = self._anim_end.name()
            self.update()
            return
        ratio = self._anim_step / 20
        r = int(
            self._anim_start.red()
            + (self._anim_end.red() - self._anim_start.red()) * ratio
        )
        g = int(
            self._anim_start.green()
            + (self._anim_end.green() - self._anim_start.green()) * ratio
        )
        b = int(
            self._anim_start.blue()
            + (self._anim_end.blue() - self._anim_start.blue()) * ratio
        )
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

        painter.fillPath(path, QColor(self.color_background))

        pen = QPen(QColor(self.current_border_color))
        pen.setWidth(2 if self.is_focused else 1)
        painter.setPen(pen)
        painter.drawPath(path)

        painter.end()
        super().paintEvent(event)


class MessageField(QWidget):
    message_sent = pyqtSignal(str)
    file_sent = pyqtSignal(str)

    def __init__(
        self,
        color_primary: str,
        color_border: str,
        color_divider: str,
        color_focus: str = COLOR_INPUT_FOCUS,
        parent=None,
    ):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_border = color_border
        self.color_divider = color_divider
        self.color_focus = color_focus
        self.attached_file: str | None = None
        self._preview: "AttachPreview | None" = None

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

        self.input_field = MessageInputField(
            self.color_primary,
            self.color_border,
            self.color_focus,
        )
        self.input_field.returnPressed.connect(self._on_send)
        layout.addWidget(self.input_field, stretch=1)

        self.send_button = SendButton(self.color_primary, COLOR_PANEL_BACKGROUND)
        self.send_button.mousePressEvent = self._send_button_pressed  # type: ignore[method-assign]
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
        self._preview = AttachPreview(
            path,
            self.color_primary,
            self.color_border,
            self.color_focus,
            parent_widget,
        )
        self._preview.removed.connect(self._on_preview_removed)
        self._reposition_preview()
        self._preview.raise_()
        self._preview.show()

    def _reposition_preview(self):
        if not self._preview:
            return
        # Позиция кнопки attach в координатах родителя
        btn_pos = self.attach_button.mapTo(
            self._preview.parent(), self.attach_button.rect().topLeft()
        )
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
        pen = QPen(QColor(self.color_divider))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(0, 0, self.width(), 0)
