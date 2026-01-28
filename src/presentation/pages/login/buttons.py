import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer, QPropertyAnimation, QEasingCurve, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QPolygon, QPainterPath, QFont
import qasync

class ChooseButton(QWidget):
    registration_clicked = pyqtSignal()
    login_clicked = pyqtSignal()

    def __init__(
            self,
            first_text: str,
            second_text: str,
            color_primary: str,
            color_secondary: str,
            color_inactive: str = "#373737",
            parent=None
    ):
        super().__init__(parent)
        self.first_text = first_text
        self.second_text = second_text
        self.color_primary = color_primary
        self.color_secondary = color_secondary
        self.color_inactive = color_inactive

        # Состояние: "left" или "right"
        self.active_side = "left"

        # Текущие цвета для анимации
        self.left_color = color_primary
        self.right_color = color_inactive

        self.setFixedSize(700, 35)

        self.font = QFont("Roboto", 20)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        triangle_width = 10
        half_width = self.width() // 2

        # Левая половина (registration)
        left_path = QPainterPath()
        left_path.moveTo(triangle_width, 0)
        left_path.lineTo(0, self.height() / 2)
        left_path.lineTo(triangle_width, self.height())
        left_path.lineTo(half_width, self.height())
        left_path.lineTo(half_width, 0)
        left_path.lineTo(triangle_width, 0)
        left_path.closeSubpath()

        painter.fillPath(left_path, QColor(self.left_color))

        # Правая половина (login)
        right_path = QPainterPath()
        right_path.moveTo(half_width, 0)
        right_path.lineTo(half_width, self.height())
        right_path.lineTo(self.width() - triangle_width, self.height())
        right_path.lineTo(self.width(), self.height() / 2)
        right_path.lineTo(self.width() - triangle_width, 0)
        right_path.lineTo(half_width, 0)
        right_path.closeSubpath()

        painter.fillPath(right_path, QColor(self.right_color))

        # Общая обводка
        full_path = QPainterPath()
        full_path.moveTo(triangle_width, 0)
        full_path.lineTo(0, self.height() / 2)
        full_path.lineTo(triangle_width, self.height())
        full_path.lineTo(self.width() - triangle_width, self.height())
        full_path.lineTo(self.width(), self.height() / 2)
        full_path.lineTo(self.width() - triangle_width, 0)
        full_path.lineTo(triangle_width, 0)
        full_path.closeSubpath()

        pen = QPen(QColor(self.color_secondary))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(full_path)

        # Линия посередине
        painter.drawLine(half_width, 0, half_width, self.height())

        # Текст слева
        painter.setPen(QColor(self.color_secondary))
        painter.setFont(self.font)
        left_rect = QRect(triangle_width, 0, half_width - triangle_width, self.height())
        painter.drawText(left_rect, Qt.AlignmentFlag.AlignCenter, self.first_text)

        # Текст справа
        right_rect = QRect(half_width, 0, half_width - triangle_width, self.height())
        painter.drawText(right_rect, Qt.AlignmentFlag.AlignCenter, self.second_text)

    def mousePressEvent(self, event):
        half_width = self.width() // 2

        if event.pos().x() < half_width:
            # Клик на левую половину
            if self.active_side != "left":
                self.active_side = "left"
                self.animate_switch("left")
                self.registration_clicked.emit()
        else:
            # Клик на правую половину
            if self.active_side != "right":
                self.active_side = "right"
                self.animate_switch("right")
                self.login_clicked.emit()

    def animate_switch(self, target_side: str):
        self.timer = QTimer()
        self.steps = 20
        self.current_step = 0

        if target_side == "left":
            # Левая становится яркой, правая тусклой
            self.left_start = QColor(self.left_color)
            self.left_end = QColor(self.color_primary)
            self.right_start = QColor(self.right_color)
            self.right_end = QColor(self.color_inactive)
        else:
            # Правая становится яркой, левая тусклой
            self.left_start = QColor(self.left_color)
            self.left_end = QColor(self.color_inactive)
            self.right_start = QColor(self.right_color)
            self.right_end = QColor(self.color_primary)

        self.timer.timeout.connect(self.update_colors)
        self.timer.start(15)

    def update_colors(self):
        if self.current_step >= self.steps:
            self.timer.stop()
            return

        ratio = self.current_step / self.steps

        # Интерполяция левого цвета
        left_r = int(self.left_start.red() + (self.left_end.red() - self.left_start.red()) * ratio)
        left_g = int(self.left_start.green() + (self.left_end.green() - self.left_start.green()) * ratio)
        left_b = int(self.left_start.blue() + (self.left_end.blue() - self.left_start.blue()) * ratio)

        # Интерполяция правого цвета
        right_r = int(self.right_start.red() + (self.right_end.red() - self.right_start.red()) * ratio)
        right_g = int(self.right_start.green() + (self.right_end.green() - self.right_start.green()) * ratio)
        right_b = int(self.right_start.blue() + (self.right_end.blue() - self.right_start.blue()) * ratio)

        self.left_color = QColor(left_r, left_g, left_b).name()
        self.right_color = QColor(right_r, right_g, right_b).name()

        self.update()
        self.current_step += 1

class AccessButton(QPushButton):
    def __init__(
        self,
        text: str,
        color_primary: str,
        color_secondary: str,
        color_error: str
    ):
        super().__init__(text)
        self.color_primary = color_primary
        self.color_secondary = color_secondary
        self.color_error = color_error
        self.current_bg_color = color_primary

        self.setFixedSize(200, 35)

        font = QFont("Roboto", 22)
        self.setFont(font)

        self.clicked.connect(self.animate_to_red)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        triangle_width = 10

        path = QPainterPath()

        path.moveTo(triangle_width, 0)
        path.lineTo(0, self.height() / 2)
        path.lineTo(triangle_width, self.height())

        path.lineTo(self.width() - triangle_width, self.height())

        path.lineTo(self.width(), self.height() / 2)
        path.lineTo(self.width() - triangle_width, 0)

        path.lineTo(triangle_width, 0)
        path.closeSubpath()

        painter.fillPath(path, QColor(self.current_bg_color))

        pen = QPen(QColor(self.color_secondary))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)

        painter.setPen(QColor(self.color_secondary))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())

    def update_style(self, bg_color):
        self.current_bg_color = bg_color
        self.update()

    def animate_to_red(self):
        self.timer = QTimer()
        self.steps = 30
        self.current_step = 0

        self.start_color = QColor(self.color_primary)
        self.end_color = QColor("#373737")

        self.timer.timeout.connect(self.update_color)
        self.timer.start(20)

    def update_color(self):
        if self.current_step >= self.steps:
            self.timer.stop()
            return
        ratio = self.current_step / self.steps
        r = int(self.start_color.red() + (self.end_color.red() - self.start_color.red()) * ratio)
        g = int(self.start_color.green() + (self.end_color.green() - self.start_color.green()) * ratio)
        b = int(self.start_color.blue() + (self.end_color.blue() - self.start_color.blue()) * ratio)

        current_color = QColor(r, g, b)
        self.update_style(current_color.name())

        self.current_step += 1