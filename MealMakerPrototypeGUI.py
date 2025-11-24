"""
Meal Maker app
- Home (ingredient input + mic)
- Results (top-N cards)
- Details (recipe view + Cook This)
- Loading spinner animation
- Offline voice-to-text via Vosk+sounddevice (optional)
- Uses a local suggest_recipes(...) function (replace or import your own)
"""

import sys
import typing
import threading
import queue
import time

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QRect, QTimer, pyqtSignal, QObject, QThread
)
from PyQt6.QtGui import QFont, QPainter, QColor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QHBoxLayout, QScrollArea, QFrame, QStackedLayout, QMessageBox, QSizePolicy
)

# Attempt to import optional speech libs
try:
    import sounddevice as sd
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except Exception:
    VOSK_AVAILABLE = False

# -----------------------
# Replace or import your real model & recipe DB here.
# For standalone run this file contains a small example DB and the
# same suggest_recipes(...) function used earlier.
# If you already have `model`, `recipe_embeddings`, `recipes`, keep them
# in a separate module and import them instead.
# -----------------------
try:
    # If you already have these globals in another module, import them:
    # from my_recommender import model, recipe_embeddings, recipes, util
    raise ImportError  # remove this line if you do import above
except ImportError:
    # Fallback example: small recipe DB + dummy sentence-transformers usage
    recipes = [
        {
            "name": "Vegetable Omelette",
            "ingredients": ["eggs", "onion", "tomato", "spinach", "salt", "pepper"],
            "instructions": "Whisk eggs. Cook chopped veggies in a pan. Add eggs and fold.",
            "tags": ["breakfast", "fast", "healthy"]
        },
        {
            "name": "Pasta with Tomato Sauce",
            "ingredients": ["pasta", "tomato", "garlic", "olive oil", "salt", "basil"],
            "instructions": "Boil pasta. Simmer garlic and tomato sauce. Mix.",
            "tags": ["lunch", "easy"]
        },
        {
            "name": "Mexican Chicken Tacos",
            "ingredients": ["chicken", "tortillas", "onion", "cilantro", "lime"],
            "instructions": "Sauté chicken. Warm tortillas. Add toppings.",
            "tags": ["latin", "protein"]
        },
        {
            "name": "Lentil Soup",
            "ingredients": ["lentils", "carrot", "onion", "celery", "garlic", "salt"],
            "instructions": "Simmer all ingredients for 30 min.",
            "tags": ["vegan", "cheap", "batch-cooking"]
        },
        {
            "name": "Fried Rice",
            "ingredients": ["rice", "egg", "carrot", "pea", "soy sauce", "onion"],
            "instructions": "Stir fry ingredients in wok.",
            "tags": ["asian", "use-leftovers"]
        },
        {
            "name": "Chicken Rice Bowl",
            "ingredients": ["rice", "chicken", "soy sauce", "carrot", "onion"],
            "instructions": "Cook rice. Stir fry chicken and veggies.",
            "tags": ["balanced"]
        },
        {
            "name": "Guacamole",
            "ingredients": ["avocado", "onion", "tomato", "lime", "cilantro", "salt"],
            "instructions": "Mash avocado. Mix chopped ingredients.",
            "tags": ["dip", "healthy", "snack"]
        },
        {
            "name": "Greek Salad",
            "ingredients": ["tomato", "cucumber", "olive oil", "onion", "feta", "oregano"],
            "instructions": "Chop and mix all ingredients.",
            "tags": ["veggie", "fresh", "low-cal"]
        },
        {
            "name": "Fruit Yogurt Bowl",
            "ingredients": ["yogurt", "banana", "berries", "honey", "granola"],
            "instructions": "Layer yogurt, fruit and granola.",
            "tags": ["breakfast", "healthy"]
        },
        {
            "name": "Stir-Fry Veggies",
            "ingredients": ["broccoli", "carrot", "pepper", "soy sauce", "garlic"],
            "instructions": "Stir fry on high heat.",
            "tags": ["vegan", "fast"]
        }
        ]

    # If you have sentence-transformers model already, set those here.
    # For this demo we produce simple heuristic scores by counting shared ingredients.
    def suggest_recipes(user_ingredients: typing.List[str], top_k=3):
        user_set = set(map(str.lower, [i.strip() for i in user_ingredients if i.strip()]))
        scored = []
        for r in recipes:
            r_set = set(map(str.lower, r["ingredients"]))
            overlap = len(user_set & r_set)
            # score: fraction of recipe ingredients present + small length penalty
            score = overlap / max(1, len(r_set))
            scored.append({"name": r["name"], "score": float(score), "ingredients": r["ingredients"], "instructions": r["instructions"]})
        # sort by score desc
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

