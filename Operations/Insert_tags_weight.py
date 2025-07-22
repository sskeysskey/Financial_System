import sys
import json
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QInputDialog, QMessageBox, QAbstractItemView
)
from PyQt5.QtCore import Qt, pyqtSignal

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
        self.list_widgets = {}  # 用于存储权重和对应的 QListWidget 的映射

        self.init_ui()
        self.load_data_and_populate()

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("标签权重编辑器")
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

        self.save_btn = QPushButton("保存更改")
        self.save_btn.setStyleSheet("background-color: #4CAF50; color: white;") # 突出显示
        self.save_btn.clicked.connect(self.save_data)
        top_layout.addWidget(self.save_btn)
        
        main_layout.addLayout(top_layout)

        # --- 栏目显示区 ---
        self.columns_layout = QHBoxLayout()
        main_layout.addLayout(self.columns_layout)

    def load_data_and_populate(self):
        """加载 JSON 数据并填充UI"""
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # 如果文件不存在或格式错误，创建一个默认的空结构
            self.data = {"1.0": []}
            QMessageBox.warning(self, "警告", f"未找到或无法解析 {self.json_path}。\n已创建一个新的空数据结构。")
        
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
            
            # 填充标签
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
                # 检查是否已存在
                if any(tag in tags for tags in self.data.values()):
                    QMessageBox.warning(self, "错误", f"标签 '{tag}' 已存在于某个栏目中！")
                    return
                
                # 更新数据和UI
                self.data[weight].append(tag)
                item = QListWidgetItem(tag)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                self.list_widgets[weight].addItem(item)

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
                    self.populate_columns() # 重新生成整个界面以保证顺序
            except ValueError:
                QMessageBox.warning(self, "错误", "请输入有效的数字作为权重！")

    def edit_item(self, item):
        """当项目被双击时，进入编辑模式"""
        # QListWidgetItem 已设为可编辑，双击会自动触发
        # 但我们需要在编辑结束后更新 self.data
        list_widget = item.listWidget()
        # 记录旧文本，以便在数据模型中找到并替换它
        old_text = item.text() 
        
        # itemChanged 信号会在编辑完成后发出，但我们无法直接获取旧值
        # 一个简单的策略是直接在编辑后重新同步整个列表的数据
        # 这里我们连接一个一次性信号处理器来更新数据
        def on_editing_finished():
            new_text = item.text()
            weight = list_widget.weight
            
            # 检查新标签是否与除自身外的其他标签重复
            is_duplicate = False
            for w, tags in self.data.items():
                for t in tags:
                    if t == new_text and t != old_text:
                        is_duplicate = True
                        break
                if is_duplicate:
                    break
            
            if is_duplicate:
                 QMessageBox.warning(self, "编辑失败", f"标签 '{new_text}' 已存在！")
                 item.setText(old_text) # 恢复旧文本
            else:
                try:
                    # 更新数据模型
                    index = self.data[weight].index(old_text)
                    self.data[weight][index] = new_text
                except ValueError:
                    # 如果旧文本找不到（不太可能发生），则忽略
                    pass
            
            # 断开这个临时连接，避免重复触发
            try:
                list_widget.itemChanged.disconnect(on_editing_finished)
            except TypeError:
                pass

        list_widget.itemChanged.connect(on_editing_finished)

    def keyPressEvent(self, event):
        """处理键盘事件，主要是删除键"""
        if event.key() == Qt.Key_Delete:
            # 找到当前有焦点的列表
            focused_widget = self.focusWidget()
            if isinstance(focused_widget, QListWidget):
                self.delete_selected_items(focused_widget)

    def delete_selected_items(self, list_widget):
        """删除指定列表中的选中项"""
        selected_items = list_widget.selectedItems()
        if not selected_items:
            return

        reply = QMessageBox.question(self, '确认删除', 
                                     f"确定要删除选中的 {len(selected_items)} 个项目吗?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            weight = list_widget.weight
            for item in selected_items:
                # 从UI中移除
                list_widget.takeItem(list_widget.row(item))
                # 从数据模型中移除
                if item.text() in self.data[weight]:
                    self.data[weight].remove(item.text())

    def handle_item_move(self, source_weight, dest_weight, texts):
        """处理项目在不同列表间移动的逻辑"""
        # 从源数据中移除
        for text in texts:
            if text in self.data[source_weight]:
                self.data[source_weight].remove(text)
        
        # 添加到目标数据中
        for text in texts:
            if text not in self.data[dest_weight]:
                self.data[dest_weight].append(text)
        
        # 从源UI中移除（因为拖拽操作会自动完成，但我们需要确保删除）
        source_list_widget = self.list_widgets[source_weight]
        # 拖拽操作后，源列表中的项目已经被移除了，我们只需要更新数据模型即可
        # 重新填充界面以确保一致性
        self.populate_columns()


    def save_data(self):
        """将当前数据写回 JSON 文件"""
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=4)
            QMessageBox.information(self, "成功", "所有更改已成功保存！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存文件时发生错误: {e}")

    def closeEvent(self, event):
        """关闭窗口前提示保存"""
        reply = QMessageBox.question(self, '退出确认',
                                     "您有未保存的更改。是否在退出前保存？",
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                     QMessageBox.Cancel)

        if reply == QMessageBox.Save:
            self.save_data()
            event.accept()
        elif reply == QMessageBox.Discard:
            event.accept()
        else:
            event.ignore()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    editor = TagEditor()
    editor.show()
    sys.exit(app.exec_())