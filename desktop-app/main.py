"""
Lapwing Desktop Application
PyQt6 WebView wrapper for Live2D character
"""
import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QSystemTrayIcon, QMenu
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import (
    Qt, QUrl, pyqtSignal, pyqtSlot, QObject
)
from PyQt6.QtGui import QAction, QKeySequence, QShortcut


class LapwingBridge(QObject):
    """Bridge between Python backend and JavaScript frontend"""

    # Signals (Python -> JavaScript)
    speak_signal = pyqtSignal(str, float)  # text, eii
    expression_signal = pyqtSignal(str)  # expression name
    motion_signal = pyqtSignal(str)  # motion name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api_url = "http://localhost:8000"

    @pyqtSlot(str, result=str)
    def send_message(self, message: str) -> str:
        """Send message to Lapwing API and return response"""
        import requests
        try:
            response = requests.post(
                f"{self.api_url}/chat",
                json={"message": message},
                timeout=30
            )
            data = response.json()
            return data.get("reply", "...")
        except Exception as e:
            return f"Error: {str(e)}"

    @pyqtSlot(str, float, result=str)
    def speak_with_voice(self, text: str, eii: float) -> str:
        """Get voice URL for text"""
        import requests
        try:
            response = requests.post(
                f"{self.api_url}/tts",
                json={"text": text, "eii": eii},
                timeout=30
            )
            data = response.json()
            return data.get("audio_url", "")
        except Exception:
            return ""

    @pyqtSlot(result=str)
    def get_status(self) -> str:
        """Get Lapwing status"""
        import requests
        try:
            response = requests.get(f"{self.api_url}/health", timeout=5)
            data = response.json()
            return f"EII: {data.get('eii', 'unknown')}"
        except Exception:
            return "Disconnected"


class LapwingWindow(QMainWindow):
    """Main window for Lapwing Desktop"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lapwing Desktop")
        self.resize(450, 600)

        # Frameless, transparent, always on top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # WebView
        self.webview = QWebEngineView()
        self.webview.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Setup WebChannel for Python-JS communication
        self.channel = QWebChannel()
        self.bridge = LapwingBridge()
        self.channel.registerObject("pybridge", self.bridge)
        self.webview.page().setWebChannel(self.channel)

        # Load HTML
        html_path = Path(__file__).parent / "index.html"
        self.webview.load(QUrl.fromLocalFile(str(html_path.absolute())))

        # Layout
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.webview)
        self.setCentralWidget(container)

        # System tray
        self.setup_tray()

        # Shortcuts
        self.setup_shortcuts()

        # Drag support
        self.dragging = False
        self.drag_position = None

    def setup_tray(self):
        """Setup system tray icon"""
        self.tray = QSystemTrayIcon(self)
        # Use default icon if custom not found
        self.tray.setToolTip("Lapwing Desktop")

        menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show)
        menu.addAction(show_action)

        hide_action = QAction("Hide", self)
        hide_action.triggered.connect(self.hide)
        menu.addAction(hide_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def setup_shortcuts(self):
        """Setup global shortcuts"""
        # Ctrl+Shift+S: Show/Hide
        self.toggle_shortcut = QShortcut(
            QKeySequence("Ctrl+Shift+S"), self
        )
        self.toggle_shortcut.activated.connect(self.toggle_visibility)

        # Ctrl+Shift+Q: Quit
        self.quit_shortcut = QShortcut(
            QKeySequence("Ctrl+Shift+Q"), self
        )
        self.quit_shortcut.activated.connect(self.quit)

    def on_tray_activated(self, reason):
        """Handle tray icon click"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_visibility()

    def toggle_visibility(self):
        """Toggle window visibility"""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def quit(self):
        """Quit application"""
        self.tray.hide()
        QApplication.quit()

    # Mouse events for dragging
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.dragging = False

    def wheelEvent(self, event):
        """Zoom with mouse wheel"""
        delta = event.angleDelta().y()
        current_size = self.size()

        if delta > 0:
            # Zoom in
            new_width = int(current_size.width() * 1.1)
            new_height = int(current_size.height() * 1.1)
        else:
            # Zoom out
            new_width = int(current_size.width() * 0.9)
            new_height = int(current_size.height() * 0.9)

        # Limit size
        new_width = max(300, min(800, new_width))
        new_height = max(400, min(1000, new_height))

        self.resize(new_width, new_height)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Enable WebGL for Live2D
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--enable-webgl --ignore-gpu-blocklist"

    window = LapwingWindow()
    window.show()

    print("Lapwing Desktop started!")
    print("Shortcuts:")
    print("  Ctrl+Shift+S: Show/Hide")
    print("  Ctrl+Shift+Q: Quit")
    print("  Mouse drag: Move window")
    print("  Mouse wheel: Zoom")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
