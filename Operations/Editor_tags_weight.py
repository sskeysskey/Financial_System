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
# 我们需要创建一个自定义类来更好地处理从一个列表拖拽到另一个列表的逻辑
class DroppableListWidget(QListWidget):
    """
    一个可接收拖拽项目的 QListWidget。
    当一个项目从其他列表拖入时，会发出一个包含源/目标文件和栏目信息的自定义信号。
    """
    # 定义一个信号，参数分别为：源文件类型, 源栏目键, 目标文件类型, 目标栏目键, 被移动的项目文本列表
    item_moved = pyqtSignal(str, str, str, str, list)

    # 修改：__init__ 接受 file_type 和 key，使其更通用
    def __init__(self, file_type, key, parent=None):
        super().__init__(parent)
        self.file_type = file_type  # 'weight' 或 'earning'
        self.key = key              # 栏目的键，如 "1.0", "BLACKLIST_TAGS"
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def dropEvent(self, event):
        source_widget = event.source()
        
        # 确保拖拽源是一个 DroppableListWidget
        if isinstance(source_widget, DroppableListWidget):
            # 不允许在同一个列表内拖拽（除非是重新排序，由父类处理）
            if source_widget is self:
                super().dropEvent(event)
                return

            texts = [item.text() for item in source_widget.selectedItems()]
            
            # 发出包含文件类型和栏目键的信号
            self.item_moved.emit(source_widget.file_type, source_widget.key, self.file_type, self.key, texts)
            
            # 接受事件，这样源列表才知道可以删除项目（如果需要）
            event.accept()
        else:
            # 其他情况（如从外部拖入文件），忽略
            event.ignore()


