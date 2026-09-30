import json
import sys
import time
import traceback
import subprocess
import tempfile
import pyperclip
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QTextEdit, QPushButton,
                             QListWidget, QMessageBox, QInputDialog, QAction,
                             QLineEdit, QStyledItemDelegate, QStyle, QStyleOptionViewItem)
from PyQt5.QtCore import Qt, QTimer, QEvent, QRect, QSize
from PyQt5.QtGui import QKeySequence, QColor, QPainter, QFont, QFontMetrics, QCursor

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# ★ Tag 黑名单共享层（位于 Query 目录）
sys.path.append(os.path.join(BASE_CODING_DIR, "Financial_System", "Query"))
try:
    import tag_blacklist as TB
    TB_OK = True
except Exception as _e:
    print(f"[黑名单] 加载 tag_blacklist 失败: {_e}")
    TB = None
    TB_OK = False


def get_clipboard_content():
    try:
        content = pyperclip.paste()
        return content.strip() if content else ""
    except Exception:
        return ""


def copy2clipboard():
    try:
        if sys.platform == 'darwin':
            script = '''
            tell application "System Events"
                keystroke "c" using {command down}
            end tell
            '''
            subprocess.run(['osascript', '-e', script], check=True)
        elif sys.platform == 'win32':
            import pyautogui
            pyautogui.hotkey('ctrl', 'c')
        else:
            return False
        time.sleep(0.5)
        return True
    except Exception:
        return False


def get_stock_symbol(default_symbol=""):
    app = QApplication.instance() or QApplication(sys.argv)
    input_dialog = QInputDialog()
    input_dialog.setWindowTitle("请输入股票代码")
    input_dialog.setLabelText("请输入股票代码:")
    input_dialog.setTextValue(default_symbol)
    label = input_dialog.findChild(QLabel)
    if label:
        label.hide()
    input_dialog.setWindowFlags(input_dialog.windowFlags() | Qt.WindowStaysOnTopHint)
    input_dialog.setStyleSheet("""
        QInputDialog { background-color: #2E3440; color: #D8DEE9; }
        QLineEdit, QLabel, QPushButton {
            color: #D8DEE9; background-color: #434C5E; border: 1px solid #4C566A;
        }
        QPushButton:hover { background-color: #5E81AC; }
    """)
    input_dialog.show()
    input_dialog.activateWindow()
    input_dialog.raise_()
    if input_dialog.exec_() == QInputDialog.Accepted:
        return input_dialog.textValue().strip()
    return None