# -----------------------
# Worker for recipe search using QThread
# -----------------------
class SearchWorker(QObject):
    finished = pyqtSignal(list)     # emits results
    error = pyqtSignal(str)

    def __init__(self, ingredients):
        super().__init__()
        self.ingredients = ingredients

    def run(self):
        try:
            results = suggest_recipes(self.ingredients, top_k=3)
            time.sleep(0.35)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))

# -----------------------
# Utilities and small UI widgets
# -----------------------
class Spinner(QWidget):
    """Simple rotating spinner drawn with QPainter."""
    def __init__(self, diameter=80, parent=None):
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(30)  # ~33 FPS

    def advance(self):
        self.angle = (self.angle + 6) % 360
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        center = r.center()
        radius = min(r.width(), r.height())/2 - 6
        p.translate(center)
        p.rotate(self.angle)
        # draw 8 arcs with varying alpha
        for i in range(8):
            col = QColor(255, 138, 64)
            col.setAlpha(int(255 * (i+1)/8))
            p.setBrush(col)
            p.setPen(Qt.PenStyle.NoPen)
            # draw small rounded rects around circle
            p.save()
            p.rotate(i * (360/8))
            p.drawRoundedRect(
                int(radius - 8),
                int(-6),
                int(16),
                int(12),
                6,
                6
            )
            p.restore()
        p.end()


