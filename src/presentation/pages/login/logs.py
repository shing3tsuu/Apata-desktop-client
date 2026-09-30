from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QBrush
from PyQt6.QtWidgets import QWidget
import math


class LoginLogs(QWidget):
    def __init__(
        self,
        color_primary: str,
        color_secondary: str,
        color_error: str,
        color_success: str,
        color_background: str,
        parent=None,
    ):
        super().__init__(parent)

        self.color_primary = QColor(color_primary)
        self.color_secondary = QColor(color_secondary)
        self.color_error = QColor(color_error)
        self.color_success = QColor(color_success)
        self.color_background = QColor(color_background)

        self.logs = []
        self.completed_steps = 0
        self.blocks = []

        self.setFixedWidth(720)
        self.setFixedHeight(240)

        self.log_font = QFont("Roboto", 11)
        self.footer_font = QFont("Roboto", 12)

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.dot_timer = QTimer()
        self.dot_timer.timeout.connect(self._update_dot_animation)
        self.dot_timer.start(500)
        self._dot_states = [".", "..", "..."]
        self._dot_index = 0

        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(self._update_blink)
        self.blink_timer.start(30)
        self._blink_time = 0.0

    def add_log(self, text: str, is_dict: bool | None = False):
        if is_dict is False:
            self.logs.append({"base": f"► {text}:", "status": "pending"})
        else:
            self.logs.append({"base": f"▼ {text}:", "status": "pending"})
        self.blocks.append("pending")
        self.update()

    def finish_log(self, success: bool, message: str):
        if not self.logs:
            return

        log = self.logs[-1]
        if success:
            log["status"] = "success"
            log["result"] = message   # сохраняем переданное сообщение
            if self.blocks:
                self.blocks[-1] = "completed"
        else:
            log["status"] = "failure"
            log["error_message"] = message
            if self.blocks:
                self.blocks[-1] = "error"

        self.completed_steps += 1
        self.update()

    def add_info(self, text: str, indent: int = 0):
        self.logs.append({"base": " " * indent + text, "status": "info"})
        self.update()

    def clear(self):
        self.logs.clear()
        self.completed_steps = 0
        self.blocks.clear()
        self._blink_time = 0.0
        self.update()

    def _update_dot_animation(self):
        if not self.logs:
            return
        last_log = self.logs[-1]
        if last_log["status"] != "pending":
            return
        self._dot_index = (self._dot_index + 1) % len(self._dot_states)
        self.update()

    def _update_blink(self):
        if not self.blocks or self.blocks[-1] != "pending":
            return
        self._blink_time += 0.05
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        footer_height = 22

        if self.logs:
            painter.setFont(self.footer_font)
            painter.setPen(self.color_primary)

            prefix = "L O Ʌ D I N G: ﹝ "
            prefix_width = painter.fontMetrics().horizontalAdvance(prefix)
            y_footer = self.height() - footer_height + 14
            painter.drawText(10, y_footer, prefix)

            x = 10 + prefix_width
            block_width = 10
            block_height = 12
            spacing = 2

            for i, status in enumerate(self.blocks):
                if status == "error":
                    color = QColor(self.color_error)
                else:
                    color = QColor(self.color_primary)

                if i == len(self.blocks) - 1 and status == "pending":
                    alpha = int((math.sin(self._blink_time) * 0.5 + 0.5) * 255)
                    color.setAlpha(alpha)
                else:
                    color.setAlpha(255)

                painter.fillRect(
                    QRect(x + i * (block_width + spacing), y_footer - block_height, block_width, block_height),
                    QBrush(color),
                )

            painter.drawText(x + len(self.blocks) * (block_width + spacing) + 5, y_footer, "﹞")

        painter.setFont(self.log_font)

        line_height = 18
        max_lines = (self.height() - footer_height - 10) // line_height

        visible_logs = self.logs[-max_lines:]
        start_y = self.height() - footer_height - 20 - (len(visible_logs) * line_height)

        for i, log in enumerate(visible_logs):
            base = log["base"]
            status = log["status"]
            y_pos = start_y + (i + 1) * line_height

            if status == "failure":
                painter.setPen(self.color_error)
                painter.drawText(
                    10,
                    y_pos,
                    f"{base} FAILURE ({log.get('error_message', 'UNKNOWN ERROR')})",
                )
            elif status == "pending":
                painter.setPen(self.color_primary)
                suffix = self._dot_states[self._dot_index]
                painter.drawText(10, y_pos, f"{base} {suffix}")
            elif status == "info":
                painter.setPen(self.color_primary)
                painter.drawText(10, y_pos, base)
            else:  # success
                painter.setPen(self.color_primary)
                prefix_text = base + " "
                painter.drawText(10, y_pos, prefix_text)

                painter.setPen(self.color_success)
                result_text = log.get("result", "SUCCESS")
                x_offset = painter.fontMetrics().horizontalAdvance(prefix_text) + 10
                painter.drawText(x_offset, y_pos, result_text)