# --- 主窗口类 ---
class TagEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        # --- 路径管理 ---
        self.weight_json_path = '/Users/yanzhang/Coding/Financial_System/Modules/tags_weight.json'
        self.earning_json_path = '/Users/yanzhang/Coding/Financial_System/Modules/tags_eanring.json'
        
        # --- 数据模型 ---
        self.weight_data = {}
        self.earning_data = {}

        self.list_widgets = {} # 使用唯一的 key (如 "1.0", "BLACKLIST_TAGS") 存储所有列表控件
        self.base_window_title = "标签编辑器"
        
        # 使用统一的“脏标记”跟踪两个文件是否有未保存的修改
        self.is_dirty = False

        self.init_ui()
        self.load_all_data_and_populate_ui()

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle(self.base_window_title)
        self.setGeometry(100, 100, 1200, 700) # 稍微增大窗口以容纳更多列

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("搜索标签:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词进行过滤...")
        self.search_input.textChanged.connect(self.search_tags)
        top_layout.addWidget(self.search_input)
        
        top_layout.addStretch(1)

        self.add_tag_btn = QPushButton("新增标签")
        self.add_tag_btn.clicked.connect(self.add_new_tag)
        top_layout.addWidget(self.add_tag_btn)

        self.add_column_btn = QPushButton("新增栏目")
        self.add_column_btn.clicked.connect(self.add_new_column)
        top_layout.addWidget(self.add_column_btn)

        self.delete_btn = QPushButton("删除选中")
        self.delete_btn.setStyleSheet("background-color: #f44336; color: white;")
        self.delete_btn.clicked.connect(self.on_delete_button_clicked)
        top_layout.addWidget(self.delete_btn)

        self.save_btn = QPushButton("保存全部更改")
        self.save_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        self.save_btn.clicked.connect(self.save_all_data)
        top_layout.addWidget(self.save_btn)
        
        main_layout.addLayout(top_layout)

        self.columns_layout = QHBoxLayout()
        main_layout.addLayout(self.columns_layout)

        esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc_shortcut.activated.connect(self.close)

        new_sc = QShortcut(QKeySequence.New, self)
        new_sc.setContext(Qt.ApplicationShortcut)
        new_sc.activated.connect(self.add_new_tag)

    def _mark_as_dirty(self):
        """将状态标记为已修改，并更新窗口标题"""
        if not self.is_dirty:
            self.is_dirty = True
            self.setWindowTitle(f"{self.base_window_title} *")

    def load_all_data_and_populate_ui(self):
        """加载所有 JSON 数据并填充UI"""
        # 加载 tags_weight.json
        try:
            with open(self.weight_json_path, 'r', encoding='utf-8') as f:
                self.weight_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.weight_data = {"1.0": []}
            QMessageBox.warning(self, "警告", f"未找到或无法解析 {self.weight_json_path}。\n已为此文件创建新的空数据结构。")
            self._mark_as_dirty()

        # 加载 tags_earning.json
        try:
            with open(self.earning_json_path, 'r', encoding='utf-8') as f:
                self.earning_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.earning_data = {"BLACKLIST_TAGS": [], "HOT_TAGS": []}
            QMessageBox.warning(self, "警告", f"未找到或无法解析 {self.earning_json_path}。\n已为此文件创建新的默认数据结构。")
            self._mark_as_dirty()
        
        self.populate_columns()

    def populate_columns(self):
        """根据 self.earning_data 和 self.weight_data 动态创建和填充所有栏目"""
        # 清空旧的布局和控件
        for i in reversed(range(self.columns_layout.count())): 
            widget_to_remove = self.columns_layout.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.deleteLater()
        self.list_widgets.clear()

        # --- 第一部分：填充 Earning 数据的栏目 (左侧固定) ---
        earning_keys = ["BLACKLIST_TAGS", "HOT_TAGS"]
        for key in earning_keys:
            if key in self.earning_data: # 确保key存在
                self._create_column_widget('earning', key, self.earning_data[key])
        
        # 添加一个视觉分隔符
        separator = QWidget()
        separator.setFixedWidth(20)
        self.columns_layout.addWidget(separator)

        # --- 第二部分：填充 Weight 数据的栏目 (右侧，带特殊排序) ---
        # 1) 按 float 正常排序
        sorted_weights = sorted(self.weight_data.keys(), key=float)
        # 2) 特殊排序规则
        if "2.0" in sorted_weights and "1.3" in sorted_weights:
            sorted_weights.remove("2.0")
            idx = sorted_weights.index("1.3") + 1
            sorted_weights.insert(idx, "2.0")
        if "1.5" in sorted_weights:
            sorted_weights.remove("1.5")
            sorted_weights.append("1.5")
        if "0.2" in sorted_weights:
            sorted_weights.remove("0.2")
            sorted_weights.append("0.2")

        for key in sorted_weights:
            self._create_column_widget('weight', key, self.weight_data[key])

    def _create_column_widget(self, file_type, key, tags):
        """辅助函数：创建一个栏目UI组件并添加到布局中"""
        column_vbox = QVBoxLayout()
        
        # 定义标题
        title_text = ""
        if file_type == 'earning':
            mapping = {"BLACKLIST_TAGS": "BLACKLIST_TAGS", "HOT_TAGS": "HOT_TAGS"}
            title_text = mapping.get(key, key)
        else: # weight
            mapping = {"0.2": "（待定）", "1.3": "（普遍分类）", "2.0": "（专业术语）"}
            suffix = mapping.get(key, "")
            title_text = f"权重: {key}{suffix}"
            
        title_label = QLabel(title_text)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        column_vbox.addWidget(title_label)
        
        # 创建列表
        list_widget = DroppableListWidget(file_type, key)
        list_widget.itemDoubleClicked.connect(self.edit_item)
        list_widget.item_moved.connect(self.handle_item_move)
        list_widget.keyPressEvent = lambda event, lw=list_widget: self.list_key_press_event(event, lw)
        list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        list_widget.customContextMenuRequested.connect(self.show_context_menu)
        
        for tag in tags:
            item = QListWidgetItem(tag)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            list_widget.addItem(item)
        
        column_vbox.addWidget(list_widget)
        
        container_widget = QWidget()
        container_widget.setLayout(column_vbox)
        self.columns_layout.addWidget(container_widget)
        
        self.list_widgets[key] = list_widget

    def _is_tag_duplicate(self, tag, excluding_item=None):
        """全局检查标签是否重复"""
        old_text = excluding_item.text() if excluding_item else None
        
        all_tags = [t for tags in self.weight_data.values() for t in tags] + \
                   [t for tags in self.earning_data.values() for t in tags]

        for existing_tag in all_tags:
            if old_text and existing_tag == old_text:
                continue # 跳过与自身（编辑前）的比较
            if existing_tag == tag:
                return True
        return False

    def search_tags(self, text):
        """根据搜索框文本过滤所有列表中的项目"""
        text = text.lower().strip()
        for list_widget in self.list_widgets.values():
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                is_match = text in item.text().lower()
                item.setHidden(not is_match)

    def add_new_tag(self):
        """新增一个标签到指定的栏目"""
        all_keys = list(self.earning_data.keys()) + list(self.weight_data.keys())
        if not all_keys:
            QMessageBox.warning(self, "操作失败", "请先至少创建一个栏目！")
            return

        # 让用户选择要添加到哪个栏目
        default_key = "2.0" if "2.0" in all_keys else (all_keys[0] if all_keys else "")
        default_index = all_keys.index(default_key) if default_key in all_keys else 0
        
        key, ok = QInputDialog.getItem(self, "选择栏目", "请选择要添加标签的栏目:", all_keys, default_index, False)
        
        if ok and key:
            tag, ok = QInputDialog.getText(self, "新增标签", f"在栏目 '{key}' 下输入新标签名:")
            if ok and tag:
                tag = tag.strip()
                if not tag:
                    QMessageBox.warning(self, "新增失败", "标签名不能为空！")
                    return
                
                if self._is_tag_duplicate(tag):
                    QMessageBox.warning(self, "错误", f"标签 '{tag}' 已在其他地方存在！")
                    return
                
                # 更新数据和UI
                if key in self.weight_data:
                    self.weight_data[key].append(tag)
                else:
                    self.earning_data[key].append(tag)
                    
                item = QListWidgetItem(tag)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                self.list_widgets[key].addItem(item)
                self._mark_as_dirty()

    def add_new_column(self):
        """新增一个栏目（权重或Earning类别）"""
        file_choice, ok = QInputDialog.getItem(
            self, "选择文件", "要为哪个文件新增栏目？", 
            ["tags_weight.json", "tags_earning.json"], 0, False
        )
        if not ok:
            return

        if file_choice == "tags_weight.json":
            new_key, ok = QInputDialog.getText(self, "新增权重栏目", "请输入新的权重值 (例如: 1.5):")
            if ok and new_key:
                new_key = new_key.strip()
                try:
                    float(new_key) # 验证是否为数字
                    if new_key in self.weight_data:
                        QMessageBox.warning(self, "错误", f"权重 '{new_key}' 已存在！")
                    else:
                        self.weight_data[new_key] = []
                        self.populate_columns()
                        self._mark_as_dirty()
                except ValueError:
                    QMessageBox.warning(self, "错误", "请输入有效的数字作为权重！")
        
        else: # tags_earning.json
            new_key, ok = QInputDialog.getText(self, "新增Earning栏目", "请输入新的栏目名称:")
            if ok and new_key:
                new_key = new_key.strip()
                if not new_key:
                    QMessageBox.warning(self, "错误", "栏目名不能为空！")
                    return
                if new_key in self.earning_data:
                    QMessageBox.warning(self, "错误", f"栏目 '{new_key}' 已存在！")
                else:
                    self.earning_data[new_key] = []
                    self.populate_columns()
                    self._mark_as_dirty()

    def edit_item(self, item):
        """当项目被双击时，进入编辑模式，并在编辑后进行验证"""
        list_widget = item.listWidget()
        old_text = item.text() 
        
        def on_editing_finished(changed_item):
            if changed_item is not item: return

            new_text = item.text().strip()
            
            if not new_text:
                QMessageBox.warning(self, "编辑失败", "标签名不能为空！")
                item.setText(old_text)
            elif self._is_tag_duplicate(new_text, excluding_item=item):
                QMessageBox.warning(self, "编辑失败", f"标签 '{new_text}' 已存在！")
                item.setText(old_text)
            else:
                file_type = list_widget.file_type
                key = list_widget.key
                data_dict = self.weight_data if file_type == 'weight' else self.earning_data
                try:
                    index = data_dict[key].index(old_text)
                    data_dict[key][index] = new_text
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
                file_type = list_widget.file_type
                key = list_widget.key
                data_dict = self.weight_data if file_type == 'weight' else self.earning_data
                
                list_widget.takeItem(list_widget.row(item))
                if item.text() in data_dict[key]:
                    data_dict[key].remove(item.text())
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

    def handle_item_move(self, src_file, src_key, dest_file, dest_key, texts):
        """处理项目在不同列表间移动的核心逻辑"""
        # 规则 1: 从 earning 拖拽到 weight 是不允许的
        if src_file == 'earning' and dest_file == 'weight':
            QMessageBox.warning(self, "操作无效", "不能将标签从 Earning 栏目移动或复制到 Weight 栏目。")
            # 重新填充源列表以撤销视觉上的拖拽效果
            src_list_widget = self.list_widgets[src_key]
            selected_rows = [item.listWidget().row(item) for item in src_list_widget.selectedItems()]
            for row in sorted(selected_rows, reverse=True):
                 src_list_widget.takeItem(row) # 移除
            self.populate_columns() # 简单粗暴但有效的方式恢复UI
            return

        src_data = self.weight_data if src_file == 'weight' else self.earning_data
        dest_data = self.weight_data if dest_file == 'weight' else self.earning_data
        
        # 规则 2: 同一个文件内部拖拽是“移动”
        is_move = (src_file == dest_file)
        # 规则 3: 从 weight 到 earning 是“复制”
        is_copy = (src_file == 'weight' and dest_file == 'earning')

        duplicates = [t for t in texts if t in dest_data[dest_key]]
        if duplicates:
            QMessageBox.warning(self, "重复标签", f"以下标签已存在于目标栏目 '{dest_key}'，将被跳过：\n" + "\n".join(duplicates))

        texts_to_process = [t for t in texts if t not in duplicates]
        if not texts_to_process:
            return

        # 更新数据模型
        for text in texts_to_process:
            if is_move:
                if text in src_data[src_key]:
                    src_data[src_key].remove(text)
            # 无论是移动还是复制，都需要添加到目标
            dest_data[dest_key].append(text)

        # 更新UI
        src_list = self.list_widgets[src_key]
        dest_list = self.list_widgets[dest_key]

        if is_move:
            # 从源UI列表中移除
            for row in range(src_list.count() - 1, -1, -1):
                if src_list.item(row).text() in texts_to_process:
                    src_list.takeItem(row)
        
        # 向目标UI列表添加
        for text in texts_to_process:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            dest_list.addItem(item)
            
        self._mark_as_dirty()

    def save_all_data(self, notify=True):
        """将所有数据写回对应的 JSON 文件"""
        try:
            # 保存 weight 数据
            with open(self.weight_json_path, 'w', encoding='utf-8') as f:
                json.dump(self.weight_data, f, ensure_ascii=False, indent=4)
            
            # 保存 earning 数据
            with open(self.earning_json_path, 'w', encoding='utf-8') as f:
                json.dump(self.earning_data, f, ensure_ascii=False, indent=4)
            
            self.is_dirty = False
            self.setWindowTitle(self.base_window_title)
            if notify:
                QMessageBox.information(self, "成功", "所有更改已成功保存！")
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
                self.save_all_data(notify=False)
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    editor = TagEditor()
    editor.show()
    sys.exit(app.exec_())