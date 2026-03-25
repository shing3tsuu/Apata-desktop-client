from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QFont, QPen


class LoginLogs(QWidget):
    def __init__(
        self, color_primary: str, color_secondary: str, color_error: str, parent=None
    ):
        super().__init__(parent)

        self.color_primary = color_primary
        self.color_secondary = color_secondary
        self.color_error = color_error

        self.logs: list[dict] = []
        self.completed_steps: int = 0

        self.setFixedWidth(720)  # 375
        self.setFixedHeight(240)

        self.font = QFont("Roboto", 12)
        self.footer_font = QFont("Roboto", 12)

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def add_log(self, text: str):
        self.logs.append(
            {
                "text": f"▶ {text}: ...",
                "status": "pending",  # pending | success | failure
            }
        )
        self.update()

    def finish_log(self, success: bool, message: str):
        if not self.logs:
            return

        log = self.logs[-1]

        if success:
            log["text"] = log["text"].replace("...", "SUCCESS")
            log["status"] = "success"
        else:
            log["text"] = log["text"].replace("...", f"FAILURE ({message})")
            log["status"] = "failure"

        self.completed_steps += 1
        self.update()

    def clear(self):
        self.logs.clear()
        self.completed_steps = 0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # рамка
        pen = QPen(QColor(self.color_secondary))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # --- footer ---
        footer_height = 22
        if self.logs:
            painter.setFont(self.footer_font)
            painter.setPen(QColor(self.color_primary))

            painter.drawText(
                QRect(
                    10, self.height() - footer_height, self.width() - 20, footer_height
                ),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._footer_text(),
            )

        # --- logs ---
        painter.setFont(self.font)
        painter.setPen(QColor(self.color_primary))

        line_height = 18
        max_lines = (self.height() - footer_height - 10) // line_height

        visible_logs = self.logs[-max_lines:]
        start_y = self.height() - footer_height - 20 - (len(visible_logs) * line_height)

        for i, log in enumerate(visible_logs):
            if log["status"] == "failure":
                painter.setPen(QColor(self.color_error))  # COLOR_ERROR
            else:
                painter.setPen(QColor(self.color_primary))

            painter.drawText(10, start_y + (i + 1) * line_height, log["text"])

    def _footer_text(self) -> str:
        blocks = "█︎" * self.completed_steps
        return f"/ / L O Ʌ D I N G: ﹝{blocks}﹞"
