from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath, QFont
from PyQt6.QtCore import Qt, QTimer

class LoginField(QLineEdit):
    def __init__(
        self,
        placeholder: str,
        color_primary: str,
        color_secondary: str,
        is_password: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_secondary = color_secondary
        self.current_border_color = color_secondary
        self.is_focused = False

        self.setPlaceholderText(placeholder)
        self.setFixedSize(200, 35)

        if is_password:
            self.setEchoMode(QLineEdit.EchoMode.Password)

        font = QFont("Roboto", 14)
        self.setFont(font)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.setStyleSheet("background: transparent; border: none; color: #ffffff;")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        triangle_width = 10

        # Рисуем фон и границу
        path = QPainterPath()

        path.moveTo(triangle_width, 0)
        path.lineTo(0, self.height() / 2)
        path.lineTo(triangle_width, self.height())

        path.lineTo(self.width() - triangle_width, self.height())

        path.lineTo(self.width(), self.height() / 2)
        path.lineTo(self.width() - triangle_width, 0)

        path.lineTo(triangle_width, 0)
        path.closeSubpath()

        # Фон
        painter.fillPath(path, QColor("#000000"))

        # Граница
        pen = QPen(QColor(self.current_border_color))
        pen.setWidth(2 if self.is_focused else 1)
        painter.setPen(pen)
        painter.drawPath(path)

        # Вызываем стандартную отрисовку текста
        painter.end()
        super().paintEvent(event)

    def focusInEvent(self, event):
        self.is_focused = True
        self.animate_border_color(self.color_primary)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.is_focused = False
        self.animate_border_color(self.color_secondary)
        super().focusOutEvent(event)

    def animate_border_color(self, target_color: str):
        self.timer = QTimer()
        self.steps = 20
        self.current_step = 0

        self.start_color = QColor(self.current_border_color)
        self.end_color = QColor(target_color)

        self.timer.timeout.connect(self.update_border_color)
        self.timer.start(15)

    def update_border_color(self):
        if self.current_step >= self.steps:
            self.timer.stop()
            return

        ratio = self.current_step / self.steps
        r = int(self.start_color.red() + (self.end_color.red() - self.start_color.red()) * ratio)
        g = int(self.start_color.green() + (self.end_color.green() - self.start_color.green()) * ratio)
        b = int(self.start_color.blue() + (self.end_color.blue() - self.start_color.blue()) * ratio)

        self.current_border_color = QColor(r, g, b).name()
        self.update()

        self.current_step += 1