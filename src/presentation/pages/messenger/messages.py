import os
from datetime import datetime, timezone
from uuid import UUID

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .theme import (
    COLOR_CONTEXT_MENU_BACKGROUND,
    COLOR_LOADING_SPINNER,
    COLOR_MESSAGE_TEXT,
    COLOR_OVERLAY,
    COLOR_PANEL_BACKGROUND,
    COLOR_SCROLLBAR_HANDLE,
    COLOR_SCROLLBAR_TRACK,
    COLOR_TEXT_ON_PRIMARY,
    COLOR_TEXT_ON_SURFACE,
    COLOR_VIDEO_CONTROLS_BACKGROUND,
    COLOR_VIDEO_SLIDER_GROOVE,
    COLOR_VIDEO_THUMBNAIL_BACKGROUND,
    COLOR_VIDEO_VIEWER_OVERLAY,
    OVERLAY_OPACITY,
)


def _as_utc(timestamp: datetime | None = None) -> datetime:
    if timestamp is None:
        return datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _as_local(timestamp: datetime) -> datetime:
    return _as_utc(timestamp).astimezone()


class LoadingSpinner(QWidget):
    def __init__(self, parent=None, size=14, color: str = COLOR_LOADING_SPINNER):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._rotate)
        self._color = QColor(color)
        self.hide()

    def start(self):
        self._timer.start(50)
        self.show()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _rotate(self):
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._color, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        rect = QRect(2, 2, self.width() - 4, self.height() - 4)
        painter.drawArc(rect, self._angle * 16, 270 * 16)


