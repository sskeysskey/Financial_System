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
    当一个项目从其他列表拖入时，会发出一个自定义信号。
    """
    # 定义一个信号，参数分别为：源列表的权重, 目标列表的权重, 被移动的项目文本列表
    item_moved = pyqtSignal(str, str, list)

    def __init__(self, weight, parent=None):
        super().__init__(parent)
        self.weight = weight  # 每个列表都知道自己的权重
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        # 允许多选，方便批量删除或移动
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def dropEvent(self, event):
        source_widget = event.source()
        
        # 确保拖拽源是一个 QListWidget 且不是自己
        if isinstance(source_widget, QListWidget) and source_widget is not self:
            # 提取被拖拽的项目文本
            texts = [item.text() for item in source_widget.selectedItems()]
            
            # 发出信号，通知主窗口数据已移动
            self.item_moved.emit(source_widget.weight, self.weight, texts)
            
            # 接受事件，这样源列表才知道可以删除项目
            event.accept()
        else:
            # 如果是在同一个列表内拖拽（重新排序），则使用默认行为
            super().dropEvent(event)


# --- 主窗口类 ---
class TagEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.json_path = '/Users/yanzhang/Documents/Financial_System/Modules/tags_weight.json'  # 假设 JSON 文件在同目录下
        self.data = {}
        self.list_widgets = {}
        self.base_window_title = "标签权重编辑器"
        
        # 新增：用于跟踪数据是否被修改的“脏标记”
        self.is_dirty = False

        self.init_ui()
        self.load_data_and_populate()

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle(self.base_window_title)
        self.setGeometry(100, 100, 1000, 600)

        # --- 创建主布局 ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- 顶部操作区 (搜索和按钮) ---
        top_layout = QHBoxLayout()
        
        # 搜索框
        top_layout.addWidget(QLabel("搜索标签:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词进行过滤...")
        self.search_input.textChanged.connect(self.search_tags)
        top_layout.addWidget(self.search_input)
        
        top_layout.addStretch(1) # 添加伸缩，让按钮靠右

        # 功能按钮
        self.add_tag_btn = QPushButton("新增标签")
        self.add_tag_btn.clicked.connect(self.add_new_tag)
        top_layout.addWidget(self.add_tag_btn)

        self.add_column_btn = QPushButton("新增栏目")
        self.add_column_btn.clicked.connect(self.add_new_column)
        top_layout.addWidget(self.add_column_btn)

        # 新增：删除按钮
        self.delete_btn = QPushButton("删除选中")
        self.delete_btn.setStyleSheet("background-color: #f44336; color: white;")
        self.delete_btn.clicked.connect(self.on_delete_button_clicked)
        top_layout.addWidget(self.delete_btn)

        self.save_btn = QPushButton("保存更改")
        self.save_btn.setStyleSheet("background-color: #4CAF50; color: white;") # 突出显示
        self.save_btn.clicked.connect(self.save_data)
        top_layout.addWidget(self.save_btn)
        
        main_layout.addLayout(top_layout)

        # --- 栏目显示区 ---
        self.columns_layout = QHBoxLayout()
        main_layout.addLayout(self.columns_layout)

        # ↓—— 在 init_ui 的最后，添加：
        esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc_shortcut.activated.connect(self.close)

        # Cmd+N （Mac） 或 Ctrl+N（Windows/Linux），跨平台“新建”
        new_sc = QShortcut(QKeySequence.New, self)
        # 关键：全应用生效
        new_sc.setContext(Qt.ApplicationShortcut)
        new_sc.activated.connect(self.add_new_tag)

    def _mark_as_dirty(self):
        """将状态标记为已修改，并更新窗口标题"""
        if not self.is_dirty:
            self.is_dirty = True
            self.setWindowTitle(f"{self.base_window_title} *")

    def load_data_and_populate(self):
        """加载 JSON 数据并填充UI"""
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # 如果文件不存在或格式错误，创建一个默认的空结构
            self.data = {"1.0": []}
            QMessageBox.warning(self, "警告", f"未找到或无法解析 {self.json_path}。\n已创建一个新的空数据结构。")
            self._mark_as_dirty() # 因为创建了新数据，所以也算“脏”状态
        
        self.populate_columns()

    def populate_columns(self):
        """根据 self.data 动态创建和填充所有栏目"""
        # 清空旧的布局和控件
        for i in reversed(range(self.columns_layout.count())): 
            widget_to_remove = self.columns_layout.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.deleteLater()
        self.list_widgets.clear()

        # 根据权重排序，确保栏目顺序稳定
        sorted_weights = sorted(self.data.keys(), key=float)

        for weight in sorted_weights:
            # 每个栏目是一个独立的垂直布局（标题+列表）
            column_vbox = QVBoxLayout()
            
            # 栏目标题
            title_label = QLabel(f"权重: {weight}")
            title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
            column_vbox.addWidget(title_label)
            
            # 标签列表
            list_widget = DroppableListWidget(weight)
            list_widget.itemDoubleClicked.connect(self.edit_item) # 双击编辑
            list_widget.item_moved.connect(self.handle_item_move) # 处理跨列表拖拽
            
            # 新增：为列表启用右键菜单
            list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
            list_widget.customContextMenuRequested.connect(self.show_context_menu)
            
            for tag in self.data[weight]:
                item = QListWidgetItem(tag)
                item.setFlags(item.flags() | Qt.ItemIsEditable) # 设置为可编辑
                list_widget.addItem(item)
            
            column_vbox.addWidget(list_widget)
            
            # 将此栏目添加到主水平布局中
            container_widget = QWidget() # 需要一个容器Widget来承载VBoxLayout
            container_widget.setLayout(column_vbox)
            self.columns_layout.addWidget(container_widget)
            
            # 存储引用
            self.list_widgets[weight] = list_widget

    def search_tags(self, text):
        """根据搜索框文本过滤所有列表中的项目"""
        text = text.lower().strip()
        for list_widget in self.list_widgets.values():
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                # 如果搜索文本为空，或项目文本包含搜索文本，则显示，否则隐藏
                is_match = text in item.text().lower()
                item.setHidden(not is_match)

    def add_new_tag(self):
        """新增一个标签"""
        if not self.data:
            QMessageBox.warning(self, "操作失败", "请先至少创建一个栏目！")
            return

        # 让用户选择要添加到哪个栏目
        weights = sorted(self.data.keys(), key=float)
        weight, ok = QInputDialog.getItem(self, "选择栏目", "请选择要添加标签的权重栏目:", weights, 0, False)
        
        if ok and weight:
            # 获取新标签名
            tag, ok = QInputDialog.getText(self, "新增标签", f"在权重 {weight} 下输入新标签名:")
            if ok and tag:
                tag = tag.strip()
                # 修复：检查标签是否为空
                if not tag:
                    QMessageBox.warning(self, "新增失败", "标签名不能为空！")
                    return
                
                if any(tag in tags for tags in self.data.values()):
                    QMessageBox.warning(self, "错误", f"标签 '{tag}' 已存在于要添加的栏目中！")
                    return
                
                # 更新数据和UI
                self.data[weight].append(tag)
                item = QListWidgetItem(tag)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                self.list_widgets[weight].addItem(item)
                self._mark_as_dirty() # 标记更改

    def add_new_column(self):
        """新增一个栏目（权重）"""
        weight, ok = QInputDialog.getText(self, "新增栏目", "请输入新的权重值 (例如: 1.5):")
        if ok and weight:
            weight = weight.strip()
            try:
                # 验证输入是否为数字
                float(weight)
                if weight in self.data:
                    QMessageBox.warning(self, "错误", f"权重 '{weight}' 已存在！")
                else:
                    self.data[weight] = []
                    self.populate_columns()
                    self._mark_as_dirty() # 标记更改
            except ValueError:
                QMessageBox.warning(self, "错误", "请输入有效的数字作为权重！")

    def edit_item(self, item):
        """当项目被双击时，进入编辑模式，并在编辑后进行验证"""
        list_widget = item.listWidget()
        # 记录旧文本，以便在数据模型中找到并替换它
        old_text = item.text() 
        
        # 使用一次性连接来处理编辑完成事件
        def on_editing_finished(changed_item):
            # 确保是同一个项目触发的信号
            if changed_item is not item:
                return

            new_text = item.text().strip()
            weight = list_widget.weight
            
            # 修复：验证新标签名是否为空
            if not new_text:
                QMessageBox.warning(self, "编辑失败", "标签名不能为空！")
                item.setText(old_text) # 恢复旧文本
            else:
                # 检查新标签是否与除自身外的其他标签重复
                is_duplicate = any(new_text == t for w, tags in self.data.items() for t in tags if t != old_text)
                
                if is_duplicate:
                    QMessageBox.warning(self, "编辑失败", f"标签 '{new_text}' 已存在！")
                    item.setText(old_text) # 恢复旧文本
                else:
                    try:
                        index = self.data[weight].index(old_text)
                        self.data[weight][index] = new_text
                        self._mark_as_dirty() # 标记更改
                    except ValueError:
                        pass # 如果旧文本找不到，忽略
            
            # 断开连接，避免重复触发或内存泄漏
            try:
                list_widget.itemChanged.disconnect(on_editing_finished)
            except TypeError:
                pass

        # 在编辑前连接信号
        list_widget.itemChanged.connect(on_editing_finished)

    def keyPressEvent(self, event):
        """处理键盘事件，主要是删除键"""
        if event.key() == Qt.Key_Delete:
            # 找到当前有焦点的列表
            focused_widget = self.focusWidget()
            if isinstance(focused_widget, QListWidget):
                self.delete_selected_items(focused_widget)

    def on_delete_button_clicked(self):
        """处理顶部删除按钮的点击事件"""
        # 找出所有列表中被选中的项目
        all_selected_items = []
        for list_widget in self.list_widgets.values():
            all_selected_items.extend(list_widget.selectedItems())

        if not all_selected_items:
            QMessageBox.information(self, "提示", "请先在列表中选中要删除的项目。")
            return
        
        # 统一调用删除逻辑，只需确认一次
        self.delete_selected_items()

    def delete_selected_items(self, list_widget_context=None):
        """删除所有列表中的选中项"""
        # 如果提供了特定列表的上下文（例如来自右键菜单），则只处理该列表
        widgets_to_process = [list_widget_context] if list_widget_context else self.list_widgets.values()
        
        items_to_delete = []
        for lw in widgets_to_process:
            items_to_delete.extend(lw.selectedItems())

        if not items_to_delete:
            return

        reply = QMessageBox.question(self, '确认删除', 
                                     f"确定要删除选中的 {len(items_to_delete)} 个项目吗?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            for item in items_to_delete:
                list_widget = item.listWidget()
                weight = list_widget.weight
                list_widget.takeItem(list_widget.row(item))
                if item.text() in self.data[weight]:
                    self.data[weight].remove(item.text())
            self._mark_as_dirty() # 标记更改

    def show_context_menu(self, position):
        """显示右键上下文菜单"""
        list_widget = self.sender()
        if not list_widget.selectedItems():
            return

        menu = QMenu()
        delete_action = menu.addAction("删除选中项")
        
        action = menu.exec_(list_widget.mapToGlobal(position))

        if action == delete_action:
            # 调用删除逻辑，并传入当前列表作为上下文
            self.delete_selected_items(list_widget)

    def handle_item_move(self, source_weight, dest_weight, texts):
        """处理项目在不同列表间移动的逻辑"""
        # 1) 更新底层数据结构
        for text in texts:
            if text in self.data[source_weight]:
                self.data[source_weight].remove(text)
            if text not in self.data[dest_weight]:
                self.data[dest_weight].append(text)

        # 2) 在对应的两个 QListWidget 上局部更新
        src_list = self.list_widgets[source_weight]
        dst_list = self.list_widgets[dest_weight]
        for text in texts:
            # 从源列表移除
            for row in range(src_list.count()):
                if src_list.item(row).text() == text:
                    src_list.takeItem(row)
                    break
            # 往目标列表添加
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            dst_list.addItem(item)

        # 3) 标记为脏
        self._mark_as_dirty()

    def save_data(self, notify=True):
        """将当前数据写回 JSON 文件"""
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=4)
            
            # 保存成功后，重置“脏标记”和窗口标题
            self.is_dirty = False
            self.setWindowTitle(self.base_window_title)
            # 根据 notify 决定是否弹提示
            if notify:
                QMessageBox.information(self, "成功", "所有更改已成功保存！")
        except Exception as e:
             QMessageBox.critical(self, "错误", f"保存文件时发生错误: {e}")

    def closeEvent(self, event):
        """关闭窗口前检查是否有未保存的更改"""
        # 只有在 is_dirty 为 True 时才弹出提示
        if self.is_dirty:
            reply = QMessageBox.question(self, '退出确认',
                                         "您有未保存的更改。是否在退出前保存？",
                                         QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                         QMessageBox.Cancel)

            if reply == QMessageBox.Save:
                self.save_data(notify=False)
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else: # Cancel
                event.ignore()
        else:
            # 如果没有未保存的更改，直接接受退出事件
            event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    editor = TagEditor()
    editor.show()
    sys.exit(app.exec_())