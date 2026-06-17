#!/usr/bin/env python3
import os, sys
os.environ['QT_IM_MODULE'] = 'xim'
os.environ['XMODIFIERS'] = '@im=fcitx'
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLineEdit, QLabel, QTextEdit
app = QApplication(sys.argv)

w = QWidget()
w.setWindowTitle("IME Test")
w.resize(400, 200)
lay = QVBoxLayout(w)
lay.addWidget(QLabel("单行输入框（QLineEdit）："))
lay.addWidget(QLineEdit())
lay.addWidget(QLabel("多行输入框（QTextEdit）："))
lay.addWidget(QTextEdit())
w.show()

sys.exit(app.exec())