class DayDivider(QWidget):
    def __init__(self, date: datetime, color_primary: str, parent=None):
        super().__init__(parent)
        self.date = date
        self.color_primary = color_primary
        self.setFixedHeight(30)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor(self.color_primary))
        pen.setWidth(1)
        painter.setPen(pen)
        mid_y = self.height() // 2
        text_width = 60
        margin = 40
        left_line_end = (self.width() - text_width) // 2 - margin
        right_line_start = (self.width() + text_width) // 2 + margin

        painter.drawLine(margin, mid_y, left_line_end, mid_y)
        painter.drawLine(right_line_start, mid_y, self.width() - margin, mid_y)

        font = QFont("Roboto", 10)
        painter.setFont(font)
        painter.setPen(QColor(self.color_primary))
        date_str = self.date.strftime("%d %b")
        painter.drawText(
            QRect((self.width() - text_width) // 2, 0, text_width, self.height()),
            Qt.AlignmentFlag.AlignCenter,
            date_str,
        )


class MessageBubble(QWidget):
    context_action = pyqtSignal(str)
    delete_requested = pyqtSignal(object)

    def __init__(
        self,
        server_message_id: UUID | None,
        text: str,
        is_mine: bool,
        color_primary: str,
        color_outgoing: str,
        color_inactive: str,
        color_error: str,
        color_third: str,
        timestamp: datetime | None = None,
        status: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.server_message_id = server_message_id
        self.text = text
        self.is_mine = is_mine
        self.color_primary = color_primary
        self.color_outgoing = color_outgoing
        self.color_inactive = color_inactive
        self.color_error = color_error
        self.color_third = color_third
        self.timestamp = _as_utc(timestamp)
        self.status = status

        if self.is_mine:
            if self.status == "failed":
                self.current_bg_color = self.color_error
            elif self.status == "sent" or self.status == "read":
                self.current_bg_color = self.color_outgoing
            else:
                self.current_bg_color = self.color_third
        else:
            self.current_bg_color = self.color_inactive

        self._anim_timer: QTimer | None = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._font = QFont("Roboto", 11)
        self._meta_font = QFont("Roboto", 8)
        self._padding_x = 18
        self._padding_y = 10
        self._bubble_max_width = 420
        self._tw = 8
        self._meta_h = 20

        fm = QFontMetrics(self._font)
        text_width = min(
            fm.horizontalAdvance(text), self._bubble_max_width - self._padding_x * 2
        )
        text_height = fm.boundingRect(
            QRect(0, 0, text_width, 9999), Qt.TextFlag.TextWordWrap, text
        ).height()

        bubble_h = text_height + self._padding_y * 2 + self._meta_h
        self.setFixedHeight(bubble_h + 20)

        self.spinner = LoadingSpinner(self, size=14, color=COLOR_LOADING_SPINNER)
        self.spinner.raise_()
        if self.is_mine and self.status == "":
            self.spinner.start()
        self._update_spinner_pos()

    def set_status(self, new_status: str):
        if self.status == new_status:
            return
        self.status = new_status

        if not self.is_mine:
            return

        if new_status == "":
            self.spinner.start()
        else:
            self.spinner.stop()

        if new_status == "failed":
            target_color = self.color_error
        elif new_status in ("sent", "read"):
            target_color = self.color_outgoing
        else:
            target_color = self.color_third

        self._animate_bg_to(target_color)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_spinner_pos()

    def _get_bubble_size(self):
        fm = QFontMetrics(self._font)
        text_width = min(
            fm.horizontalAdvance(self.text),
            self._bubble_max_width - self._padding_x * 2,
        )
        text_height = fm.boundingRect(
            QRect(0, 0, text_width, 9999), Qt.TextFlag.TextWordWrap, self.text
        ).height()
        bubble_w = text_width + self._padding_x * 2
        bubble_h = text_height + self._padding_y * 2 + self._meta_h
        return bubble_w, bubble_h

    def _update_spinner_pos(self):
        if not self.is_mine:
            return
        bubble_w, _ = self._get_bubble_size()
        margin = 16
        bx = self.width() - bubble_w - margin  # левый край пузырька
        spinner_x = bx - self.spinner.width() - 4  # слева от пузырька с отступом 4px
        spinner_y = (self.height() - self.spinner.height()) // 2
        self.spinner.move(spinner_x, spinner_y)
        self.spinner.raise_()

    def _animate_bg_to(self, target_color: str):
        if self._anim_timer and self._anim_timer.isActive():
            self._anim_timer.stop()

        self._anim_start = QColor(self.current_bg_color)
        self._anim_end = QColor(target_color)
        self._anim_step = 0
        self._anim_steps = 20
        self._anim_timer = QTimer()
        self._anim_timer.timeout.connect(self._tick_bg_animation)
        self._anim_timer.start(15)

    def _tick_bg_animation(self):
        if self._anim_step >= self._anim_steps:
            if self._anim_timer is not None:
                self._anim_timer.stop()
            self.current_bg_color = self._anim_end.name()
            self.update()
            return

        ratio = self._anim_step / self._anim_steps
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

        self.current_bg_color = QColor(r, g, b).name()
        self.update()
        self._anim_step += 1

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self._font)

        fm = QFontMetrics(self._font)
        text_width = min(
            fm.horizontalAdvance(self.text),
            self._bubble_max_width - self._padding_x * 2,
        )
        text_height = fm.boundingRect(
            QRect(0, 0, text_width, 9999), Qt.TextFlag.TextWordWrap, self.text
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
        path.moveTo(bx + tw, by)
        path.lineTo(bx, by + bubble_h / 2)
        path.lineTo(bx + tw, by + bubble_h)
        path.lineTo(bx + bubble_w - tw, by + bubble_h)
        path.lineTo(bx + bubble_w, by + bubble_h / 2)
        path.lineTo(bx + bubble_w - tw, by)
        path.closeSubpath()

        if self.is_mine and self.status == "failed":
            fill_color = self.color_error
        else:
            fill_color = self.current_bg_color

        painter.fillPath(path, QColor(fill_color))
        pen = QPen(QColor(fill_color))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)

        painter.setPen(QColor(COLOR_MESSAGE_TEXT))
        painter.setFont(self._font)
        painter.drawText(
            QRect(bx + self._padding_x, by + self._padding_y, text_width, text_height),
            Qt.TextFlag.TextWordWrap,
            self.text,
        )

        painter.setFont(self._meta_font)
        meta_y = by + self._padding_y + text_height + 2
        meta_rect = QRect(bx + tw, meta_y, bubble_w - tw * 2, self._meta_h)

        # Отображаем только время ЧЧ:ММ
        time_str = _as_local(self.timestamp).strftime("%H:%M")
        time_color = QColor(COLOR_MESSAGE_TEXT)
        time_color.setAlphaF(0.75)
        painter.setPen(time_color)
        painter.drawText(
            meta_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"   {time_str}",
        )

        if self.is_mine and self.status:
            if self.status == "read":
                checkmark = "◢︎◢︎︎"
            elif self.status == "sent":
                checkmark = "◢︎"
            elif self.status == "failed":
                checkmark = "×"
            else:
                checkmark = ""

            if checkmark:
                check_color = QColor(COLOR_MESSAGE_TEXT)
                painter.setPen(check_color)
                painter.setFont(QFont("Roboto", 13))
                painter.drawText(
                    meta_rect,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    checkmark,
                )

    def _bubble_path(self) -> QPainterPath:
        # Returns the path of the bubble hexagon in widget coordinates.

        fm = QFontMetrics(self._font)
        text_width = min(
            fm.horizontalAdvance(self.text),
            self._bubble_max_width - self._padding_x * 2,
        )
        text_height = fm.boundingRect(
            QRect(0, 0, text_width, 9999), Qt.TextFlag.TextWordWrap, self.text
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
        path.moveTo(bx + tw, by)
        path.lineTo(bx, by + bubble_h / 2)
        path.lineTo(bx + tw, by + bubble_h)
        path.lineTo(bx + bubble_w - tw, by + bubble_h)
        path.lineTo(bx + bubble_w, by + bubble_h / 2)
        path.lineTo(bx + bubble_w - tw, by)
        path.closeSubpath()
        return path

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            if self._bubble_path().contains(QPointF(event.pos())):
                self._show_context_menu(event.pos())
            return
        super().mousePressEvent(event)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu {
                background-color: """
            + COLOR_CONTEXT_MENU_BACKGROUND
            + ";" + """
                border: 1px solid """
            + self.color_primary
            + """;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                color: """
            + self.color_primary
            + """;
                padding: 6px 24px;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: """
            + self.color_primary
            + """;
                color: """
            + COLOR_TEXT_ON_PRIMARY
            + ";" + """
            }
        """
        )
        copy_action = menu.addAction("⛘ COPY")
        delete_action = menu.addAction("⌫ DELETE")
        forward_action = menu.addAction("↹ FORWARD")
        reply_action = menu.addAction("↪ REPLY")

        action = menu.exec(self.mapToGlobal(pos))
        if action == copy_action:
            print(self.text.replace("‹ ", "").replace(" ›", ""))
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(
                    self.text.replace("‹ ", "").replace(" ›", "")
                )
            self.context_action.emit("copy_text")
        elif action == delete_action:
            print(f"Deleting message {self.server_message_id}")
            self.context_action.emit("delete")
            self.delete_requested.emit(self.server_message_id)
        elif action == forward_action:
            self.context_action.emit("forward")
        elif action == reply_action:
            self.context_action.emit("reply")


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
        parent = self.parent()
        if isinstance(parent, QWidget):
            self.setGeometry(parent.rect())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        overlay_color = QColor(COLOR_OVERLAY)
        overlay_color.setAlpha(OVERLAY_OPACITY)
        painter.fillRect(self.rect(), overlay_color)

        if self._pixmap.isNull():
            return

        margin = 60
        target = self.rect().adjusted(margin, margin, -margin, -margin)
        scaled = self._pixmap.scaled(
            target.width(),
            target.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
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
            "‹ C L I C K  T O  C L O S E ›",
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
        color_outgoing: str,
        color_inactive: str,
        color_error: str,
        color_third: str,  # серый (цвет отправки)
        timestamp: datetime | None = None,
        status: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.path = path
        self.is_mine = is_mine
        self.color_primary = color_primary
        self.color_outgoing = color_outgoing
        self.color_inactive = color_inactive
        self.color_error = color_error
        self.color_third = color_third
        self.timestamp = _as_utc(timestamp)
        self.status = status

        # Определяем текущий цвет фона
        if self.is_mine:
            if self.status == "failed":
                self.current_bg_color = self.color_error
            elif self.status in ("sent", "read"):
                self.current_bg_color = self.color_outgoing
            else:
                self.current_bg_color = self.color_third
        else:
            self.current_bg_color = self.color_inactive

        self._anim_timer: QTimer | None = None

        self._margin = 16
        self._max_img_w = 320
        self._max_img_h = 240
        self._tw = 8
        self._padding_x = 12
        self._padding_y = 12
        self._meta_h = 18

        # Загружаем и масштабируем изображение
        self._pixmap = QPixmap(path)
        if not self._pixmap.isNull():
            self._pixmap = self._pixmap.scaled(
                self._max_img_w,
                self._max_img_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._img_w = self._pixmap.width() if not self._pixmap.isNull() else 100
        self._img_h = self._pixmap.height() if not self._pixmap.isNull() else 100

        self._bubble_w = self._img_w + self._padding_x * 2
        self._bubble_h = self._img_h + self._padding_y * 2 + self._meta_h + 4

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self._bubble_h + 20)

        # Спиннер (только для своих сообщений в статусе отправки)
        self.spinner = LoadingSpinner(self, size=14, color=COLOR_LOADING_SPINNER)
        self.spinner.raise_()
        if self.is_mine and self.status == "":
            self.spinner.start()
        self._update_spinner_pos()

    def set_status(self, new_status: str):
        if self.status == new_status:
            return
        self.status = new_status

        if not self.is_mine:
            return

        if new_status == "":
            self.spinner.start()
        else:
            self.spinner.stop()

        if new_status == "failed":
            target_color = self.color_error
        elif new_status in ("sent", "read"):
            target_color = self.color_outgoing
        else:
            target_color = self.color_third

        self._animate_bg_to(target_color)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_spinner_pos()

    def _bubble_x(self) -> int:
        if self.is_mine:
            return self.width() - self._bubble_w - self._margin
        else:
            return self._margin

    def _update_spinner_pos(self):
        if not self.is_mine:
            return
        bx = self._bubble_x()
        spinner_x = bx - self.spinner.width() - 4
        spinner_y = (self.height() - self.spinner.height()) // 2
        self.spinner.move(spinner_x, spinner_y)
        self.spinner.raise_()

    def _animate_bg_to(self, target_color: str):
        if self._anim_timer and self._anim_timer.isActive():
            self._anim_timer.stop()

        self._anim_start = QColor(self.current_bg_color)
        self._anim_end = QColor(target_color)
        self._anim_step = 0
        self._anim_steps = 20
        self._anim_timer = QTimer()
        self._anim_timer.timeout.connect(self._tick_bg_animation)
        self._anim_timer.start(15)

    def _tick_bg_animation(self):
        if self._anim_step >= self._anim_steps:
            if self._anim_timer is not None:
                self._anim_timer.stop()
            self.current_bg_color = self._anim_end.name()
            self.update()
            return

        ratio = self._anim_step / self._anim_steps
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

        self.current_bg_color = QColor(r, g, b).name()
        self.update()
        self._anim_step += 1

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )

        bw = self._bubble_w
        bh = self._bubble_h
        bx = self._bubble_x()
        by = 4
        tw = self._tw

        # Шестиугольная рамка
        path = QPainterPath()
        path.moveTo(bx + tw, by)
        path.lineTo(bx, by + bh / 2)
        path.lineTo(bx + tw, by + bh)
        path.lineTo(bx + bw - tw, by + bh)
        path.lineTo(bx + bw, by + bh / 2)
        path.lineTo(bx + bw - tw, by)
        path.closeSubpath()

        fill_color = QColor(self.current_bg_color)
        painter.fillPath(path, fill_color)
        pen = QPen(fill_color)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)

        # Изображение внутри
        if not self._pixmap.isNull():
            img_x = bx + self._padding_x
            img_y = by + self._padding_y
            painter.drawPixmap(img_x, img_y, self._pixmap)

        # Время и статус
        meta_y = by + self._padding_y + self._img_h + 4
        meta_rect = QRect(bx + tw, meta_y, bw - tw * 2, self._meta_h)

        time_str = _as_local(self.timestamp).strftime("%H:%M")
        time_color = QColor(COLOR_MESSAGE_TEXT)
        time_color.setAlphaF(0.75)
        painter.setPen(time_color)
        painter.setFont(QFont("Roboto", 8))
        painter.drawText(
            meta_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"   {time_str}",
        )

        if self.is_mine and self.status:
            if self.status == "read":
                checkmark = "◢︎◢︎"
            elif self.status == "sent":
                checkmark = "◢︎"
            elif self.status == "failed":
                checkmark = "×"
            else:
                checkmark = ""

            if checkmark:
                painter.setPen(QColor(COLOR_MESSAGE_TEXT))
                painter.setFont(QFont("Roboto", 13))
                painter.drawText(
                    meta_rect,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    checkmark,
                )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            top = self.window()
            full_pixmap = QPixmap(self.path)
            viewer = ImageViewer(self.color_primary, full_pixmap, top)
            viewer.setFocus()
        super().mousePressEvent(event)


class VideoBubble(QWidget):
    def __init__(
        self,
        path: str,
        is_mine: bool,
        color_primary: str,
        color_outgoing: str,
        color_inactive: str,
        color_error: str,
        color_third: str,
        timestamp: datetime | None = None,
        status: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.path = path
        self.is_mine = is_mine
        self.color_primary = color_primary
        self.color_outgoing = color_outgoing
        self.color_inactive = color_inactive
        self.color_error = color_error
        self.color_third = color_third
        self.timestamp = _as_utc(timestamp)
        self.status = status

        if self.is_mine:
            if self.status == "failed":
                self.current_bg_color = self.color_error
            elif self.status in ("sent", "read"):
                self.current_bg_color = self.color_outgoing
            else:
                self.current_bg_color = self.color_third
        else:
            self.current_bg_color = self.color_inactive

        self._anim_timer: QTimer | None = None

        self._margin = 16
        self._thumb_w = 320
        self._thumb_h = 240
        self._tw = 8
        self._padding_x = 12
        self._padding_y = 12
        self._meta_h = 18

        self._bubble_w = self._thumb_w + self._padding_x * 2
        self._bubble_h = self._thumb_h + self._padding_y * 2 + self._meta_h + 4

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self._bubble_h + 20)

        self._thumbnail: QPixmap | None = None

        self._capture_thumbnail()

        self.spinner = LoadingSpinner(self, size=14, color=COLOR_LOADING_SPINNER)
        self.spinner.raise_()
        if self.is_mine and self.status == "":
            self.spinner.start()
        self._update_spinner_pos()

    def _capture_thumbnail(self):
        if not os.path.exists(self.path):
            return

        self._player = QMediaPlayer()
        self._player.setSource(QUrl.fromLocalFile(self.path))
        from PyQt6.QtMultimedia import QVideoSink

        self._sink = QVideoSink()
        self._player.setVideoSink(self._sink)

        self._capture_attempts = 0
        self._sink.videoFrameChanged.connect(self._on_video_frame_changed)
        self._player.play()
        QTimer.singleShot(3000, self._check_thumbnail_fallback)

    def _on_video_frame_changed(self, frame):
        if self._thumbnail is not None:
            return
        if frame.isValid():
            pix = QPixmap.fromImage(frame.toImage())
            if not pix.isNull():
                self._thumbnail = pix.scaled(
                    self._thumb_w,
                    self._thumb_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._player.pause()
                self.update()

    def _check_thumbnail_fallback(self):
        if self._thumbnail is None:
            self.update()

    def set_status(self, new_status: str):
        if self.status == new_status:
            return
        self.status = new_status

        if not self.is_mine:
            return

        if new_status == "":
            self.spinner.start()
        else:
            self.spinner.stop()

        if new_status == "failed":
            target_color = self.color_error
        elif new_status in ("sent", "read"):
            target_color = self.color_outgoing
        else:
            target_color = self.color_third

        self._animate_bg_to(target_color)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_spinner_pos()

    def _bubble_x(self) -> int:
        if self.is_mine:
            return self.width() - self._bubble_w - self._margin
        else:
            return self._margin

    def _update_spinner_pos(self):
        if not self.is_mine:
            return
        bx = self._bubble_x()
        spinner_x = bx - self.spinner.width() - 4
        spinner_y = (self.height() - self.spinner.height()) // 2
        self.spinner.move(spinner_x, spinner_y)
        self.spinner.raise_()

    def _animate_bg_to(self, target_color: str):
        if self._anim_timer and self._anim_timer.isActive():
            self._anim_timer.stop()

        self._anim_start = QColor(self.current_bg_color)
        self._anim_end = QColor(target_color)
        self._anim_step = 0
        self._anim_steps = 20
        self._anim_timer = QTimer()
        self._anim_timer.timeout.connect(self._tick_bg_animation)
        self._anim_timer.start(15)

    def _tick_bg_animation(self):
        if self._anim_step >= self._anim_steps:
            if self._anim_timer is not None:
                self._anim_timer.stop()
            self.current_bg_color = self._anim_end.name()
            self.update()
            return

        ratio = self._anim_step / self._anim_steps
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

        self.current_bg_color = QColor(r, g, b).name()
        self.update()
        self._anim_step += 1

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )

        bw = self._bubble_w
        bh = self._bubble_h
        bx = self._bubble_x()
        by = 4
        tw = self._tw

        path = QPainterPath()
        path.moveTo(bx + tw, by)
        path.lineTo(bx, by + bh / 2)
        path.lineTo(bx + tw, by + bh)
        path.lineTo(bx + bw - tw, by + bh)
        path.lineTo(bx + bw, by + bh / 2)
        path.lineTo(bx + bw - tw, by)
        path.closeSubpath()

        fill_color = QColor(self.current_bg_color)
        painter.fillPath(path, fill_color)
        pen = QPen(fill_color)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)

        thumb_x = bx + self._padding_x
        thumb_y = by + self._padding_y
        thumb_rect = QRect(thumb_x, thumb_y, self._thumb_w, self._thumb_h)

        if self._thumbnail is not None:
            painter.drawPixmap(thumb_rect, self._thumbnail)
        else:
            painter.fillRect(thumb_rect, QColor(COLOR_VIDEO_THUMBNAIL_BACKGROUND))
            painter.setPen(QPen(QColor(self.color_inactive), 1))
            painter.drawRect(thumb_rect)
            painter.setPen(QColor(self.color_primary))
            painter.setFont(QFont("Roboto", 48))
            painter.drawText(thumb_rect, Qt.AlignmentFlag.AlignCenter, "▶")

        meta_y = by + self._padding_y + self._thumb_h + 4
        meta_rect = QRect(bx + tw, meta_y, bw - tw * 2, self._meta_h)

        time_str = _as_local(self.timestamp).strftime("%H:%M")
        time_color = QColor(COLOR_MESSAGE_TEXT)
        time_color.setAlphaF(0.75)
        painter.setPen(time_color)
        painter.setFont(QFont("Roboto", 8))
        painter.drawText(
            meta_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"   {time_str}",
        )

        if self.is_mine and self.status:
            if self.status == "read":
                checkmark = "◢︎◢︎"
            elif self.status == "sent":
                checkmark = "◢︎"
            elif self.status == "failed":
                checkmark = "×"
            else:
                checkmark = ""

            if checkmark:
                painter.setPen(QColor(COLOR_MESSAGE_TEXT))
                painter.setFont(QFont("Roboto", 13))
                painter.drawText(
                    meta_rect,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    checkmark,
                )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            viewer = VideoViewer(self.path, self.color_primary, self.window())
            viewer.setFocus()
        super().mousePressEvent(event)


class VideoViewer(QWidget):
    def __init__(self, file_path: str, color_primary: str, parent=None):
        super().__init__(parent)
        self.color_primary = color_primary
        self.file_path = file_path

        self.setGeometry(parent.rect() if parent else QRect(0, 0, 800, 600))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(f"background: {COLOR_VIDEO_VIEWER_OVERLAY};")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self.video_widget = QVideoWidget()
        self.video_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )  # ← исправлено
        self.video_widget.setStyleSheet(
            f"background: {COLOR_VIDEO_THUMBNAIL_BACKGROUND};"
        )

        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.setSource(QUrl.fromLocalFile(file_path))
        self.media_player.play()

        self._layout.addWidget(self.video_widget, 1)

        controls = QWidget()
        controls.setStyleSheet(
            f"background: {COLOR_VIDEO_CONTROLS_BACKGROUND};"
        )
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(12, 8, 12, 8)
        controls_layout.setSpacing(10)

        self.play_pause_btn = QPushButton("◼")
        self.play_pause_btn.setFixedSize(40, 40)
        self.play_pause_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.color_primary};
                border: none;
                border-radius: 20px;
                font-size: 18px;
                color: {COLOR_TEXT_ON_PRIMARY};
            }}
            QPushButton:hover {{
                opacity: 0.8;
            }}
        """)
        self.play_pause_btn.clicked.connect(self.toggle_play_pause)
        controls_layout.addWidget(self.play_pause_btn)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {COLOR_VIDEO_SLIDER_GROOVE};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {self.color_primary};
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{
                background: {self.color_primary};
            }}
        """)
        self.position_slider.sliderMoved.connect(self.set_position)
        controls_layout.addWidget(self.position_slider, 1)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet(
            f"color: {COLOR_TEXT_ON_SURFACE}; font-size: 12px;"
        )
        controls_layout.addWidget(self.time_label)

        self._layout.addWidget(controls)

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_ui)
        self.update_timer.start(200)

        self.media_player.playbackStateChanged.connect(self.on_state_changed)
        self.media_player.durationChanged.connect(self.on_duration_changed)
        self.media_player.positionChanged.connect(self.on_position_changed)

        self.setFocus()
        self.show()

    def toggle_play_pause(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def set_position(self, pos):
        self.media_player.setPosition(pos)

    def on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_pause_btn.setText("◼︎")
        else:
            self.play_pause_btn.setText("▶")

    def on_duration_changed(self, duration):
        self.position_slider.setRange(0, duration)
        self.update_time_label()

    def on_position_changed(self, position):
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(position)
        self.position_slider.blockSignals(False)
        self.update_time_label()

    def update_ui(self):
        pass

    def update_time_label(self):
        pos = self.media_player.position()
        dur = self.media_player.duration()
        pos_str = f"{pos // 60000:02d}:{(pos // 1000) % 60:02d}"
        dur_str = f"{dur // 60000:02d}:{(dur // 1000) % 60:02d}" if dur > 0 else "00:00"
        self.time_label.setText(f"{pos_str} / {dur_str}")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QColor(self.color_primary))
        painter.setFont(QFont("Roboto", 10))
        if hasattr(self, "close_hint") and self.close_hint:
            painter.drawText(
                self.rect().adjusted(0, self.height() - 40, -16, -12),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                self.close_hint,
            )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_Space:
            self.toggle_play_pause()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.pos().y() < self.height() - 60:
            self.close()
        super().mousePressEvent(event)

    def closeEvent(self, event):
        self.media_player.stop()
        self.update_timer.stop()
        super().closeEvent(event)

    def showEvent(self, event):
        self.close_hint = "‹ C L I C K   T O   C L O S E ›"
        QTimer.singleShot(3000, lambda: setattr(self, "close_hint", ""))
        super().showEvent(event)


class MessageList(QWidget):
    def __init__(
        self,
        color_primary: str,
        color_outgoing: str,
        color_inactive: str,
        color_error: str,
        color_third: str,
        parent=None,
    ):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_outgoing = color_outgoing
        self.color_inactive = color_inactive
        self.color_error = color_error
        self.color_third = color_third

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 8, 0, 8)
        self._layout.setSpacing(2)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(self._layout)

        self._last_date: tuple[int, int, int] | None = None

    def _divider(self, current_date: datetime):
        local_date = _as_local(current_date)
        current_key = (local_date.year, local_date.month, local_date.day)
        if self._last_date is None:
            divider = DayDivider(local_date, self.color_primary)
            self._layout.addWidget(divider)
            self._last_date = current_key
            return
        if current_key != self._last_date:
            divider = DayDivider(local_date, self.color_primary)
            self._layout.addWidget(divider)
            self._last_date = current_key

    def add_message(
        self,
        server_message_id: UUID | None,
        text: str,
        is_mine: bool,
        timestamp: datetime | None = None,
        status: str = "",
    ) -> MessageBubble:
        timestamp = _as_utc(timestamp)
        self._divider(timestamp)
        bubble = MessageBubble(
            server_message_id,
            text,
            is_mine,
            self.color_primary,
            self.color_outgoing,
            self.color_inactive,
            self.color_error,
            self.color_third,
            timestamp,
            status,
        )
        self._layout.addWidget(bubble)
        return bubble

    def add_video(
        self, path: str, is_mine: bool, timestamp: datetime | None = None, status: str = ""
    ) -> VideoBubble:
        timestamp = _as_utc(timestamp)
        self._divider(timestamp)
        bubble = VideoBubble(
            path,
            is_mine,
            self.color_primary,
            self.color_outgoing,
            self.color_inactive,
            self.color_error,
            self.color_third,
            timestamp,
            status,
        )
        self._layout.addWidget(bubble)
        return bubble

    def add_image(self, path: str, is_mine: bool, timestamp: datetime | None = None):
        timestamp = _as_utc(timestamp)
        self._divider(timestamp)
        bubble = ImageBubble(
            path,
            is_mine,
            self.color_primary,
            self.color_outgoing,
            self.color_inactive,
            self.color_error,
            self.color_third,
            timestamp,
        )
        self._layout.addWidget(bubble)
        return bubble

    def clear_messages(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._last_date = None


class MessagesView(QWidget):
    def __init__(
        self,
        color_primary: str,
        color_outgoing: str,
        color_inactive: str,
        color_error: str,
        color_third: str,
        parent=None,
    ):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_outgoing = color_outgoing
        self.color_inactive = color_inactive
        self.color_error = color_error
        self.color_third = color_third

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {COLOR_PANEL_BACKGROUND}; }}
            QScrollBar:vertical {{ background: {COLOR_SCROLLBAR_TRACK}; width: 4px; }}
            QScrollBar::handle:vertical {{ background: {COLOR_SCROLLBAR_HANDLE}; border-radius: 2px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        self.message_list = MessageList(
            self.color_primary,
            self.color_outgoing,
            self.color_inactive,
            self.color_error,
            self.color_third,
            parent,
        )
        scroll.setWidget(self.message_list)
        self._scroll = scroll

        layout.addWidget(scroll)
        self.setLayout(layout)

        QTimer.singleShot(50, self._smooth_scroll_to_bottom)

    # def _scroll_to_bottom(self):
    #    bar = self._scroll.verticalScrollBar()
    #    bar.setValue(bar.maximum())

    def _smooth_scroll_to_bottom(self):
        scrollbar = self._scroll.verticalScrollBar()
        if scrollbar is None:
            return
        target = scrollbar.maximum()
        current = scrollbar.value()
        if current == target:
            return
        self._scroll_animation = QPropertyAnimation(scrollbar, b"value")
        self._scroll_animation.setDuration(500)
        self._scroll_animation.setStartValue(current)
        self._scroll_animation.setEndValue(target)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scroll_animation.start()