# ======================================================================
# ★ Tag 行绘制代理：左侧常驻黑名单徽章 + 悬停/选中时右侧显示操作按钮
#   （用 delegate 而不是 setItemWidget，拖拽排序时按钮不会丢失）
# ======================================================================
class TagItemDelegate(QStyledItemDelegate):
    BTN_H = 26
    BTN_GAP = 6
    PAD = 10
    ROW_MIN_H = 42

    def __init__(self, view, on_action):
        super().__init__(view)
        self.view = view
        self.on_action = on_action
        self.hover_row = -1
        self.hover_pos = None
        self.btn_font = QFont()
        self.btn_font.setPixelSize(13)
        self.btn_font.setBold(True)
        self.chip_font = QFont()
        self.chip_font.setPixelSize(12)
        self.chip_font.setBold(True)

    @staticmethod
    def actions_for(tag):
        """[(op, group, 文本, 颜色)]"""
        if not TB_OK:
            return []
        sure, maybe = TB.GROUP_SURE, TB.GROUP_MAYBE
        c = TB.GROUP_COLORS
        g = TB.group_of(tag)
        if g is None:
            return [("add", sure, f"＋{sure}", c[sure]),
                    ("add", maybe, f"＋{maybe}", c[maybe])]
        other = maybe if g == sure else sure
        return [("move", other, f"→{other}", c[other]),
                ("remove", g, f"✕ 移出{g}", "#4C566A")]

    def button_rects(self, rect, tag):
        fm = QFontMetrics(self.btn_font)
        out = []
        x = rect.right() - self.PAD
        for op, grp, label, color in reversed(self.actions_for(tag)):
            w = fm.horizontalAdvance(label) + 20
            r = QRect(x - w, rect.center().y() - self.BTN_H // 2, w, self.BTN_H)
            out.insert(0, (op, grp, label, color, r))
            x = r.left() - self.BTN_GAP
        return out

    def hit(self, index, pos):
        if not index.isValid():
            return None
        tag = index.data(Qt.DisplayRole) or ""
        for op, grp, _, _, r in self.button_rects(self.view.visualRect(index), tag):
            if r.contains(pos):
                return op, grp, tag
        return None

    def _buttons_visible(self, option, index):
        return (index.row() == self.hover_row
                or bool(option.state & QStyle.State_Selected)
                or bool(option.state & QStyle.State_MouseOver))

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width(), max(s.height(), self.ROW_MIN_H))

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        tag = opt.text or ""
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)   # 背景（hover/selected）

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = option.rect
        g = TB.group_of(tag) if TB_OK else None
        x = rect.left() + self.PAD

        if g:   # 常驻徽章
            fm = QFontMetrics(self.chip_font)
            cw = fm.horizontalAdvance(g) + 14
            chip = QRect(x, rect.center().y() - 10, cw, 20)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(TB.GROUP_COLORS[g]))
            painter.drawRoundedRect(chip, 4, 4)
            painter.setFont(self.chip_font)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(chip, Qt.AlignCenter, g)
            x = chip.right() + 8

        rects = self.button_rects(rect, tag) if (TB_OK and self._buttons_visible(option, index)) else []
        right = (rects[0][4].left() - 8) if rects else rect.right() - self.PAD
        text_rect = QRect(x, rect.top(), max(0, right - x), rect.height())

        f = QFont(opt.font)
        if g:
            f.setBold(True)
        painter.setFont(f)
        if g == (TB.GROUP_SURE if TB_OK else None):
            painter.setPen(QColor("#FF9DA4"))
        elif g:
            painter.setPen(QColor("#F0B48F"))
        else:
            painter.setPen(QColor("#ECEFF4"))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft,
                         QFontMetrics(f).elidedText(tag, Qt.ElideRight, text_rect.width()))

        for op, grp, label, col, r in rects:
            hovered = (self.hover_pos is not None and index.row() == self.hover_row
                       and r.contains(self.hover_pos))
            c = QColor(col)
            if hovered:
                c = c.lighter(130)
            painter.setPen(Qt.NoPen)
            painter.setBrush(c)
            painter.drawRoundedRect(r, 5, 5)
            painter.setFont(self.btn_font)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(r, Qt.AlignCenter, label)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if TB_OK and event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                                      QEvent.MouseButtonDblClick):
            tag = index.data(Qt.DisplayRole) or ""
            for op, grp, _, _, r in self.button_rects(option.rect, tag):
                if r.contains(event.pos()):
                    if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                        QTimer.singleShot(0, lambda o=op, g=grp, t=tag: self.on_action(o, g, t))
                    return True      # 吃掉事件：不触发选择 / 拖拽 / 编辑
        return super().editorEvent(event, model, option, index)


