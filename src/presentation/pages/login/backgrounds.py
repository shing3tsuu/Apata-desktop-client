import random

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget


class BackgroundTriangle(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self.color)))

        base_width = self.width() * 0.5
        base_start = (self.width() - base_width) / 2
        triangle_height = self.height() * 0.5
        top = (self.height() - triangle_height) / 2

        triangle = QPainterPath()
        triangle.moveTo(base_start, top)
        triangle.lineTo(base_start + base_width, top)
        triangle.lineTo(self.width() / 2, top + triangle_height)
        triangle.closeSubpath()

        painter.drawPath(triangle)


class HeaderLabel(QWidget):
    def __init__(self, text: str, color_primary: str, color_text: str, parent=None):
        super().__init__(parent)
        self.text = text
        self.color_primary = color_primary
        self.color_text = color_text
        self.setFixedSize(600, 36)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.label_font = QFont("Roboto Condensed", 11)
        self.label_font.setLetterSpacing(
            QFont.SpacingType.AbsoluteSpacing,
            0.6,
        )
        self.title_font = QFont("Roboto Condensed", 13)
        self.title_font.setWeight(QFont.Weight.Bold)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        title, description = self.text.split(" - ", maxsplit=1)

        painter.setFont(self.title_font)
        painter.setPen(QColor(self.color_primary))
        baseline = (
            self.height()
            + painter.fontMetrics().ascent()
            - painter.fontMetrics().descent()
        ) // 2
        title_width = painter.fontMetrics().horizontalAdvance(title)

        painter.setFont(self.label_font)
        painter.setPen(QColor(self.color_text))
        description_text = f" - {description}"
        description_width = painter.fontMetrics().horizontalAdvance(description_text)
        start_x = (self.width() - title_width - description_width) // 2

        painter.setFont(self.title_font)
        painter.setPen(QColor(self.color_primary))
        painter.drawText(start_x, baseline, title)

        painter.setFont(self.label_font)
        painter.setPen(QColor(self.color_text))
        painter.drawText(start_x + title_width, baseline, description_text)


class UpperArtifacts(QWidget):
    def __init__(
        self,
        color_primary: str,
        color_secondary: str,
        color_inactive: str,
        parent=None,
    ):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_secondary = color_secondary
        self.color_inactive = color_inactive

        self.symbols = (
            "⠻ ⠺ ⠹ ⠸ ⠷ ⠶ ⠵ ⠴ ⠳ ⠲ ⠱ ⣿ ⠿ ⠾ ⠽ ⠼ ⠻ ⠺ ⠹ ⠸".split()
        )

        self.setFixedSize(500, 30)
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
        dark_color = QColor(self.color_inactive)

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
        self.setFixedSize(90, 150)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # Анимация
        self.horizontal_distance = 45
        self.step_size = 5
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
        pen.setWidth(4)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(self.color)))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(76, 76, 8, 8)
        painter.setPen(pen)

        if self.horizontal_visible:
            painter.drawLine(
                70 - self.horizontal_current,
                85 + self.horizontal_current,
                70,
                85,
            )

        if self.vertical_visible and self.vertical_state:
            painter.drawLine(82, 10, 82, 68)


class TopRightCorner(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(90, 150)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.horizontal_distance = 45
        self.step_size = 5
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
        pen.setWidth(4)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(self.color)))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(6, 76, 8, 8)
        painter.setPen(pen)

        if self.horizontal_visible:
            painter.drawLine(
                20 + self.horizontal_current,
                85 + self.horizontal_current,
                20,
                85,
            )

        if self.vertical_visible and self.vertical_state:
            painter.drawLine(8, 10, 8, 68)


class BottomLeftCorner(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(90, 150)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.horizontal_distance = 45
        self.step_size = 5
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
        pen.setWidth(4)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(self.color)))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(76, 55, 8, 8)
        painter.setPen(pen)

        if self.horizontal_visible:
            painter.drawLine(
                70 - self.horizontal_current,
                54 - self.horizontal_current,
                70,
                54,
            )

        if self.vertical_visible and self.vertical_state:
            painter.drawLine(82, 71, 82, 129)


class BottomRightCorner(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(90, 150)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.horizontal_distance = 45
        self.step_size = 5
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
        pen.setWidth(4)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(self.color)))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(6, 55, 8, 8)
        painter.setPen(pen)

        if self.horizontal_visible:
            painter.drawLine(
                20 + self.horizontal_current,
                54 - self.horizontal_current,
                20,
                54,
            )

        if self.vertical_visible and self.vertical_state:
            painter.drawLine(8, 71, 8, 129)
