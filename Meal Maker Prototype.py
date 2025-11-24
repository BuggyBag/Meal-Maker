import json
import numpy as np
from sentence_transformers import SentenceTransformer, util

import sys
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect
from PyQt6.QtGui import QColor, QPalette, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QHBoxLayout, QScrollArea, QFrame
)

# ------------------------------------------------------
# Core logic — ingredient input → recipe suggestions
# ------------------------------------------------------
def suggest_recipes(user_ingredients, top_k=3):
    """Returns the top-k recipe matches."""
    query = " ".join(user_ingredients)
    query_embedding = model.encode(query)

    # Compute cosine similarity
    scores = util.cos_sim(query_embedding, recipe_embeddings)[0]

    # Get top-k matches
    top_results = scores.argsort(descending=True)[:top_k]

    suggestions = []
    for idx in top_results:
        suggestions.append({
            "name": recipes[idx]["name"],
            "score": float(scores[idx]),
            "ingredients": recipes[idx]["ingredients"],
            "instructions": recipes[idx]["instructions"]
        })

    return suggestions

# ----------------------------------------------------
# Stylish mobile-like card widget
# ----------------------------------------------------
class RecipeCard(QFrame):
    def __init__(self, title, score, ingredients, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 20px;
                border: 1px solid #DDDDDD;
            }
            QLabel {
                font-family: 'Segoe UI';
            }
        """)

        layout = QVBoxLayout()
        self.setLayout(layout)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title_label)

        score_label = QLabel(f"🔥 {int(score*100)}% match")
        score_label.setStyleSheet("font-size: 14px; color: #E67300;")
        layout.addWidget(score_label)

        ing_label = QLabel("Ingredients: " + ", ".join(ingredients))
        ing_label.setStyleSheet("font-size: 13px; color: #555;")
        ing_label.setWordWrap(True)
        layout.addWidget(ing_label)

        self.setFixedHeight(120)

        # Animation
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(450)
        self.anim.setEasingCurve(QEasingCurve.Type.OutBack)

    def animate_in(self, delay, y_start, y_end):
        self.anim.setStartValue(QRect(20, y_start, 340, 120))
        self.anim.setEndValue(QRect(20, y_end, 340, 120))
        self.anim.setDuration(450 + delay)
        self.anim.start()


# ----------------------------------------------------
# Main mobile-style window
# ----------------------------------------------------
class MealMaker(QWidget):
    def __init__(self):
        super().__init__()

        # Set "phone" size
        self.setFixedSize(390, 760)
        self.setWindowTitle("Meal Maker")
        self.setStyleSheet("background-color: #000000;")

        # Main layout
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(20, 30, 20, 20)
        self.setLayout(self.layout)

        # App title
        title = QLabel("🍽️ Meal Maker")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 26px; font-weight: bold; font-family: Segoe UI;")
        self.layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("What ingredients do you have?")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 16px;")
        self.layout.addWidget(subtitle)

        # Input box
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("eggs, tomato, onion...")
        self.input_box.setStyleSheet("""
            QLineEdit {
                background: white;
                border-radius: 15px;
                padding: 12px;
                border: 2px solid #FFDDC1;
                font-size: 15px;
            }
            QLineEdit:focus {
                border: 2px solid #000000;
            }
        """)
        self.layout.addWidget(self.input_box)

        # Search button
        search_btn = QPushButton("Find Recipes")
        search_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF8C42;
                border-radius: 15px;
                padding: 12px;
                color: white;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FF7A20;
            }
        """)
        search_btn.clicked.connect(self.show_recipe_results)
        self.layout.addWidget(search_btn)

        # Scroll area for recipe cards
        self.scroll = QScrollArea()
        self.scroll.setStyleSheet("border: none;")
        self.scroll.setWidgetResizable(True)
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout()
        self.cards_container.setLayout(self.cards_layout)
        self.scroll.setWidget(self.cards_container)
        self.layout.addWidget(self.scroll)

        # Floating microphone button
        self.mic_button = QPushButton("🎤")
        self.mic_button.setStyleSheet("""
            QPushButton {
                background-color: #FF6A00;
                border-radius: 35px;
                color: white;
                font-size: 28px;
                min-width: 70px;
                min-height: 70px;
            }
        """)
        self.mic_button.setParent(self)
        self.mic_button.move(300, 650)
        self.mic_button.raise_()

        # Mic animation (pulse)
        self.mic_anim = QPropertyAnimation(self.mic_button, b"geometry")
        self.mic_anim.setDuration(1700)
        self.mic_anim.setLoopCount(-1)
        self.mic_anim.setStartValue(QRect(300, 650, 70, 70))
        self.mic_anim.setEndValue(QRect(295, 645, 80, 80))
        self.mic_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.mic_anim.start()


    # ----------------------------------------------------
    # Inject your backend recipe suggestion function here
    # ----------------------------------------------------
    def suggest(self, ingredients_string):
        # Convert GUI string to list of ingredients
        ingredients_list = [
            i.strip().lower()
            for i in ingredients_string.split(",")
            if i.strip()
        ]

        # Call your core recommendation engine
        results = suggest_recipes(ingredients_list)

        # Convert dict results → tuple format expected by GUI
        formatted = [
            (r["name"], r["score"], r["ingredients"])
            for r in results
        ]

        return formatted


    # ----------------------------------------------------
    # Display recipe cards with animation
    # ----------------------------------------------------
    def show_recipe_results(self):
        # Clear old results
        for i in reversed(range(self.cards_layout.count())):
            widget = self.cards_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        ingredients = self.input_box.text()
        results = self.suggest(ingredients)

        y_start = 800
        y_offset = 0

        # Add animated cards
        for idx, (title, score, ing) in enumerate(results):
            card = RecipeCard(title, score, ing)
            self.cards_layout.addWidget(card)
            card.animate_in(delay=idx * 200, y_start=y_start, y_end=y_offset)
            y_offset += 140

        self.cards_layout.addStretch()

# ------------------------------------------------------
# Load lightweight model (runs on low-end devices easily)
# ------------------------------------------------------
model = SentenceTransformer("all-MiniLM-L6-v2")  # ~20MB

# ------------------------------------------------------
# Example local recipe database
# ------------------------------------------------------
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

# Convert recipe ingredients into texts
recipe_texts = [" ".join(r["ingredients"]) for r in recipes]
recipe_embeddings = model.encode(recipe_texts)

# ----------------------------------------------------
# RUN APP
# ----------------------------------------------------
def run_gui():
    app = QApplication(sys.argv)
    win = MealMaker()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_gui()