class TagEditor(QMainWindow):
    def __init__(self, init_symbol=None):
        super().__init__()
        self.json_file_path = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")
        self.current_item = None
        self.current_category = None
        self.original_tags = []
        self.load_json_data()

        self.setWindowTitle("标签编辑器 (支持拖拽排序 / 黑名单)")
        self.setGeometry(100 + 400, 100, 640, 720)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.quit_action = QAction("Quit", self)
        self.quit_action.setShortcut(QKeySequence("Esc"))
        self.quit_action.triggered.connect(self.close)
        self.addAction(self.quit_action)

        self.init_ui()
        self.apply_stylesheet()

        self.process_symbol(init_symbol)
        self.new_tag_input.setFocus()
        self.tags_list.setFocusPolicy(Qt.StrongFocus)

        # ★ 黑名单文件监视（Check_Group 设置 / 手动编辑后同步显示）
        self._bl_sig = TB.signature() if TB_OK else None
        self._bl_timer = QTimer(self)
        self._bl_timer.setInterval(1000)
        self._bl_timer.timeout.connect(self._poll_blacklist)
        self._bl_timer.start()
        self.refresh_blacklist_view()

    def eventFilter(self, source, event):
        # ★ Qt 虚函数里绝不能让异常漏出去，否则 PyQt 会 qFatal → abort（闪退）
        try:
            if self._handle_event(source, event):
                return True
        except Exception:
            traceback.print_exc()
        return super().eventFilter(source, event)

    def _handle_event(self, source, event):
        tags_list = getattr(self, "tags_list", None)
        new_input = getattr(self, "new_tag_input", None)
        delegate = getattr(self, "tag_delegate", None)
        if tags_list is None or new_input is None or delegate is None:
            return False          # UI 还没建完，什么都不做

        et = event.type()
        # 输入框：Enter 顶部添加 / Shift+Enter 底部添加
        if source is new_input and et == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                bottom = bool(event.modifiers() & Qt.ShiftModifier)
                QTimer.singleShot(0, lambda b=bottom: self.add_tag(bottom=b))
                return True

        # 列表：键盘操作
        if source is tags_list and et == QEvent.KeyPress and tags_list.currentItem():
            k = event.key()
            if TB_OK and k == Qt.Key_1:
                self.toggle_current_blacklist(TB.GROUP_SURE); return True
            if TB_OK and k == Qt.Key_2:
                self.toggle_current_blacklist(TB.GROUP_MAYBE); return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self.edit_current_tag(); return True
            if k in (Qt.Key_Delete, Qt.Key_Backspace):
                self.delete_current_tag(); return True

        # 列表视口：悬停跟踪
        if source is tags_list.viewport():
            if et == QEvent.MouseMove:
                idx = tags_list.indexAt(event.pos())
                delegate.hover_row = idx.row() if idx.isValid() else -1
                delegate.hover_pos = event.pos()
                over = delegate.hit(idx, event.pos()) is not None
                source.setCursor(QCursor(Qt.PointingHandCursor if over else Qt.ArrowCursor))
                source.update()
            elif et == QEvent.Leave:
                delegate.hover_row = -1
                delegate.hover_pos = None
                source.unsetCursor()
                source.update()
        return False

    def init_ui(self):
        self.symbol_label = QLabel("Symbol: ")
        self.layout.addWidget(self.symbol_label)

        self.tags_list = QListWidget()
        self.tags_list.itemDoubleClicked.connect(self.on_double_click)
        self.tags_list.setSelectionMode(QListWidget.SingleSelection)
        self.tags_list.setDragDropMode(QListWidget.InternalMove)
        self.tags_list.setDefaultDropAction(Qt.MoveAction)
        self.tags_list.setMouseTracking(True)
        self.tags_list.viewport().setMouseTracking(True)
        self.tag_delegate = TagItemDelegate(self.tags_list, self.apply_blacklist_action)
        self.tags_list.setItemDelegate(self.tag_delegate)
        self.layout.addWidget(self.tags_list)

        # 黑名单提示 + 汇总
        bl_row = QHBoxLayout()
        self.bl_hint = QLabel()
        self.bl_hint.setObjectName("hintLabel")
        self.bl_hint.setWordWrap(True)
        self.bl_hint.setText(
            "黑名单：鼠标悬停或 ↑↓ 选中 Tag → 右侧按钮加入 / 转组 / 移出（立即生效）；"
            "快捷键 1=确定  2=疑似（再按一次即移出）" if TB_OK else
            "⚠ tag_blacklist.py 未加载，黑名单功能不可用")
        bl_row.addWidget(self.bl_hint, 1)
        self.bl_file_btn = QPushButton("📝 黑名单文件")
        self.bl_file_btn.setObjectName("smallButton")
        self.bl_file_btn.setEnabled(TB_OK)
        self.bl_file_btn.clicked.connect(lambda: TB.open_in_editor() if TB_OK else None)
        bl_row.addWidget(self.bl_file_btn)
        self.layout.addLayout(bl_row)

        input_layout = QHBoxLayout()
        self.new_tag_input = QTextEdit()
        self.new_tag_input.setPlaceholderText("在此输入新标签，Enter 添加到顶部，Shift+Enter 添加到底部...")
        self.new_tag_input.setFixedHeight(80)

        add_button = QPushButton("添加标签")
        add_button.clicked.connect(lambda _=False: self.add_tag(bottom=False))
        input_layout.addWidget(self.new_tag_input)
        input_layout.addWidget(add_button)
        self.layout.addLayout(input_layout)

        buttons_layout = QHBoxLayout()
        self.bl_summary = QLabel("")
        self.bl_summary.setObjectName("hintLabel")
        buttons_layout.addWidget(self.bl_summary)
        buttons_layout.addStretch(1)
        delete_button = QPushButton("删除选中")
        save_button = QPushButton("保存并退出")
        delete_button.setObjectName("deleteButton")
        save_button.setObjectName("saveButton")
        delete_button.clicked.connect(self.delete_tag)
        save_button.clicked.connect(self.save_changes)
        buttons_layout.addWidget(delete_button)
        buttons_layout.addWidget(save_button)
        self.layout.addLayout(buttons_layout)
        # ★ 所有控件都创建完之后再装事件过滤器，避免构建过程中触发 eventFilter
        self.tags_list.installEventFilter(self)
        self.tags_list.viewport().installEventFilter(self)
        self.new_tag_input.installEventFilter(self)

    def apply_stylesheet(self):
        qss = """
        QMainWindow, QWidget { background-color: #2E3440; }
        QLabel { color: #D8DEE9; font-size: 16px; font-weight: bold; padding: 5px; }
        QLabel#hintLabel { color: #88C0D0; font-size: 12px; font-weight: normal; padding: 2px 5px; }
        QListWidget {
            background-color: #3B4252; color: #ECEFF4;
            border: 1px solid #4C566A; border-radius: 5px; font-size: 20px;
        }
        QListWidget::item { padding: 8px; }
        QListWidget::item:hover { background-color: #434C5E; }
        QListWidget::item:selected { background-color: #5E81AC; color: #ECEFF4; }
        QListWidget::drop-indicator { border: 2px dashed #A3BE8C; }
        QTextEdit {
            background-color: #3B4252; color: #ECEFF4; border: 1px solid #4C566A;
            border-radius: 5px; font-size: 14px; padding: 5px;
        }
        QTextEdit:focus { border: 1px solid #5E81AC; }
        QPushButton {
            background-color: #4C566A; color: #ECEFF4; border: none;
            padding: 10px 15px; font-size: 14px; border-radius: 5px;
        }
        QPushButton:hover { background-color: #5E81AC; }
        QPushButton:pressed { background-color: #81A1C1; }
        QPushButton:disabled { color: #777; }
        QPushButton#smallButton { padding: 5px 10px; font-size: 12px; }
        QPushButton#saveButton { background-color: #A3BE8C; font-weight: bold; }
        QPushButton#saveButton:hover { background-color: #B4D39C; }
        QPushButton#deleteButton { background-color: #BF616A; }
        QPushButton#deleteButton:hover { background-color: #D08770; }
        QStatusBar { color: #EBCB8B; font-size: 13px; }
        QScrollBar:vertical { border: none; background: #3B4252; width: 10px; margin: 0; }
        QScrollBar::handle:vertical { background: #5E81AC; min-height: 20px; border-radius: 5px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """
        self.setStyleSheet(qss)

    # ==================================================================
    # ★ 黑名单
    # ==================================================================
    def apply_blacklist_action(self, op, grp, tag):
        if not TB_OK:
            return
        try:
            if op == "remove":
                TB.set_group(tag, None)
                msg = f"已将「{tag}」移出「{grp}」黑名单"
            else:
                TB.set_group(tag, grp)
                msg = f"已将「{tag}」{'转入' if op == 'move' else '加入'}「{grp}」黑名单"
        except Exception as e:
            QMessageBox.warning(self, "黑名单写入失败", str(e))
            return
        self._bl_sig = TB.signature()
        self.refresh_blacklist_view()
        self.statusBar().showMessage(msg + "（Check_Group / Chart 约 1 秒内同步）", 5000)

    def toggle_current_blacklist(self, grp):
        it = self.tags_list.currentItem()
        if not it or not TB_OK:
            return
        tag = it.text()
        cur = TB.group_of(tag)
        if cur == grp:
            self.apply_blacklist_action("remove", grp, tag)
        else:
            self.apply_blacklist_action("move" if cur else "add", grp, tag)

    def refresh_blacklist_view(self):
        self.tags_list.viewport().update()
        if not TB_OK:
            return
        c = TB.counts()
        hits = TB.blacklisted_tags(self._ui_tags())
        txt = f"黑名单  确定 {c[TB.GROUP_SURE]} ｜ 疑似 {c[TB.GROUP_MAYBE]}"
        if hits:
            txt += f"   本股命中 {len(hits)} 个"
        if TB.last_error():
            txt += "   ⚠ 文件解析失败"
        self.bl_summary.setText(txt)

    def _poll_blacklist(self):
        if not TB_OK:
            return
        sig = TB.signature()
        if sig != self._bl_sig:
            self._bl_sig = sig
            TB.load(force=True)
            self.refresh_blacklist_view()

    # ==================================================================
    # Tag 编辑（一律以 UI 列表为准 —— 修复拖拽后按行号改错数据的 bug）
    # ==================================================================
    def _ui_tags(self):
        return [self.tags_list.item(i).text() for i in range(self.tags_list.count())]

    def save_json_data(self):
        """只在确有改动时保存；保存前重新读取磁盘最新内容，只替换当前 symbol 的 tag，原子写入"""
        if not self.current_item:
            return True
        tags = self._ui_tags()
        if tags == self.original_tags:
            return True
        symbol = self.current_item.get('symbol')
        try:
            try:
                with open(self.json_file_path, 'r', encoding='utf-8') as f:
                    fresh = json.load(f)
            except Exception:
                fresh = self.data
            target = None
            for cat in [self.current_category, 'stocks', 'etfs']:
                for it in (fresh.get(cat) or []) if cat else []:
                    if it.get('symbol') == symbol:
                        target = it
                        break
                if target is not None:
                    break
            if target is None:            # 磁盘上找不到（被别处删了）→ 退回内存数据
                fresh = self.data
                target = self.current_item
            target['tag'] = tags

            dir_ = os.path.dirname(self.json_file_path)
            fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".description.", suffix=".tmp")
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(fresh, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.json_file_path)
            except Exception:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            self.data = fresh
            self.current_item = target
            self.original_tags = list(tags)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"保存失败: {str(e)}")
            return False

    def add_tag(self, bottom=False):
        if not self.current_item:
            QMessageBox.warning(self, "警告", "没有加载任何项目，无法添加标签。")
            return
        new_tag = self.new_tag_input.toPlainText().strip()
        if not new_tag:
            self.new_tag_input.setFocus()
            return
        if new_tag in self._ui_tags():
            QMessageBox.information(self, "提示", "该标签已存在。")
            self.new_tag_input.clear()
            self.new_tag_input.setFocus()
            return
        if bottom:
            self.tags_list.addItem(new_tag)
            self.tags_list.setCurrentRow(self.tags_list.count() - 1)
        else:
            self.tags_list.insertItem(0, new_tag)
            self.tags_list.setCurrentRow(0)
        self.tags_list.scrollToItem(self.tags_list.currentItem())
        self.new_tag_input.clear()
        self.new_tag_input.setFocus()
        self.refresh_blacklist_view()
        if TB_OK and TB.group_of(new_tag):
            self.statusBar().showMessage(f"注意：「{new_tag}」在「{TB.group_of(new_tag)}」黑名单中", 5000)

    def edit_current_tag(self):
        item = self.tags_list.currentItem()
        if not item:
            return
        old_tag = item.text()
        new_tag, ok = QInputDialog.getText(self, "编辑标签", "请输入新标签:", QLineEdit.Normal, old_tag)
        new_tag = (new_tag or "").strip()
        if ok and new_tag and new_tag != old_tag:
            if new_tag in self._ui_tags():
                QMessageBox.information(self, "提示", "该标签已存在。")
                return
            item.setText(new_tag)
            self.refresh_blacklist_view()

    def delete_current_tag(self):
        item = self.tags_list.currentItem()
        if item and self.current_item:
            row = self.tags_list.row(item)
            self.tags_list.takeItem(row)
            if self.tags_list.count():
                self.tags_list.setCurrentRow(min(row, self.tags_list.count() - 1))
            self.refresh_blacklist_view()

    def show(self):
        super().show()
        self.activateWindow()
        self.raise_()
        self.new_tag_input.setFocus(Qt.OtherFocusReason)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self.new_tag_input.setFocus)

    def process_symbol(self, symbol):
        if not symbol:
            new_symbol = get_stock_symbol()
            if new_symbol:
                self.process_symbol(new_symbol)
            else:
                QTimer.singleShot(0, self.close)
            return

        original_symbol = symbol
        category, item = self.find_symbol(original_symbol)
        if not item:
            uppercase_symbol = original_symbol.upper()
            if uppercase_symbol != original_symbol:
                category, item = self.find_symbol(uppercase_symbol)

        if item:
            self.current_category = category
            self.current_item = item
            tags = item.get('tag') or []
            if isinstance(tags, str):
                tags = [tags]
            self.original_tags = [str(t) for t in tags]
            self.update_ui(item)
        else:
            new_symbol = get_stock_symbol(default_symbol=original_symbol)
            if new_symbol:
                self.process_symbol(new_symbol)
            else:
                QTimer.singleShot(0, self.close)

    def load_json_data(self):
        try:
            with open(self.json_file_path, 'r', encoding='utf-8') as file:
                self.data = json.load(file)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"加载JSON文件失败: {str(e)}")
            self.data = {"stocks": [], "etfs": []}
            QTimer.singleShot(0, self.close)

    def on_double_click(self, item):
        # 双击落在右侧黑名单按钮上时不弹编辑框
        vp = self.tags_list.viewport()
        pos = vp.mapFromGlobal(QCursor.pos())
        if self.tag_delegate.hit(self.tags_list.indexAt(pos), pos):
            return
        self.edit_current_tag()

    def find_symbol(self, symbol):
        for category in ['stocks', 'etfs']:
            for item in self.data.get(category, []):
                if item.get('symbol') == symbol:
                    return category, item
        return None, None

    def update_ui(self, item):
        self.symbol_label.setText(f"Symbol: <b>{item['symbol']}</b>")
        self.tags_list.clear()
        if self.original_tags:
            self.tags_list.addItems(self.original_tags)
        if hasattr(self, 'bl_summary'):
            self.refresh_blacklist_view()

    def delete_tag(self):
        self.delete_current_tag()

    def save_changes(self):
        if self.current_item:
            if self.save_json_data():
                self.close()
        else:
            self.close()

    def closeEvent(self, event):
        if self.current_item:
            if self.save_json_data():
                event.accept()
            else:
                reply = QMessageBox.question(
                    self, '保存失败', "数据保存失败，是否仍要关闭程序？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.Yes:
                    event.accept()
                else:
                    event.ignore()
        else:
            event.accept()


def main():
    def _excepthook(t, v, tb):
        traceback.print_exception(t, v, tb)   # 只打印，不让 PyQt 调 abort
    sys.excepthook = _excepthook
    app = QApplication(sys.argv)
    init_symbol = sys.argv[1] if len(sys.argv) > 1 else None

    if not init_symbol:
        pyperclip.copy('')
        if not copy2clipboard():
            init_symbol = get_stock_symbol()
        else:
            time.sleep(0.1)
            new_content = get_clipboard_content()
            init_symbol = new_content if new_content else get_stock_symbol()

    if not init_symbol:
        return

    editor = TagEditor(init_symbol)
    if not editor.isVisible():
        editor.show()
        sys.exit(app.exec_())


if __name__ == "__main__":
    main()