class ClickableCard(QFrame):
    clicked = pyqtSignal(object)  # emits recipe dict

    def __init__(self, recipe: dict, parent=None):
        super().__init__(parent)
        self.recipe = recipe
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 14px;
                border: 1px solid #ddd;
            }
            QLabel { font-family: 'Segoe UI'; }
        """)
        self.setFixedHeight(110)
        layout = QVBoxLayout(self)
        title = QLabel(recipe["name"])
        title.setStyleSheet("font-size:16px; font-weight:600;")
        layout.addWidget(title)
        score = QLabel(f"Match: {int(recipe.get('score',0)*100)}%")
        score.setStyleSheet("color:#E66A00; font-weight:600;")
        ing = QLabel("Ingredients: " + ", ".join(recipe["ingredients"]))
        ing.setWordWrap(True)
        ing.setStyleSheet("color:#444; font-size:12px;")
        layout.addWidget(score)
        layout.addWidget(ing)

    def mousePressEvent(self, ev):
        self.clicked.emit(self.recipe)


# -----------------------
# Worker for voice capture using Vosk (runs in thread)
# -----------------------
class VoskWorker(QObject):
    recognized = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, model_path: str):
        super().__init__()
        self._stop = False
        self.model_path = model_path

    def stop(self):
        self._stop = True

    def run(self):
        if not VOSK_AVAILABLE:
            self.error.emit("Vosk or sounddevice not installed.")
            return
        try:
            model = Model(self.model_path)
        except Exception as e:
            self.error.emit(f"Failed to load Vosk model: {e}")
            return
        # sample rate and block size
        samplerate = 16000
        try:
            rec = KaldiRecognizer(model, samplerate)
            with sd.RawInputStream(samplerate=samplerate, blocksize=8000, dtype='int16',
                                   channels=1) as stream:
                while not self._stop:
                    data = stream.read(4000)[0]
                    if len(data) == 0:
                        continue
                    if rec.AcceptWaveform(data):
                        res = rec.Result()
                        import json
                        txt = json.loads(res).get("text", "")
                        if txt:
                            self.recognized.emit(txt)
                            break
                    else:
                        # partial = rec.PartialResult()
                        pass
        except Exception as e:
            self.error.emit(f"Audio capture error: {e}")


# -----------------------
# Pages
# -----------------------
class HomePage(QWidget):
    start_search = pyqtSignal(str)       # emits ingredient string
    start_listen = pyqtSignal()          # request to start voice capture

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("🍽️ Meal Maker")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:22px; font-weight:700;")
        layout.addWidget(title)

        subtitle = QLabel("What ingredients do you have?")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size:13px; color:#444;")
        layout.addWidget(subtitle)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("e.g., eggs, tomato, onion...")
        self.input_box.setStyleSheet("""
            QLineEdit {
                padding:10px; border-radius:12px; background:white;
            }
        """)
        layout.addWidget(self.input_box)

        btn_row = QHBoxLayout()
        self.find_btn = QPushButton("Find Recipes")
        self.find_btn.setStyleSheet("padding:10px; border-radius:10px; background:#FF8C42; color:white; font-weight:600;")
        self.find_btn.clicked.connect(self.on_find)
        btn_row.addWidget(self.find_btn)

        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setFixedSize(58, 58)
        self.mic_btn.setStyleSheet("border-radius:29px; background:#FF6A00; color:white; font-size:20px;")
        self.mic_btn.clicked.connect(lambda: self.start_listen.emit())
        btn_row.addWidget(self.mic_btn)

        layout.addLayout(btn_row)
        layout.addStretch()

    def on_find(self):
        text = self.input_box.text()
        if not text.strip():
            QMessageBox.warning(self, "Empty", "Please type some ingredients or use the mic.")
            return
        self.start_search.emit(text)


class ResultsPage(QWidget):
    show_details = pyqtSignal(dict)   # recipe dict
    back = pyqtSignal()

    def __init__(self):
        super().__init__()
        main = QVBoxLayout(self)
        top_row = QHBoxLayout()
        self.back_btn = QPushButton("← Back")
        self.back_btn.clicked.connect(lambda: self.back.emit())
        top_row.addWidget(self.back_btn)
        self.title = QLabel("Results")
        self.title.setStyleSheet("font-size:18px; font-weight:700;")
        top_row.addWidget(self.title)
        main.addLayout(top_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(8, 8, 8, 8)
        self.vbox.setSpacing(12)
        self.scroll.setWidget(self.container)
        main.addWidget(self.scroll)

    def set_results(self, items: typing.List[dict]):
        # Clear
        for i in reversed(range(self.vbox.count())):
            w = self.vbox.itemAt(i).widget()
            if w:
                w.setParent(None)

        for r in items:
            card = ClickableCard(r)
            card.clicked.connect(lambda rec: self.show_details.emit(rec))
            self.vbox.addWidget(card)
        self.vbox.addStretch()


class DetailsPage(QWidget):
    back = pyqtSignal()
    cook = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        top_row = QHBoxLayout()
        self.back_btn = QPushButton("← Back")
        self.back_btn.clicked.connect(lambda: self.back.emit())
        top_row.addWidget(self.back_btn)
        layout.addLayout(top_row)

        self.title = QLabel("Recipe")
        self.title.setStyleSheet("font-size:20px; font-weight:700;")
        layout.addWidget(self.title)

        self.ingredients_label = QLabel()
        self.ingredients_label.setWordWrap(True)
        layout.addWidget(self.ingredients_label)

        self.instructions_label = QLabel()
        self.instructions_label.setWordWrap(True)
        layout.addWidget(self.instructions_label)

        self.cook_btn = QPushButton("Cook This")
        self.cook_btn.setStyleSheet("padding:12px; border-radius:10px; background:#4CAF50; color:white; font-weight:700;")
        self.cook_btn.clicked.connect(self.on_cook)
        layout.addWidget(self.cook_btn)
        layout.addStretch()

        self.current_recipe = None

    def set_recipe(self, recipe: dict):
        self.current_recipe = recipe
        self.title.setText(recipe["name"])
        self.ingredients_label.setText("Ingredients:\n • " + "\n • ".join(recipe["ingredients"]))
        self.instructions_label.setText("Instructions:\n" + recipe.get("instructions", ""))

    def on_cook(self):
        if self.current_recipe:
            self.cook.emit(self.current_recipe)
            QMessageBox.information(self, "Let's cook!", f"Ready to cook {self.current_recipe['name']} — good luck!")


# -----------------------
# Main app shell with navigation and loading overlay
# -----------------------
class MealMakerShell(QWidget):
    def __init__(self, vosk_model_path: str = None):
        super().__init__()
        self.setWindowTitle("Meal Maker")
        self.setFixedSize(390, 760)
        self.setStyleSheet("""
            QWidget {
                background-color: #000000;
                color: white;
                font-family: 'Segoe UI';
            }
            QLineEdit {
                background-color: #222;
                color: #000000;
                border: 2px solid #444;
                border-radius: 12px;
                padding: 10px;
            }
            QPushButton {
                background-color: #444;
                color: white;
                border-radius: 12px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #555;
            }
        """)


        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Stacked layout for pages
        self.stack = QStackedLayout()
        self.home = HomePage()
        self.results = ResultsPage()
        self.details = DetailsPage()

        self.stack.addWidget(self.home)
        self.stack.addWidget(self.results)
        self.stack.addWidget(self.details)

        layout.addLayout(self.stack)

        # Loading overlay
        self.loading_overlay = QFrame(self)
        self.loading_overlay.setStyleSheet("background: rgba(0,0,0,0.35); border-radius: 14px;")
        self.loading_overlay.setGeometry(40, 200, 310, 200)
        self.loading_overlay.hide()
        lo_layout = QVBoxLayout(self.loading_overlay)
        lo_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spinner = Spinner(100)
        lo_layout.addWidget(self.spinner)
        self.loading_label = QLabel("Looking for best recipes…")
        self.loading_label.setStyleSheet("color:white; font-weight:700;")
        lo_layout.addWidget(self.loading_label)

        # Connect signals
        self.home.start_search.connect(self.on_search)
        self.home.start_listen.connect(self.on_listen_request)
        self.results.back.connect(lambda: self.stack.setCurrentWidget(self.home))
        self.results.show_details.connect(self.on_show_details)
        self.details.back.connect(lambda: self.stack.setCurrentWidget(self.results))
        self.details.cook.connect(self.on_cook)

        # Voice
        self.vosk_model_path = vosk_model_path
        self.vosk_thread = None
        self.vosk_worker = None

    def show_loading(self, show=True):
        if show:
            self.loading_overlay.show()
        else:
            self.loading_overlay.hide()

    def on_search(self, ingredient_string: str):
        self.show_loading(True)

        raw = ingredient_string.lower().replace(",", " ")
        ingredients = [i.strip() for i in raw.split() if i.strip()]

        # Create thread + worker
        self.thread = QThread()
        self.worker = SearchWorker(ingredients)

        # Move worker to QThread
        self.worker.moveToThread(self.thread)

        # Connect signals
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._search_finished)
        self.worker.error.connect(self._search_error)

        # Cleanup
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        # Start
        self.thread.start()

    def _search_finished(self, results):
        formatted = []
        for r in results:
            formatted.append({
                "name": r["name"],
                "score": r["score"],
                "ingredients": r["ingredients"],
                "instructions": r.get("instructions", "")
            })

        self.results.set_results(formatted)
        self.stack.setCurrentWidget(self.results)
        self.show_loading(False)

    def _search_error(self, msg):
        self.show_loading(False)
        QMessageBox.warning(self, "Search error", msg)


    def on_show_details(self, recipe: dict):
        self.details.set_recipe(recipe)
        self.stack.setCurrentWidget(self.details)

    def on_cook(self, recipe: dict):
        # Example: when user presses Cook This; we show a short animation and message
        self.show_loading(True)
        self.loading_label.setText("Prepping your recipe…")
        def finish_cook():
            time.sleep(0.9)
            def done():
                self.show_loading(False)
                self.loading_label.setText("Looking for best recipes…")
                QMessageBox.information(self, "Done", f"All set to cook {recipe['name']} — enjoy!")
            QTimer.singleShot(0, done)
        threading.Thread(target=finish_cook).start()

    # -----------------------
    # Voice control
    # -----------------------
    def on_listen_request(self):
        # If Vosk not available or no model path, show an info dialog with fallback
        if not VOSK_AVAILABLE or not self.vosk_model_path:
            QMessageBox.information(self, "Voice input", "Offline voice not available. Please type ingredients or install Vosk + sounddevice and set a model path to enable.)")
            return

        # show loading overlay but with different label
        self.loading_label.setText("Listening… speak now")
        self.show_loading(True)

        # Prepare worker
        self.vosk_worker = VoskWorker(self.vosk_model_path)
        self.vosk_worker.recognized.connect(self._on_vosk_result)
        self.vosk_worker.error.connect(self._on_vosk_error)

        def run_worker():
            self.vosk_worker.run()
        self.vosk_thread = threading.Thread(target=run_worker, daemon=True)
        self.vosk_thread.start()

    def _on_vosk_result(self, text: str):
        # Fill input box and run search
        self.home.input_box.setText(text)
        self.show_loading(False)
        # small delay
        QTimer.singleShot(50, lambda: self.on_search(text))

    def _on_vosk_error(self, msg: str):
        self.show_loading(False)
        QMessageBox.warning(self, "Voice error", f"Voice recognition failed: {msg}")

# -----------------------
# Run
# -----------------------
def main():
    # If you want Vosk voice: set path to a downloaded Vosk model directory here.
    # Download small model manually (not handled in-app). Example folder: "model-small"
    # e.g., vosk_model_path = r"/path/to/vosk-model-small-en-us-0.15"
    vosk_model_path = None  # <-- set to str path if you installed model

    app = QApplication(sys.argv)
    shell = MealMakerShell(vosk_model_path=vosk_model_path)
    shell.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

