# messenger/buttons
from PyQt6.QtCore import (
    QEasingCurve,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from .theme import COLOR_CONTACT_BACKGROUND


class ContactSectionButton(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(
        self,
        title: str,
        color_default: str,
        color_active: str,
        color_background: str,
        count: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.title = title
        self.color_default = color_default
        self.color_active = color_active
        self.color_background = color_background
        self.count = count
        self._expanded = False
        self._rotation = 0.0

        self.setFixedHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"SHOW {title.replace(' ', '')}")
        self.setStyleSheet("background: transparent;")

        self._rotation_animation = QVariantAnimation(self)
        self._rotation_animation.setDuration(180)
        self._rotation_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._rotation_animation.valueChanged.connect(self._set_rotation)

    def _set_rotation(self, value: float) -> None:
        self._rotation = float(value)
        self.update()

    @property
    def expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool, *, animated: bool = True) -> None:
        target_rotation = 180.0 if expanded else 0.0
        self._expanded = expanded
        self.setToolTip(
            f"{'HIDE' if expanded else 'SHOW'} {self.title.replace(' ', '')}"
        )

        self._rotation_animation.stop()
        if animated:
            self._rotation_animation.setStartValue(self._rotation)
            self._rotation_animation.setEndValue(target_rotation)
            self._rotation_animation.start()
        else:
            self._set_rotation(target_rotation)
        self.update()

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.set_expanded(not self._expanded)
            self.toggled.emit(self._expanded)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), QColor(self.color_background))

        color = self.color_active if self._expanded else self.color_default
        icon_font = QFont("Segoe UI Symbol", 13, QFont.Weight.DemiBold)
        title_font = QFont("Roboto Condensed", 9, QFont.Weight.DemiBold)
        display_title = f"{self.title}   ( {self.count} )"
        icon_width = 24
        content_gap = 4
        title_width = QFontMetrics(title_font).horizontalAdvance(display_title)
        content_width = icon_width + content_gap + title_width
        content_left = max(20, (self.width() - content_width) // 2)
        content_right = content_left + content_width
        line_margin = 12
        line_gap = 9
        line_y = self.height() // 2

        line_pen = QPen(QColor(color), 1)
        painter.setPen(line_pen)
        left_line_end = content_left - line_gap
        right_line_start = content_right + line_gap
        if left_line_end > line_margin:
            painter.drawLine(line_margin, line_y, left_line_end, line_y)
        if right_line_start < self.width() - line_margin:
            painter.drawLine(
                right_line_start,
                line_y,
                self.width() - line_margin,
                line_y,
            )

        icon_rect = QRect(content_left, 3, icon_width, self.height() - 6)
        painter.save()
        painter.setPen(QColor(color))
        painter.setFont(icon_font)
        painter.translate(icon_rect.center())
        painter.rotate(self._rotation)
        painter.drawText(
            QRectF(
                -icon_rect.width() / 2,
                -icon_rect.height() / 2,
                icon_rect.width(),
                icon_rect.height(),
            ),
            Qt.AlignmentFlag.AlignCenter,
            "⛛",
        )
        painter.restore()

        painter.setPen(QColor(color))
        painter.setFont(title_font)
        painter.drawText(
            QRect(
                content_left + icon_width + content_gap,
                3,
                title_width,
                self.height() - 6,
            ),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            display_title,
        )


class ConversationTabButton(QWidget):
    clicked = pyqtSignal()

    def __init__(
        self,
        title: str,
        color_active: str,
        color_inactive: str,
        color_divider: str,
        active: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.title = title
        self.color_active = color_active
        self.color_inactive = color_inactive
        self.color_divider = color_divider
        self.active = active
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")

    def set_active(self, active: bool) -> None:
        if self.active == active:
            return
        self.active = active
        self.update()

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.color_active if self.active else self.color_inactive

        painter.setPen(QPen(QColor(self.color_divider), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRect(0, 12, 3, 16)

        painter.setPen(QColor(color))
        painter.setFont(QFont("Roboto", 11))
        painter.drawText(
            self.rect().adjusted(14, 0, 0, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.title,
        )


class GlobalSearchToggleButton(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(
        self,
        color_active: str,
        color_inactive: str,
        parent=None,
    ):
        super().__init__(parent)
        self.color_active = color_active
        self.color_inactive = color_inactive
        self.checked = False
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")

    def set_checked(self, checked: bool, *, emit_signal: bool = False) -> None:
        if self.checked == checked:
            return
        self.checked = checked
        self.update()
        if emit_signal:
            self.toggled.emit(checked)

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.set_checked(not self.checked, emit_signal=True)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.color_active if self.checked else self.color_inactive
        painter.setPen(QColor(color))

        painter.setFont(QFont("Segoe UI Symbol", 13))
        painter.drawText(
            self.rect().adjusted(10, 0, 0, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "☑" if self.checked else "☐",
        )

        label_font = QFont("Roboto", 8)
        label_font.setWeight(QFont.Weight.Bold)
        painter.setFont(label_font)
        painter.drawText(
            self.rect().adjusted(35, 0, 0, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "G L O B A L   S E A R C H",
        )


class CreateChatButton(QWidget):
    clicked = pyqtSignal()

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(self.color))
        painter.setFont(QFont("Segoe UI Symbol", 16))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "✚")


class AddChatParticipantButton(QWidget):
    clicked = pyqtSignal()

    def __init__(
        self,
        color_active: str,
        color_inactive: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.color_active = color_active
        self.color_inactive = color_inactive
        self._active = False
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("ADD CONTACT TO CHAT")
        self.setStyleSheet("background: transparent;")

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.color_active if self._active else self.color_inactive
        painter.setPen(QColor(color))
        painter.setFont(QFont("Segoe UI Symbol", 16))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "⛨")


class CreateChatSubmitButton(QWidget):
    clicked = pyqtSignal()

    def __init__(
        self,
        color: str,
        color_background: str,
        parent=None,
    ):
        super().__init__(parent)
        self.color = color
        self.color_background = color_background
        self._busy = False
        self.setFixedHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.setCursor(
            Qt.CursorShape.ArrowCursor
            if busy
            else Qt.CursorShape.PointingHandCursor
        )
        self.update()

    def mouseReleaseEvent(self, event):
        if (
            not self._busy
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

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
        painter.setPen(QPen(QColor(self.color), 2))
        painter.drawPath(path)
        painter.setPen(QColor(self.color))
        painter.setFont(QFont("Roboto Condensed", 10, QFont.Weight.Normal))
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "C R E A T E",
        )


class SendButton(QWidget):
    def __init__(
        self,
        color_primary: str,
        color_background: str,
        parent=None,
    ):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_background = color_background

        self.setFixedWidth(90)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

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

        pen = QPen(QColor(self.color_primary))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawPath(path)

        font = QFont("Segoe UI Symbol", 20, QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(self.color_primary))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "➤")


class AttachButton(QWidget):
    file_selected = pyqtSignal(str)  # отдаёт путь к файлу

    def __init__(
        self,
        color_primary: str,
        color_secondary: str,
        color_background: str = COLOR_CONTACT_BACKGROUND,
        parent=None,
    ):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_secondary = color_secondary
        self.current_bg_color = color_background
        self.current_border_color = color_secondary
        self.is_pressed = False
        self._timer: QTimer | None = None

        self.setFixedWidth(50)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

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

        painter.fillPath(path, QColor(self.current_bg_color))

        pen = QPen(QColor(self.current_border_color))
        pen.setWidth(2 if self.is_pressed else 1)
        painter.setPen(pen)
        painter.drawPath(path)

        font = QFont("Roboto", 25)
        painter.setFont(font)
        painter.setPen(QColor(self.current_border_color))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "⎙")

    def mousePressEvent(self, event):
        self.is_pressed = True
        self._animate_border(self.color_primary)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_pressed = False
        self._animate_border(self.color_secondary)
        self._open_file_dialog()
        super().mouseReleaseEvent(event)

    def _open_file_dialog(self):
        from PyQt6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Attach file",
            "",
            "All files (*);;Images (*.png *.jpg *.jpeg *.gif *.webp);;Documents (*.pdf *.txt *.docx)",
        )
        if path:
            self.file_selected.emit(path)

    def _animate_border(self, target_border: str):
        if self._timer is not None and self._timer.isActive():
            self._timer.stop()
        self._anim_start = QColor(self.current_border_color)
        self._anim_end = QColor(target_border)
        self._anim_step = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(15)

    def _tick(self):
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
