from ebooklib import epub
import re
import os

def clean_and_format_text(txt_path):
    """
    清理文本并保持格式
    
    参数:
        txt_path: 输入的txt文件路径
    返回:
        清理后的文本内容
    """
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 移除所有类似于"wsj\n<document>..."的模式
        cleaned_content = re.sub(r'(?:wsj|bloomberg|ft|economist|hbr)\s*\n*<document>.*?</document>.*?(?=\n|$)', '', content)
        
        # 确保段落之间的空行得以保留
        cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)
        
        return cleaned_content.strip()
        
    except Exception as e:
        print(f"处理文本时出现错误: {str(e)}")
        return None

def txt_to_epub_with_formatting(txt_path, epub_path):
    """
    将处理后的txt转换为epub，保持格式
    
    参数:
        txt_path: txt文件路径
        epub_path: 输出的epub文件路径
    """
    try:
        # 获取清理后的内容
        content = clean_and_format_text(txt_path)
        if not content:
            return False
            
        # 创建epub书籍
        book = epub.EpubBook()
        
        # 设置元数据
        book.set_identifier('id123456')
        book.set_title(os.path.splitext(os.path.basename(txt_path))[0])
        book.set_language('zh-CN')
        
        # 将换行转换为HTML段落标签
        html_content = ''
        for paragraph in content.split('\n\n'):
            if paragraph.strip():
                html_content += f'<p>{paragraph.replace("\n", "<br/>")}</p>\n'
        
        # 创建章节
        chapter = epub.EpubHtml(title='Content',
                               file_name='content.xhtml',
                               lang='zh-CN')
        
        # 添加CSS样式以确保正确的段落间距
        style = '''
            p {
                margin: 1em 0;
                line-height: 1.5;
            }
        '''
        css = epub.EpubItem(uid="style",
                           file_name="style.css",
                           media_type="text/css",
                           content=style)
        
        book.add_item(css)
        chapter.add_item(css)
        
        chapter.content = f'<html><head></head><body>{html_content}</body></html>'
        
        # 添加章节
        book.add_item(chapter)
        
        # 创建目录
        book.toc = (epub.Link('content.xhtml', 'Content', 'content'),)
        
        # 添加导航
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # 定义阅读顺序
        book.spine = ['nav', chapter]
        
        # 生成epub
        epub.write_epub(epub_path, book, {})
        
        return True
        
    except Exception as e:
        print(f"转换过程中出现错误: {str(e)}")
        return False

# 使用示例
if __name__ == "__main__":
    txt_file = "/Users/yanzhang/Documents/News/News_24_10_26.txt"
    epub_file = "/Users/yanzhang/Documents/News/output.epub"
    
    if txt_to_epub_with_formatting(txt_file, epub_file):
        print(f"成功将 {txt_file} 转换为 {epub_file}")
    else:
        print("转换失败")