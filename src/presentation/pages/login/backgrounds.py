import asyncio
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QFont
import random


class UpperArtifacts(QWidget):
    def __init__(
            self,
            color_primary: str,
            color_secondary: str,
            parent=None
    ):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_secondary = color_secondary

        self.symbols = "⛌ ⣿ ⠿ ⠾ ⠽ ⠼ ⠻ ⠺ ⠹ ⠸ ⠷ ⠶ ⠵ ⠴ ⠳ ⠲ ⠱ ⣿ ⠿ ⠾ ⠽ ⠼ ⠻ ⠺ ⠹ ⠸ ⠷ ⠶ ⠵ ⠴ ⠳⛌".split()

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
            if random.random() < 0.9:
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

            r = int(dark_color.red() + (primary_color.red() - dark_color.red()) * brightness)
            g = int(dark_color.green() + (primary_color.green() - dark_color.green()) * brightness)
            b = int(dark_color.blue() + (primary_color.blue() - dark_color.blue()) * brightness)

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