# messenger/buttons
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath

class SendButton(QWidget):
    def __init__(self, color_primary: str, color_secondary: str, parent=None):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_secondary = color_secondary
        self.current_bg_color = color_primary

        self.setFixedWidth(90)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

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

        pen = QPen(QColor(self.current_bg_color))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)

        font = QFont("Roboto", 20)
        painter.setFont(font)
        painter.setPen(QColor(self.color_secondary))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "➤")

    def mousePressEvent(self, event):
        self._animate_click()
        super().mousePressEvent(event)

    def _animate_click(self):
        self.timer = QTimer()
        self.steps = 20
        self.current_step = 10
        self.start_color = QColor(self.color_primary)
        self.end_color = QColor("#373737")
        self.timer.timeout.connect(self._update_color)
        self.timer.start(10)

    def _update_color(self):
        if self.current_step >= self.steps:
            self.current_bg_color = self.color_primary
            self.update()
            self.timer.stop()
            return

        ratio = self.current_step / self.steps
        r = int(self.start_color.red() + (self.end_color.red() - self.start_color.red()) * ratio)
        g = int(self.start_color.green() + (self.end_color.green() - self.start_color.green()) * ratio)
        b = int(self.start_color.blue() + (self.end_color.blue() - self.start_color.blue()) * ratio)

        self.current_bg_color = QColor(r, g, b).name()
        self.update()
        self.current_step += 1

class AttachButton(QWidget):
    file_selected = pyqtSignal(str)  # отдаёт путь к файлу

    def __init__(self, color_primary: str, color_secondary: str, parent=None):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_secondary = color_secondary
        self.current_bg_color = "#000000"
        self.current_border_color = color_secondary

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
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)

        font = QFont("Roboto", 25)
        painter.setFont(font)
        painter.setPen(QColor(self.current_border_color))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "⎙")

    def mousePressEvent(self, event):
        self._animate_hover(self.color_primary)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._animate_hover(self.color_secondary)
        self._open_file_dialog()
        super().mouseReleaseEvent(event)

    def _open_file_dialog(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Attach file",
            "",
            "All files (*);;Images (*.png *.jpg *.jpeg *.gif *.webp);;Documents (*.pdf *.txt *.docx)"
        )
        if path:
            self.file_selected.emit(path)

    def _animate_hover(self, target_border: str):
        self._anim_start = QColor(self.color_primary)
        self._anim_end = QColor(target_border)
        self._anim_step = 10
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(15)

    def _tick(self):
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