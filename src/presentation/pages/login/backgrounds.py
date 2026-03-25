import asyncio
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QTransform
import random


class UpperArtifacts(QWidget):
    def __init__(self, color_primary: str, color_secondary: str, parent=None):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_secondary = color_secondary

        self.symbols = (
            "⛌ ⣿ ⠿ ⠾ ⠽ ⠼ ⠻ ⠺ ⠹ ⠸ ⠷ ⠶ ⠵ ⠴ ⠳ ⠲ ⠱ ⣿ ⠿ ⠾ ⠽ ⠼ ⠻ ⠺ ⠹ ⠸ ⠷ ⠶ ⠵ ⠴ ⠳⛌".split()
        )

        self.setFixedSize(700, 30)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        font = QFont("Roboto", 14)
        self.setFont(font)

        self.brightness_states = [random.choice([0.0, 1.0]) for _ in self.symbols]

        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.update_states)
        self.animation_timer.start(150)

    def update_states(self):
        for i in range(1, len(self.symbols) - 1):
            if random.random() < 0.05:
                self.brightness_states[i] = random.choice([0.0, 0.75])

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self.font())

        symbol_width = self.width() // len(self.symbols)

        primary_color = QColor(self.color_primary)
        dark_color = QColor("#000000")

        for i, symbol in enumerate(self.symbols):
            if i == 0 or i == len(self.symbols) - 1:
                brightness = 1.0
            else:
                brightness = self.brightness_states[i]

            r = int(
                dark_color.red() + (primary_color.red() - dark_color.red()) * brightness
            )
            g = int(
                dark_color.green()
                + (primary_color.green() - dark_color.green()) * brightness
            )
            b = int(
                dark_color.blue()
                + (primary_color.blue() - dark_color.blue()) * brightness
            )

            color = QColor(r, g, b)
            painter.setPen(color)

            x = i * symbol_width
            y = self.height() // 2 + 5
            painter.drawText(x, y, symbol)

    def stop_animation(self):
        self.animation_timer.stop()

    def start_animation(self):
        if not self.animation_timer.isActive():
            self.animation_timer.start(150)


class TopLeftCorner(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(90, 110)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # Анимация
        self.horizontal_distance = 60
        self.step_size = 10
        self.horizontal_current = 0
        self.horizontal_visible = True

        self.vertical_visible = False
        self.vertical_blink_count = 0
        self.vertical_state = True

        self.animation_stage = "horizontal"

        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.timer.start(500)

    def animate(self):
        if self.animation_stage == "horizontal":
            self.horizontal_visible = not self.horizontal_visible

            if self.horizontal_visible:
                self.horizontal_current += self.step_size

                if self.horizontal_current >= self.horizontal_distance:
                    self.horizontal_current = self.horizontal_distance
                    self.horizontal_visible = True
                    self.animation_stage = "vertical"
                    self.vertical_visible = True

        elif self.animation_stage == "vertical":
            self.vertical_state = not self.vertical_state
            self.vertical_blink_count += 1

            if self.vertical_blink_count >= 12:
                self.vertical_state = True
                self.animation_stage = "done"
                self.timer.stop()

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor(self.color))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(self.color)))

        painter.drawRect(73, 75, 12, 10)

        if self.horizontal_visible:
            painter.drawRect(
                68 - self.horizontal_current, 83, self.horizontal_current, 2
            )

        if self.vertical_visible and self.vertical_state:
            painter.drawRect(83, 10, 2, 60)


class TopRightCorner(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(90, 110)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.horizontal_distance = 60
        self.step_size = 10
        self.horizontal_current = 0
        self.horizontal_visible = True

        self.vertical_visible = False
        self.vertical_blink_count = 0
        self.vertical_state = True

        self.animation_stage = "horizontal"

        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.timer.start(500)

    def animate(self):
        if self.animation_stage == "horizontal":
            self.horizontal_visible = not self.horizontal_visible

            if self.horizontal_visible:
                self.horizontal_current += self.step_size

                if self.horizontal_current >= self.horizontal_distance:
                    self.horizontal_current = self.horizontal_distance
                    self.horizontal_visible = True
                    self.animation_stage = "vertical"
                    self.vertical_visible = True

        elif self.animation_stage == "vertical":
            self.vertical_state = not self.vertical_state
            self.vertical_blink_count += 1

            if self.vertical_blink_count >= 12:
                self.vertical_state = True
                self.animation_stage = "done"
                self.timer.stop()

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor(self.color))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(self.color)))

        painter.drawRect(4, 75, 12, 10)

        if self.horizontal_visible:
            painter.drawRect(22, 83, self.horizontal_current, 2)

        if self.vertical_visible and self.vertical_state:
            painter.drawRect(5, 10, 2, 60)


class BottomLeftCorner(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(90, 110)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.horizontal_distance = 60
        self.step_size = 10
        self.horizontal_current = 0
        self.horizontal_visible = True

        self.vertical_visible = False
        self.vertical_blink_count = 0
        self.vertical_state = True

        self.animation_stage = "horizontal"

        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.timer.start(500)

    def animate(self):
        if self.animation_stage == "horizontal":
            self.horizontal_visible = not self.horizontal_visible

            if self.horizontal_visible:
                self.horizontal_current += self.step_size

                if self.horizontal_current >= self.horizontal_distance:
                    self.horizontal_current = self.horizontal_distance
                    self.horizontal_visible = True
                    self.animation_stage = "vertical"
                    self.vertical_visible = True

        elif self.animation_stage == "vertical":
            self.vertical_state = not self.vertical_state
            self.vertical_blink_count += 1

            if self.vertical_blink_count >= 12:
                self.vertical_state = True
                self.animation_stage = "done"
                self.timer.stop()

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor(self.color))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(self.color)))

        painter.drawRect(74, 23, 12, 10)

        if self.horizontal_visible:
            painter.drawRect(
                68 - self.horizontal_current, 25, self.horizontal_current, 2
            )

        if self.vertical_visible and self.vertical_state:
            painter.drawRect(83, 40, 2, 60)


class BottomRightCorner(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(90, 110)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.horizontal_distance = 60
        self.step_size = 10
        self.horizontal_current = 0
        self.horizontal_visible = True

        self.vertical_visible = False
        self.vertical_blink_count = 0
        self.vertical_state = True

        self.animation_stage = "horizontal"

        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.timer.start(500)

    def animate(self):
        if self.animation_stage == "horizontal":
            self.horizontal_visible = not self.horizontal_visible

            if self.horizontal_visible:
                self.horizontal_current += self.step_size

                if self.horizontal_current >= self.horizontal_distance:
                    self.horizontal_current = self.horizontal_distance
                    self.horizontal_visible = True
                    self.animation_stage = "vertical"
                    self.vertical_visible = True

        elif self.animation_stage == "vertical":
            self.vertical_state = not self.vertical_state
            self.vertical_blink_count += 1

            if self.vertical_blink_count >= 12:
                self.vertical_state = True
                self.animation_stage = "done"
                self.timer.stop()

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor(self.color))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(self.color)))

        painter.drawRect(4, 24, 12, 10)

        if self.horizontal_visible:
            painter.drawRect(22, 25, self.horizontal_current, 2)

        if self.vertical_visible and self.vertical_state:
            painter.drawRect(5, 40, 2, 60)
