#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тёмная тема приложения (графит + синий/фиолетовый, без кислотных цветов)."""

DARK_QSS = """
QMainWindow, QWidget#page { background: #23262B; color: #E6E9EF; }
QWidget { font-size: 13px; }
QLabel { color: #E6E9EF; }
QLabel#muted { color: #9AA3B2; }
QLabel#title { font-size: 17px; font-weight: bold; }
QLabel#mono, QTextEdit#mono, QLineEdit#mono {
    font-family: "Consolas", "Courier New", monospace; font-size: 13px; }
QPushButton {
    background: #3B82F6; color: white; border: none;
    border-radius: 8px; padding: 8px 16px; font-weight: bold; }
QPushButton:hover { background: #5B98FF; }
QPushButton:pressed { background: #2F6FD6; }
QPushButton:disabled { background: #3A4048; color: #7A828E; }
QPushButton#secondary { background: #4A5160; }
QPushButton#secondary:hover { background: #5A6272; }
QPushButton#danger { background: #8A3030; }
QPushButton#danger:hover { background: #A53D3D; }
QPushButton#nav { background: transparent; color: #C6CCD6; font-weight: normal;
    text-align: left; padding: 10px 14px; border-radius: 8px; font-size: 14px; }
QPushButton#nav:hover { background: #31363E; }
QPushButton#nav:checked { background: #3B82F6; color: white; font-weight: bold; }
QTextEdit, QLineEdit, QComboBox, QSpinBox {
    background: #2B2F36; color: #E6E9EF; border: 1px solid #4A5160;
    border-radius: 8px; padding: 6px; selection-background-color: #3B82F6; }
QTextEdit:focus, QLineEdit:focus, QComboBox:focus { border: 1px solid #3B82F6; }
QComboBox QAbstractItemView { background: #2B2F36; color: #E6E9EF;
    selection-background-color: #3B82F6; }
QGroupBox { border: 1px solid #4A5160; border-radius: 8px; margin-top: 12px;
    padding-top: 8px; font-weight: bold; color: #C6CCD6; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QTableWidget, QTableView { background: #2B2F36; color: #E6E9EF;
    gridline-color: #3A4048; border: 1px solid #4A5160; border-radius: 8px;
    selection-background-color: #3B82F6; }
QHeaderView::section { background: #31363E; color: #C6CCD6; border: none; padding: 6px; }
QProgressBar { background: #2B2F36; border: 1px solid #4A5160; border-radius: 8px;
    text-align: center; color: #E6E9EF; height: 18px; }
QProgressBar::chunk { background: #8B7CF6; border-radius: 6px; }
QStatusBar { background: #1C1F24; color: #9AA3B2; }
QSplitter::handle { background: #3A4048; }
QToolTip { background: #31363E; color: #E6E9EF; border: 1px solid #4A5160; }
QScrollBar:vertical { background: #23262B; width: 12px; }
QScrollBar::handle:vertical { background: #4A5160; border-radius: 6px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QPushButton#plug { font-family: "Consolas", monospace; font-size: 14px;
    font-weight: bold; padding: 6px; min-width: 34px; }
QPushButton#plug[paired="true"] { background: #8B7CF6; }
QPushButton#plug[selected="true"] { background: #3FB96B; }
QRadioButton, QCheckBox { color: #E6E9EF; spacing: 6px; }
"""
