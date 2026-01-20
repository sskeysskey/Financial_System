import sys
import json
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QInputDialog, QMessageBox, QAbstractItemView, QMenu, QShortcut
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence

# --- 自定义 QListWidget 以支持拖拽事件 ---
# 简化了 DroppableListWidget，因为它现在只处理单个文件内部的移动
class DroppableListWidget(QListWidget):
    """
    一个可接收拖拽项目的 QListWidget。
    当一个项目从其他列表拖入时，会发出一个包含源/目标栏目键和项目文本的信号。
    """
    # 定义信号，参数为：源栏目键, 目标栏目键, 被移动的项目文本列表
    item_moved = pyqtSignal(str, str, list)

    def __init__(self, key, parent=None):
        super().__init__(parent)
        self.key = key  # 栏目的键，如 "newlow", "screener"
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def dropEvent(self, event):
        source_widget = event.source()
        
        if isinstance(source_widget, DroppableListWidget) and source_widget is not self:
            texts = [item.text() for item in source_widget.selectedItems()]
            # 发出简化的信号
            self.item_moved.emit(source_widget.key, self.key, texts)
            event.accept()
        else:
            # 允许在同一列表内重新排序
            super().dropEvent(event)


# --- 主窗口类 ---
class BlacklistEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        # --- 路径管理 ---
        # 唯一的JSON文件路径
        self.blacklist_json_path = '/Users/yanzhang/Coding/Financial_System/Modules/Blacklist.json'
        # [新增] 第二个文件路径
        self.sectors_json_path = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json'
        
        # --- 数据模型 ---
        self.blacklist_data = {} 
        self.sectors_full_data = {} # [新增] 用于存储 Sectors_panel 的完整原始数据
        
        self.list_widgets = {} 
        self.base_window_title = "黑名单编辑器"
        
        self.is_dirty = False 
        self.init_ui()
        self.load_data_and_populate_ui()

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle(self.base_window_title)
        self.setGeometry(100, 100, 1200, 700)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("搜索项目:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词进行过滤...")
        self.search_input.textChanged.connect(self.search_items)
        top_layout.addWidget(self.search_input)
        
        top_layout.addStretch(1)

        self.add_item_btn = QPushButton("新增项目")
        self.add_item_btn.clicked.connect(self.add_new_item)
        top_layout.addWidget(self.add_item_btn)

        self.add_column_btn = QPushButton("新增分组")
        self.add_column_btn.clicked.connect(self.add_new_column)
        top_layout.addWidget(self.add_column_btn)

        self.delete_btn = QPushButton("删除选中")
        self.delete_btn.setStyleSheet("background-color: #f44336; color: white;")
        self.delete_btn.clicked.connect(self.on_delete_button_clicked)
        top_layout.addWidget(self.delete_btn)

        self.save_btn = QPushButton("保存全部更改")
        self.save_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        self.save_btn.clicked.connect(self.save_data)
        top_layout.addWidget(self.save_btn)
        
        main_layout.addLayout(top_layout)

        self.columns_layout = QHBoxLayout()
        main_layout.addLayout(self.columns_layout)

        # 快捷键
        QShortcut(QKeySequence(Qt.Key_Escape), self, self.close)
        QShortcut(QKeySequence.New, self, self.add_new_item)

    def _mark_as_dirty(self):
        """将状态标记为已修改，并更新窗口标题"""
        if not self.is_dirty:
            self.is_dirty = True
            self.setWindowTitle(f"{self.base_window_title} *")

    def load_data_and_populate_ui(self):
        """加载 JSON 数据并填充UI"""
        # 1. 加载主黑名单数据
        try:
            with open(self.blacklist_json_path, 'r', encoding='utf-8') as f:
                self.blacklist_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.blacklist_data = {"newlow": [], "screener": [], "etf": [], "Earning": []}
            
        # 2. [新增] 加载 Sectors 数据
        try:
            with open(self.sectors_json_path, 'r', encoding='utf-8') as f:
                self.sectors_full_data = json.load(f)
                
            # 提取 Options_zero 并转换为列表 (因为 UI 只处理列表)
            # 注意：Sectors 文件是字典结构 {"Key": "Value"}，我们只需要 Key
            if "Options_zero" in self.sectors_full_data:
                options_zero_dict = self.sectors_full_data["Options_zero"]
                # 将字典的键提取出来作为列表
                self.blacklist_data["Options_zero"] = list(options_zero_dict.keys())
            else:
                # 如果文件中没有这个键，初始化为空列表
                self.blacklist_data["Options_zero"] = []
                # 同时确保原始数据里也有这个键，防止保存时报错
                self.sectors_full_data["Options_zero"] = {}

        except (FileNotFoundError, json.JSONDecodeError):
            QMessageBox.warning(self, "警告", f"无法加载 {self.sectors_json_path}")
            self.sectors_full_data = {}
            self.blacklist_data["Options_zero"] = []

        self.populate_columns()


    def populate_columns(self):
        """根据 self.blacklist_data 动态创建和填充所有栏目"""
        # 清空旧的布局和控件
        for i in reversed(range(self.columns_layout.count())): 
            widget_to_remove = self.columns_layout.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.deleteLater()
        self.list_widgets.clear()

        # [修改] 定义固定的栏目顺序，把 Options_zero 加入进去
        column_order = ["newlow", "screener", "etf", "Earning", "Options", "Options_zero"]

        for key in self.blacklist_data:
            if key not in column_order:
                column_order.append(key)
        for key in column_order:
            if key in self.blacklist_data:
                self._create_column_widget(key, self.blacklist_data[key])

    def _create_column_widget(self, key, items):
        """辅助函数：创建一个栏目UI组件并添加到布局中"""
        column_vbox = QVBoxLayout()
        
        title_label = QLabel(f"分组: {key}")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        column_vbox.addWidget(title_label)
        
        list_widget = DroppableListWidget(key)
        list_widget.itemDoubleClicked.connect(self.edit_item)
        list_widget.item_moved.connect(self.handle_item_move)
        list_widget.keyPressEvent = lambda event, lw=list_widget: self.list_key_press_event(event, lw)
        list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        list_widget.customContextMenuRequested.connect(self.show_context_menu)
        
        for item_text in items:
            item = QListWidgetItem(item_text)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            list_widget.addItem(item)
        
        column_vbox.addWidget(list_widget)
        
        container_widget = QWidget()
        container_widget.setLayout(column_vbox)
        self.columns_layout.addWidget(container_widget)
        
        self.list_widgets[key] = list_widget

    def _is_item_duplicate(self, text, key, excluding_item=None):
        """仅在指定分组内检查项目是否重复"""
        old_text = excluding_item.text() if excluding_item else None
        
        # 只获取当前分组的列表
        target_group_items = self.blacklist_data.get(key, [])

        for existing_item in target_group_items:
            if old_text and existing_item == old_text:
                continue
            if existing_item == text:
                return True
        return False

    def search_items(self, text):
        """根据搜索框文本过滤所有列表中的项目"""
        text = text.lower().strip()
        for list_widget in self.list_widgets.values():
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                is_match = text in item.text().lower()
                item.setHidden(not is_match)

    def add_new_item(self):
        """新增一个项目到指定的栏目"""
        all_keys = list(self.blacklist_data.keys())
        if not all_keys:
            QMessageBox.warning(self, "操作失败", "请先至少创建一个分组！")
            return

        key, ok = QInputDialog.getItem(self, "选择分组", "请选择要添加项目的分组:", all_keys, 0, False)
        
        if ok and key:
            text, ok = QInputDialog.getText(self, "新增项目", f"在分组 '{key}' 下输入新项目名:")
            if ok and text:
                text = text.strip()
                if not text:
                    QMessageBox.warning(self, "新增失败", "项目名不能为空！")
                    return
                
                if self._is_item_duplicate(text, key): # 传入当前的 key
                    QMessageBox.warning(self, "错误", f"项目 '{text}' 已在分组 '{key}' 中存在！")
                    return
                
                self.blacklist_data[key].append(text)
                item = QListWidgetItem(text)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                self.list_widgets[key].addItem(item)
                self._mark_as_dirty()

    def add_new_column(self):
        """新增一个分组栏目"""
        new_key, ok = QInputDialog.getText(self, "新增分组", "请输入新的分组名称:")
        if ok and new_key:
            new_key = new_key.strip()
            if not new_key:
                QMessageBox.warning(self, "错误", "分组名不能为空！")
                return
            if new_key in self.blacklist_data:
                QMessageBox.warning(self, "错误", f"分组 '{new_key}' 已存在！")
            else:
                self.blacklist_data[new_key] = []
                self.populate_columns() # 重新渲染UI以显示新栏目
                self._mark_as_dirty()

    def edit_item(self, item):
        """当项目被双击时，进入编辑模式，并在编辑后进行验证"""
        list_widget = item.listWidget()
        old_text = item.text() 
        
        def on_editing_finished(changed_item):
            if changed_item is not item: return

            new_text = item.text().strip()
            
            if not new_text:
                QMessageBox.warning(self, "编辑失败", "项目名不能为空！")
                item.setText(old_text)
            elif self._is_item_duplicate(new_text, excluding_item=item):
                QMessageBox.warning(self, "编辑失败", f"项目 '{new_text}' 已存在！")
                item.setText(old_text)
            else:
                key = list_widget.key
                try:
                    index = self.blacklist_data[key].index(old_text)
                    self.blacklist_data[key][index] = new_text
                    self._mark_as_dirty()
                except ValueError:
                    pass
            
            try:
                list_widget.itemChanged.disconnect(on_editing_finished)
            except TypeError:
                pass

        list_widget.itemChanged.connect(on_editing_finished)

    def list_key_press_event(self, event, list_widget):
        """处理列表控件的按键事件（删除）"""
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and list_widget.selectedItems():
            self.delete_selected_items(list_widget)
        else:
            QListWidget.keyPressEvent(list_widget, event)

    def on_delete_button_clicked(self):
        """处理顶部删除按钮的点击事件"""
        all_selected_items = [item for lw in self.list_widgets.values() for item in lw.selectedItems()]
        if not all_selected_items:
            QMessageBox.information(self, "提示", "请先在列表中选中要删除的项目。")
            return
        self.delete_selected_items()

    def delete_selected_items(self, list_widget_context=None):
        """删除所有列表中的选中项"""
        widgets_to_process = [list_widget_context] if list_widget_context else self.list_widgets.values()
        items_to_delete = [item for lw in widgets_to_process for item in lw.selectedItems()]
        if not items_to_delete: return

        reply = QMessageBox.question(self, '确认删除', f"确定要删除选中的 {len(items_to_delete)} 个项目吗?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            for item in items_to_delete:
                list_widget = item.listWidget()
                key = list_widget.key
                
                list_widget.takeItem(list_widget.row(item))
                if item.text() in self.blacklist_data[key]:
                    self.blacklist_data[key].remove(item.text())
            self._mark_as_dirty()

    def show_context_menu(self, position):
        """显示右键上下文菜单"""
        list_widget = self.sender()
        if not list_widget.selectedItems(): return

        menu = QMenu()
        delete_action = menu.addAction("删除选中项")
        action = menu.exec_(list_widget.mapToGlobal(position))

        if action == delete_action:
            self.delete_selected_items(list_widget)

    def handle_item_move(self, src_key, dest_key, texts):
        """处理项目在不同列表间移动的核心逻辑（简化为移动）"""
        duplicates = [t for t in texts if t in self.blacklist_data[dest_key]]
        if duplicates:
            QMessageBox.warning(self, "重复项目", f"以下项目已存在于目标分组 '{dest_key}'，将被跳过：\n" + "\n".join(duplicates))

        texts_to_process = [t for t in texts if t not in duplicates]
        if not texts_to_process:
            return

        # 更新数据模型：从源移除，添加到目标
        for text in texts_to_process:
            if text in self.blacklist_data[src_key]:
                self.blacklist_data[src_key].remove(text)
            self.blacklist_data[dest_key].append(text)

        # 更新UI
        src_list = self.list_widgets[src_key]
        dest_list = self.list_widgets[dest_key]

        # 从源UI列表移除
        for row in range(src_list.count() - 1, -1, -1):
            if src_list.item(row).text() in texts_to_process:
                src_list.takeItem(row)
        
        # 向目标UI列表添加
        for text in texts_to_process:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            dest_list.addItem(item)
            
        self._mark_as_dirty()

    def save_data(self, notify=True):
        """将数据拆分并写回两个 JSON 文件"""
        try:
            # --- 处理 Options_zero (Sectors_panel.json) ---
            # 1. 从当前编辑的数据中取出 Options_zero 的列表
            options_zero_list = self.blacklist_data.get("Options_zero", [])
            
            # 2. 获取旧的字典数据 (为了保留原本可能存在的注释值，虽然 Options_zero 示例是空的)
            old_options_dict = self.sectors_full_data.get("Options_zero", {})
            new_options_dict = {}
            
            # 3. 重建字典：如果 Key 以前存在，保留 Value；如果是新的，Value 为空字符串
            for item in options_zero_list:
                new_options_dict[item] = old_options_dict.get(item, "")
            
            # 4. 更新完整数据对象
            self.sectors_full_data["Options_zero"] = new_options_dict
            
            # 5. 保存 Sectors_panel.json
            with open(self.sectors_json_path, 'w', encoding='utf-8') as f:
                json.dump(self.sectors_full_data, f, ensure_ascii=False, indent=4)

            # --- 处理 Blacklist.json ---
            # 1. 创建一个不包含 Options_zero 的副本用于保存到 Blacklist.json
            blacklist_to_save = self.blacklist_data.copy()
            if "Options_zero" in blacklist_to_save:
                del blacklist_to_save["Options_zero"]

            # 2. 保存 Blacklist.json
            with open(self.blacklist_json_path, 'w', encoding='utf-8') as f:
                json.dump(blacklist_to_save, f, ensure_ascii=False, indent=4)
            
            self.is_dirty = False
            self.setWindowTitle(self.base_window_title)
            if notify:
                QMessageBox.information(self, "成功", "所有更改已分别保存到两个文件中！")
                
        except Exception as e:
             QMessageBox.critical(self, "错误", f"保存文件时发生错误: {e}")


    def closeEvent(self, event):
        """关闭窗口前检查是否有未保存的更改"""
        if self.is_dirty:
            reply = QMessageBox.question(self, '退出确认',
                             "您有未保存的更改。是否在退出前保存？",
                             QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                             QMessageBox.Save)

            if reply == QMessageBox.Save:
                self.save_data(notify=False)
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    editor = BlacklistEditor()
    editor.show()
    sys.exit(app.exec_())