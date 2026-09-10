# Cool slate, paper-white panels, cobalt actions and teal success indicators.
# Typography: Segoe UI Variable Display / Segoe UI / Cascadia Mono.
PALETTES = {
    'light': dict(bg='#EDF2F8', panel='#FFFFFF', text='#162D46', muted='#52647B', border='#B9C8D9', accent='#205BCC', field='#F8FAFD'),
    'dark': dict(bg='#192636', panel='#22344A', text='#EAF2FC', muted='#B9C8D9', border='#62758D', accent='#205BCC', field='#192C42'),
}


def stylesheet(dark=False):
    p = PALETTES['dark' if dark else 'light']
    return '''
    QWidget {{ background: {bg}; color: {text}; font-family: 'Segoe UI'; font-size: 10pt; }}
    QDialog, QMainWindow {{ background: {bg}; }}
    QLabel {{ background: transparent; }}
    QLabel#title {{ font-family: 'Segoe UI Variable Display'; font-size: 24pt; font-weight: 650; }}
    QLabel#subtitle {{ color: {muted}; }}
    QGroupBox {{ background: {panel}; border: 1px solid {border}; border-radius: 12px;
                 margin-top: 16px; padding: 18px 14px 12px; font-weight: 600; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 16px; padding: 0 6px; }}
    QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QTableWidget {{ background: {field}; border: 1px solid {border};
                 border-radius: 6px; padding: 8px; selection-background-color: {accent}; selection-color: white; }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus, QComboBox:focus, QTableWidget:focus {{ border: 2px solid {accent}; }}
    QPushButton {{ background: {panel}; border: 1px solid {border}; padding: 9px 14px; border-radius: 7px; }}
    QPushButton:hover {{ border: 1px solid {accent}; }}
    QPushButton:focus {{ border: 2px solid {accent}; }}
    QPushButton#primary {{ color: white; background: {accent}; border: 2px solid {accent}; font-weight: 600; }}
    QPushButton#primary:focus {{ border: 2px solid {text}; }}
    QPushButton:disabled {{ color: {muted}; background: {bg}; }}
    QTabWidget::pane {{ border: 1px solid {border}; border-radius: 8px; }}
    QTabBar::tab {{ padding: 10px 15px; background: {bg}; border-bottom: 3px solid transparent; }}
    QTabBar::tab:selected {{ border-bottom-color: {accent}; font-weight: 600; }}
    QProgressBar {{ border: 1px solid {border}; border-radius: 6px; text-align: center; min-height: 21px; }}
    QProgressBar::chunk {{ background: #277E74; border-radius: 5px; }}
    QPlainTextEdit#markdownInput, QPlainTextEdit#log {{ font-family: 'Cascadia Mono'; font-size: 10pt; }}
    QHeaderView::section {{ background: {panel}; padding: 8px; border: none; color: {text}; }}
    QScrollArea {{ border: none; }}
    QCheckBox {{ spacing: 8px; padding: 4px; }}
    '''.format(**p)
