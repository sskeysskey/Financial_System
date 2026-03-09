// 保存 WSJ 页面待完成下载的图片下载ID，key 为 tabId
let DownloadsPending = {};

// 点击扩展图标时触发
chrome.action.onClicked.addListener(async (tab) => {
  if (
    tab.url.includes("ft.com") ||
    tab.url.includes("bloomberg.com") ||
    tab.url.includes("wsj.com") ||
    tab.url.includes("economist.com") ||
    tab.url.includes("technologyreview.com") ||
    tab.url.includes("reuters.com") ||
    tab.url.includes("nytimes.com") ||
    tab.url.includes("washingtonpost.com") ||
    tab.url.includes("asia.nikkei.com") ||
    tab.url.includes("dw.com") ||
    tab.url.includes("dw.com") ||
    tab.url.includes("bbc.com")
  ) {
    try {
      // 执行文本提取与复制操作
      const [result] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        function: extractAndCopy
      });

      if (result && result.result) { // 检查 result 是否存在
        // 显示文本复制成功通知
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          function: showNotification,
          args: ['已成功复制到剪贴板']
        });
      } else {
        // 显示复制失败通知
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          function: showNotification,
          args: ['复制失败，未找到内容或提取出错']
        });
      }
    } catch (err) {
      console.error('Script execution failed:', err);
      // 显示错误通知
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        function: showNotification,
        args: ['发生错误，请重试']
      });
    }
  }
});

// 修改后的下载图片消息监听器，增加下载完成跟踪逻辑
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'downloadImage') {
    const tabId = sender.tab ? sender.tab.id : null;
    if (tabId !== null) {
      // 初始化该 tab 的数据结构
      if (!DownloadsPending[tabId]) {
        DownloadsPending[tabId] = {
          downloads: [],
          hasStartedImageProcess: true // 标记已开始处理图片下载
        };
      } else {
        // 如果 tabId 已存在，确保 hasStartedImageProcess 也被设置
        DownloadsPending[tabId].hasStartedImageProcess = true;
      }
    }
    chrome.downloads.download({
      url: request.url,
      filename: request.filename,
      saveAs: false // 直接下载，不显示保存对话框
    }, (downloadId) => {
      if (chrome.runtime.lastError) {
        console.error(`Download failed for ${request.url}: ${chrome.runtime.lastError.message}`);
        // 可以在这里通知用户下载失败，但避免干扰已有的通知逻辑
        // 如果需要，可以向 content script 发送消息显示特定错误
        if (tabId !== null && DownloadsPending[tabId]) {
          // 尝试从队列中移除，即使没有 downloadId (不太可能发生)
          // 主要目的是为了在所有其他图片下载完成后能正确触发“全部完成”
          // 但这里没有 downloadId，所以无法精确移除
        }
        return;
      }
      if (downloadId && tabId !== null && DownloadsPending[tabId]) {
        // 将下载任务ID加入跟踪队列中
        DownloadsPending[tabId].downloads.push(downloadId);
      } else if (!downloadId && tabId !== null && DownloadsPending[tabId]) {
        // 如果下载启动失败 (没有 downloadId)，也应该处理队列
        // 这种情况比较少见，但为了健壮性可以考虑
        // 例如，如果URL无效，downloadId可能是undefined
        // 为了简单起见，我们主要依赖 onChanged 的 complete 状态
        // 但如果一个下载从未开始，它也不会完成。
        // 这种情况下，如果 DownloadsPending[tabId].downloads 最终为空，
        // 且 hasStartedImageProcess 为 true，但没有图片实际下载，
        // “所有图片下载完成”的通知可能不准确。
        // 一个更复杂的处理是记录预期下载数量。
      }
    });
  } else if (request.action === 'noImages') {
    // 处理无图片的情况
    const tabId = sender.tab ? sender.tab.id : null;
    if (tabId !== null) {
      // 检查 DownloadsPending[tabId] 是否已初始化，以及是否真的没有图片开始下载
      if (DownloadsPending[tabId] && DownloadsPending[tabId].downloads && DownloadsPending[tabId].downloads.length === 0 && DownloadsPending[tabId].hasStartedImageProcess) {
        // 如果已经标记开始处理图片，但下载队列为空，并且收到了 noImages
        // 这意味着确实没有图片被发送到下载流程
        chrome.scripting.executeScript({
          target: { tabId: tabId },
          function: showNotification,
          args: ['没有找到可下载的图片']
        });
        delete DownloadsPending[tabId]; // 清理
      } else if (!DownloadsPending[tabId] || !DownloadsPending[tabId].hasStartedImageProcess) {
        // 如果从未开始图片处理流程（例如，文本提取失败导致根本没尝试图片）
        // 或者，如果这是第一次收到 noImages 且尚未初始化 DownloadsPending
        chrome.scripting.executeScript({
          target: { tabId: tabId },
          function: showNotification,
          args: ['没有找到可下载的图片']
        });
        // 确保清理，以防万一
        if (DownloadsPending[tabId]) delete DownloadsPending[tabId];
      }
      // 如果有图片正在下载中，收到 noImages 消息（理论上不应发生），则不应显示“无图片”
    }
  }
});

// 监听下载完成后弹出通知
chrome.downloads.onChanged.addListener((delta) => {
  if (delta.state && delta.state.current === "complete") {
    chrome.downloads.search({ id: delta.id }, (results) => {
      if (results && results.length > 0) {
        const downloadItem = results[0];
        const downloadId = downloadItem.id;
        // 遍历所有页面的 tabId
        for (const tabIdStr in DownloadsPending) {
          const tabId = parseInt(tabIdStr); // 确保 tabId 是数字
          const tabData = DownloadsPending[tabIdStr];
          if (tabData && tabData.downloads) { // 确保 tabData 和 downloads 存在
            const index = tabData.downloads.indexOf(downloadId);
            if (index !== -1) {
              // 移除该下载任务ID
              tabData.downloads.splice(index, 1);
              // 如果该 tab 下所有图片都下载完成，并且我们确实为这个tab启动了图片处理流程
              if (tabData.downloads.length === 0 && tabData.hasStartedImageProcess) {
                chrome.tabs.get(tabId, (tab) => { // 检查tab是否存在
                  if (chrome.runtime.lastError || !tab) {
                    // Tab不存在或已关闭，清理并退出
                    delete DownloadsPending[tabIdStr];
                    return;
                  }
                  // Tab 存在，执行脚本
                  chrome.scripting.executeScript({
                    target: { tabId: tabId },
                    function: showNotification,
                    args: ['所有图片下载完成']
                  }).catch(err => console.error(`Error showing notification on tab ${tabId}:`, err));
                  // 清理该 tab 对应的数据
                  delete DownloadsPending[tabIdStr];
                });
              }
              break; // 已找到并处理该下载项，跳出循环
            }
          }
        }
      }
    });
  } else if (delta.state && delta.state.current === "interrupted") {
    // 处理下载中断的情况
    chrome.downloads.search({ id: delta.id }, (results) => {
      if (results && results.length > 0) {
        const downloadItem = results[0];
        const downloadId = downloadItem.id;
        for (const tabIdStr in DownloadsPending) {
          const tabId = parseInt(tabIdStr);
          const tabData = DownloadsPending[tabIdStr];
          if (tabData && tabData.downloads) {
            const index = tabData.downloads.indexOf(downloadId);
            if (index !== -1) {
              tabData.downloads.splice(index, 1); // 从队列中移除
              console.warn(`Download ${downloadId} for tab ${tabId} was interrupted.`);
              // 检查是否所有剩余（或全部）下载都已处理完毕
              if (tabData.downloads.length === 0 && tabData.hasStartedImageProcess) {
                chrome.tabs.get(tabId, (tab) => {
                  if (chrome.runtime.lastError || !tab) {
                    delete DownloadsPending[tabIdStr];
                    return;
                  }
                  chrome.scripting.executeScript({
                    target: { tabId: tabId },
                    function: showNotification,
                    args: ['部分图片下载中断，其余已完成'] // 或者更通用的消息
                  }).catch(err => console.error(`Error showing notification on tab ${tabId}:`, err));
                  delete DownloadsPending[tabIdStr];
                });
              }
              break;
            }
          }
        }
      }
    });
  }
});

function showNotification(message) {
  // 如果未添加通知相关的样式，则创建一次
  if (!document.getElementById('notification-style')) {
    const style = document.createElement('style');
    style.id = 'notification-style';
    style.textContent = `
      #notification-container {
    position: fixed;
    top: 20px;
      left: 50%;
        transform: translateX(-50%);
        z-index: 2147483647;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 10px;
      }
      .copy-notification {
        background-color: #4CAF50;
    color: white;
    padding: 12px 24px;
    border-radius: 4px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    font-size: 14px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        opacity: 0;
        transform: translateY(-20px);
        transition: opacity 0.3s ease, transform 0.3s ease;
      }
      .copy-notification.show {
        opacity: 1;
        transform: translateY(0);
    }
  `;
    document.head.appendChild(style);
  }

  // 创建通知容器（如果尚未创建）
  let container = document.getElementById('notification-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'notification-container';
    document.body.appendChild(container);
  }

  // 创建新的通知元素
  const notification = document.createElement('div');
  notification.className = 'copy-notification';
  notification.textContent = message;
  container.appendChild(notification);

  // Trigger animation
  requestAnimationFrame(() => {
    notification.classList.add('show');
  });

  // 持续显示7秒后移除通知
  setTimeout(() => {
    notification.classList.remove('show');
    // Wait for fade out animation to complete before removing
    notification.addEventListener('transitionend', () => {
      notification.remove();
      // 如果容器内没有其他通知则移除容器
      if (container.children.length === 0) {
        container.remove();
        // Optionally remove style if no more notifications are expected soon
        // const styleSheet = document.getElementById('notification-style');
        // if (styleSheet) styleSheet.remove();
      }
    });
  }, 7000);
}

function extractAndCopy() {
  let textContent = '';
  let imagesFoundForDownload = false; // 用于跟踪是否至少尝试下载了一张图片

  if (window.location.hostname.includes("ft.com")) {
    const siteContent = document.getElementById('site-content');
    // 先尝试最常见的新版结构，再 fallback 到旧版
    const articleBody =
      document.getElementById('article-body') ||
      siteContent?.querySelector('#article-body');

    if (articleBody) {
      // 1. 文本提取：兼容 <p> 和最外层 <div> 两种容器
      let paras = Array.from(articleBody.querySelectorAll('p'));
      // 加回新版里文字被 <div> 包裹的情况
      const divParas = Array.from(articleBody.children)
        .filter(el => el.tagName === 'DIV');
      paras = [...new Set([...paras, ...divParas])];

      // 原有的 FT.com 段落过滤逻辑
      const kept = paras.filter(p => {
        const text = p.textContent.trim();
        if (!text || text.length <= 1) return false;
        if (text === '@' || text === '•' || text === '».') return false;
        if (text.includes('is the author of') ||
          text.toLowerCase().includes('follow ft weekend')) return false;
        if (text.toLowerCase().includes('change has been made') ||
          text.toLowerCase().includes('story was originally published'))
          return false;
        if (text.toLowerCase().includes('subscribe') ||
          text.toLowerCase().includes('newsletter'))
          return false;
        if (text.toLowerCase().includes('follow') &&
          (text.includes('instagram') || text.includes('twitter')))
          return false;
        // 排除主要由 <em> 组成的段落
        const emTags = p.getElementsByTagName('em');
        if (emTags.length > 0 && emTags[0].textContent.length > text.length / 2)
          return false;
        // 排除大量链接
        const links = p.getElementsByTagName('a');
        if (links.length > 2) return false;
        return true;
      });
      const textContent = kept
        .map(p => p.textContent.trim())
        .join('\n\n');

      // 2. 图片下载：先按老逻辑抓特定类名的 <figure>，再 fallback 到 siteContent 下所有 <figure>
      let imageFigures = Array.from(
        document.querySelectorAll(
          'figure.n-content-image, figure.n-content-picture, ' +
          'figure.o-topper_visual, .main-image'
        )
      );
      if (imageFigures.length === 0 && siteContent) {
        imageFigures = Array.from(siteContent.querySelectorAll('figure'));
      }
      // 同一元素去重
      imageFigures = [...new Set(imageFigures)];

      if (imageFigures.length === 0) {
        chrome.runtime.sendMessage({ action: 'noImages' });
      } else {
        let seenUrls = new Set();
        let seenNames = new Set();
        imageFigures.forEach((fig, idx) => {
          // 取 <picture><img> 或 fig.querySelector('img')
          const pic = fig.querySelector('picture');
          const img = pic ? pic.querySelector('img') : fig.querySelector('img');
          if (!img) return;

          // 最高分辨率
          let url = img.src;
          if (img.srcset) {
            const candidates = img.srcset
              .split(',')
              .map(entry => {
                const [u, w] = entry.trim().split(/\s+/);
                return { url: u, width: parseInt(w) || 0 };
              })
              .filter(c => c.width > 0)
              .sort((a, b) => b.width - a.width);
            if (candidates[0]) url = candidates[0].url;
          }
          url = url.trim();
          if (!/^https?:\/\//.test(url) || seenUrls.has(url)) return;
          seenUrls.add(url);

          // 描述：合并所有 span 并去掉版权 ©…
          let caption = '';
          const fc = fig.querySelector('figcaption');
          if (fc) {
            caption = Array.from(fc.querySelectorAll('span'))
              .map(sp => sp.textContent.trim())
              .join(' ')
              .replace(/©.*$/g, '')
              .trim();
          }
          if (!caption) caption = img.alt.trim();
          if (!caption) caption = `ft-image-${Date.now()}-${idx}`;

          // ★★★ 修改点 ★★★
          // 2. 修改正则表达式，增加对'+'的过滤
          // 清洗成合法文件名，防重名
          let base = caption
            .replace(/[/\\?%*:|"<>+]/g, '') // 过滤掉非法字符以及+和-号
            .replace(/\s+/g, ' ')
            .substring(0, 200)
            .trim();
          let filename = `${base}.jpg`;
          let counter = 1;
          while (seenNames.has(filename)) {
            filename = `${base}(${counter++}).jpg`;
          }
          seenNames.add(filename);

          chrome.runtime.sendMessage({
            action: 'downloadImage',
            url,
            filename
          });
        });
      }

      // 3. 复制并返回 true
      if (textContent) {
        const ta = document.createElement('textarea');
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        ta.value = textContent;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        return true;
      }
    } else {
      // 没找到 #article-body
      chrome.runtime.sendMessage({ action: 'noImages' });
    }
    return false;
  }

  // ==========================================
  // 2. 【新增】DW (德国之声) 处理逻辑
  // ==========================================
  else if (window.location.hostname.includes("dw.com")) {
    // DW 的内容通常在 article 标签内
    const contentRoot = document.querySelector('article') || document.querySelector('#main-content') || document;

    if (contentRoot) {
      // 1. 提取文本
      // DW 的正文和标题通常在 data-tracking-name="rich-text" 的 div 下
      const textSelectors = [
        'div[data-tracking-name="rich-text"] h2',
        'div[data-tracking-name="rich-text"] h3',
        'div[data-tracking-name="rich-text"] p'
      ];

      const allElements = contentRoot.querySelectorAll(textSelectors.join(','));
      let uniqueElements = [...new Set(allElements)];

      textContent = uniqueElements
        .map(el => {
          // 1. 过滤视频容器
          if (el.closest('.vjs-wrapper')) return '';
          if (el.textContent.includes("To view this video please enable JavaScript")) return '';

          const tagName = el.tagName.toLowerCase();

          // 2. 基础文本清理
          let text = el.textContent.trim()
            .replace(/\s+/g, ' ')
            .replace(/&nbsp;/g, ' ')
            .trim();

          // ★★★ 修改点：精准过滤包含“长平观察：”的整段内容 ★★★
          if (text.includes("长平观察：")) {
            return '';
          }

          // 3. ★★★ 新增：过滤社交媒体推广和版权声明 ★★★
          if (
            text.includes("DW中文有Instagram") ||
            text.includes("摘编自其他媒体") ||
            text.includes("dw.chinese") ||
            text.includes("德国之声版权声明") ||
            text.startsWith("© 20") // 匹配 © 2026年...
          ) {
            return '';
          }

          // 4. 过滤无效字符
          if (!text || text.length <= 1 || ['@', '•', '∞'].includes(text)) {
            return '';
          }

          // 5. 标题格式化
          if (tagName === 'h2' || tagName === 'h3') {
            return `\n【${text}】\n`;
          }
          return text;
        })
        .filter(text => text.length > 0)
        .join('\n\n');


      // 2. 提取并下载图片
      if (textContent) {
        // DW 的图片通常在 figure 标签内
        let allImages = [...document.querySelectorAll('article figure img')];

        // 去重
        allImages = [...new Set(allImages)];

        // ★★★ 关键修改：过滤掉低清占位图 (lq-img) ★★★
        // DW 页面中一个 figure 里通常有两个 img，一个是 lq-img (placeholder)，一个是 hq-img (real)
        // 如果不过滤，会导致重复下载，且 lq-img 可能会导致文件名冲突或下载为 HTML
        allImages = allImages.filter(img => !img.classList.contains('lq-img'));

        if (allImages.length === 0) {
          chrome.runtime.sendMessage({
            action: 'noImages'
          });
        } else {
          const processedUrls = new Set();
          allImages.forEach(img => {
            if (img) {
              // 查找高清图 URL (复用 WSJ 的 srcset 解析逻辑)
              let highestResUrl = img.src;
              if (img.srcset) {
                const cleanSrcset = img.srcset.replace(/\n/g, ' ').replace(/\s+/g, ' ').trim();
                const srcsetEntries = cleanSrcset.split(',').map(entry => {
                  // DW 的 srcset 格式通常是 "url width_descriptor"
                  const parts = entry.trim().split(/\s+/);
                  // 取最后一部分作为宽度，去掉 'w'
                  const widthStr = parts[parts.length - 1];
                  const url = parts[0];
                  const widthNum = parseInt(widthStr?.replace(/[^0-9]/g, '') || '0');
                  return {
                    url: url,
                    width: widthNum
                  };
                });

                // 找到宽度最大的图片
                const highestResSrc = srcsetEntries.reduce((prev, current) => {
                  return (current.width > prev.width) ? current : prev;
                }, srcsetEntries[0]);
                if (highestResSrc && highestResSrc.url) {
                  highestResUrl = highestResSrc.url;
                }
              }

              // 清理 URL
              const finalUrl = highestResUrl.split('?')[0];

              if (!processedUrls.has(finalUrl)) {
                processedUrls.add(finalUrl);

                // 提取图片描述
                let altText = '';
                const figure = img.closest('figure');
                if (figure) {
                  const figcaption = figure.querySelector('figcaption');
                  if (figcaption) {
                    // 移除版权信息等杂质
                    const clone = figcaption.cloneNode(true);
                    const smalls = clone.querySelectorAll('small, .copyright');
                    smalls.forEach(s => s.remove());
                    altText = clone.textContent.trim();
                  }
                }
                // 兜底描述
                if (!altText) altText = img.title || img.alt || 'dw_image';

                // ★★★ 关键修改：增强文件名清理逻辑 ★★★
                const processFileName = (text) => {
                  text = text
                    // 1. 移除中文引号和句号，防止文件名出现 ".." 或 ".html" 混淆
                    .replace(/[“”。，,]/g, '')
                    // 2. 移除系统非法字符
                    .replace(/[\\/?%*:|"<>+]/g, '-')
                    .replace(/\s+/g, ' ')
                    .trim();
                  if (text.length > 100) {
                    text = text.substr(0, 96) + '...';
                  }
                  return `${text}.jpg`;
                };

                chrome.runtime.sendMessage({
                  action: 'downloadImage',
                  url: finalUrl,
                  filename: processFileName(altText)
                });
              }
            }
          });
        }
      }
    }
  }

  // --- 修复版：处理 rfi.fr ---
  else if (window.location.hostname.includes("rfi.fr")) {
    const article = document.querySelector('article') || document.getElementById('main-content');

    if (article) {
      // 1. 提取正文
      // 修复点1：兼容 .t-content_body (单下划线) 和 .t-content__body (双下划线)
      const bodyContainer = article.querySelector('.t-content__body, .t-content_body');

      if (bodyContainer) {
        // 修复点2：改用 childNodes 遍历。
        // 因为你的源码显示有 "＜p>" 这种奇怪的标签，还有直接裸露在 div 里的文本。
        // querySelectorAll('p') 抓不到它们，遍历节点最稳妥。
        textContent = Array.from(bodyContainer.childNodes)
          .map(node => {
            // 排除广告容器 (通过类名判断)
            if (node.nodeType === Node.ELEMENT_NODE) {
              // 1. 排除广告和推广容器
              if (node.closest && (node.closest('.o-self-promo') || node.closest('.m-interstitial'))) return '';
              // 如果是元素，取其文本
              return node.textContent.trim();
            }
            // 如果是文本节点（为了抓取那些裸露的文本）
            if (node.nodeType === Node.TEXT_NODE) {
              return node.textContent.trim();
            }
            return '';
          })
          .filter(t => {
            // 基础过滤：去除空文本或单字符
            if (!t || t.length <= 1) return false;

            // ★★★ 新增：精准过滤“广告”二字 ★★★
            if (t === '广告') return false;

            // --- 需求 2：过滤以 "AdChoices" 开头的行 ---
            // 使用 startsWith 判断，同时也建议转为小写判断以防大小写差异
            if (t.startsWith('AdChoices')) return false;

            // 过滤无效符号 (清理了原代码中的转义斜杠)
            if (['@', '•', '∞', 'flex', '::before', '::after'].includes(t)) return false;

            // 过滤空白行
            if (/^\s*$/.test(t)) return false;
            return true;
          })
          .map(t => {
            // 额外清理：去掉可能残留的 "＜p>" 或类似标签文本
            return t.replace(/^＜p>/, '').trim();
          })
          .join('\n\n');
      }

      // 2. 提取图片
      if (textContent) {
        const figures = Array.from(article.querySelectorAll('figure.m-item-image'));

        if (figures.length === 0) {
          chrome.runtime.sendMessage({ action: 'noImages' });
        } else {
          const processedUrls = new Set();

          figures.forEach((figure, idx) => {
            const img = figure.querySelector('img');
            if (!img) return;

            // RFI 图片通常在 picture > source 中有高清源
            let bestUrl = '';
            const sources = figure.querySelectorAll('source');

            // 尝试从 source 中找最大的
            let maxW = 0;
            sources.forEach(src => {
              if (src.srcset) {
                const candidates = src.srcset.split(',').map(s => {
                  const parts = s.trim().split(/\s+/);
                  const url = parts[0];
                  const wStr = parts[1] || '';
                  const w = parseInt(wStr.replace(/\D/g, '')) || 0;
                  return { url, w };
                });
                const localMax = candidates.sort((a, b) => b.w - a.w)[0];
                if (localMax && localMax.w > maxW) {
                  maxW = localMax.w;
                  bestUrl = localMax.url;
                }
              }
            });

            // 回退 img 标签
            if (!bestUrl) {
              if (img.srcset) {
                const candidates = img.srcset.split(',').map(s => {
                  const parts = s.trim().split(/\s+/);
                  return { url: parts[0], w: parseInt(parts[1]?.replace(/\D/g, '') || '0') };
                }).sort((a, b) => b.w - a.w);
                if (candidates[0]) bestUrl = candidates[0].url;
              }
            }

            if (!bestUrl) bestUrl = img.src;

            if (!bestUrl) return;
            try {
              bestUrl = new URL(bestUrl, window.location.href).href;
            } catch (e) { return; }

            if (processedUrls.has(bestUrl)) return;
            processedUrls.add(bestUrl);

            // 提取 Caption
            let caption = '';
            const figcaption = figure.querySelector('figcaption');
            if (figcaption) {
              caption = Array.from(figcaption.querySelectorAll('span'))
                .map(s => s.textContent.trim())
                .join(' ')
                .trim();
            }
            if (!caption && img.alt) caption = img.alt.trim();

            let ext = 'jpg';
            if (bestUrl.includes('.webp')) ext = 'webp';
            else if (bestUrl.includes('.png')) ext = 'png';

            let filename = (caption || `rfi-image-${Date.now()}-${idx}`)
              .replace(/[\\/?%*:|"<>+]/g, '-')
              .replace(/\s+/g, ' ')
              .substring(0, 150)
              .trim();

            filename = `${filename}.${ext}`;

            chrome.runtime.sendMessage({
              action: 'downloadImage',
              url: bestUrl,
              filename: filename
            });
          });
        }
      }
    }
  }

  // ==========================================
  // 3. 【新增】BBC 处理逻辑
  // ==========================================
  else if (window.location.hostname.includes("bbc.com")) {
    // BBC 的主要内容通常在 main 标签内
    const contentRoot = document.querySelector('main[role="main"]') || document;

    if (contentRoot) {
      // 1. 提取文本
      // BBC 正文段落和小标题
      const textSelectors = [
        'h2',
        'h3',
        'p'
      ];

      const allElements = contentRoot.querySelectorAll(textSelectors.join(','));
      let uniqueElements = [...new Set(allElements)];

      textContent = uniqueElements
        .map(el => {
          // 过滤掉图片描述(figcaption)内的文本，避免正文重复
          if (el.closest('figcaption')) return '';
          // 过滤掉页面导航、推荐阅读等非正文区域
          if (el.closest('[data-e2e="recommendations-heading"]') || el.closest('header')) return '';

          const tagName = el.tagName.toLowerCase();
          let text = el.textContent.trim()
            .replace(/\s+/g, ' ')
            .replace(/&nbsp;/g, ' ')
            .trim();

          // 过滤无效文本
          if (!text || text.length <= 1 || text === '圖像加註文字，') {
            return '';
          }

          // ★★★ 新增：过滤图片来源标注行 ★★★
          if (text.startsWith('圖像來源，')) {
            return '';
          }

          // ★★★ 新增：过滤文章结尾标记 ★★★
          if (text === 'End of content') {
            return '';
          }

          // 标题格式化
          if (tagName === 'h2' || tagName === 'h3') {
            return `\n【${text}】\n`;
          }
          return text;
        })
        .filter(text => text.length > 0)
        .join('\n\n');

      // 2. 提取并下载图片
      if (textContent) {
        // 查找 main 下的所有 figure 中的图片
        let allImages = [...contentRoot.querySelectorAll('figure img')];
        allImages = [...new Set(allImages)];

        if (allImages.length === 0) {
          chrome.runtime.sendMessage({ action: 'noImages' });
        } else {
          const processedUrls = new Set();

          allImages.forEach(img => {
            if (img) {
              // 解析 srcset 获取最高清图片
              let highestResUrl = img.src;
              if (img.srcset) {
                const cleanSrcset = img.srcset.replace(/\n/g, ' ').replace(/\s+/g, ' ').trim();
                const srcsetEntries = cleanSrcset.split(',').map(entry => {
                  const parts = entry.trim().split(/\s+/);
                  const widthStr = parts[parts.length - 1];
                  const url = parts[0];
                  const widthNum = parseInt(widthStr?.replace(/[^0-9]/g, '') || '0');
                  return { url: url, width: widthNum };
                });

                const highestResSrc = srcsetEntries.reduce((prev, current) => {
                  return (current.width > prev.width) ? current : prev;
                }, srcsetEntries[0]);

                if (highestResSrc && highestResSrc.url) {
                  highestResUrl = highestResSrc.url;
                }
              }

              // 清理 URL 并在后面加上 .webp 扩展名（BBC图片通常是webp）
              const finalUrl = highestResUrl.split('?')[0];

              if (!processedUrls.has(finalUrl)) {
                processedUrls.add(finalUrl);

                // 提取图片描述
                let altText = '';
                const figure = img.closest('figure');
                if (figure) {
                  // 优先查找 data-testid="caption-paragraph"
                  const captionSpan = figure.querySelector('[data-testid="caption-paragraph"]');
                  if (captionSpan) {
                    altText = captionSpan.textContent.trim();
                  } else {
                    const figcaption = figure.querySelector('figcaption');
                    if (figcaption) {
                      // 移除 "圖像加註文字，" 等前缀
                      let rawText = figcaption.textContent.trim();
                      altText = rawText.replace(/^圖像加註文字，\s*/, '');
                    }
                  }
                }

                // 兜底描述
                if (!altText) altText = img.alt || 'bbc_image';

                // 文件名清理逻辑
                const processFileName = (text) => {
                  text = text
                    .replace(/[“”。，,]/g, '')
                    .replace(/[\\/?%*:|"<>+]/g, '-')
                    .replace(/\s+/g, ' ')
                    .trim();
                  if (text.length > 100) {
                    text = text.substr(0, 96) + '...';
                  }
                  // BBC 的高清图通常以 .webp 结尾，为了兼容性可以存为 .jpg，系统会自动处理
                  return `${text}.jpg`;
                };

                chrome.runtime.sendMessage({
                  action: 'downloadImage',
                  url: finalUrl,
                  filename: processFileName(altText)
                });
              }
            }
          });
        }
      }
    }
  }



  // ==========================================
  // 3. 通用/收尾逻辑
  // ==========================================

  // 如果提取到了文本，执行复制
  if (textContent) {
    // 创建一个隐藏的 textarea 元素以复制文本
    const textarea = document.createElement('textarea');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    textarea.value = textContent;
    document.body.appendChild(textarea);
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length); // For better compatibility

    try {
      document.execCommand('copy');
      // 返回 true 表示文本复制成功。图片下载是异步的，其成功与否由 background script 的通知处理。
      return true;
    } catch (err) {
      console.error('复制失败:', err);
      return false;
    } finally {
      document.body.removeChild(textarea);
    }
  } else if (imagesFoundForDownload) {
    // 如果没有文本内容，但尝试了图片下载（例如 Reuters Pictures 页面）
    // 这种情况下，我们不应该返回 false 导致“复制失败”的通知。
    // 而是让 background script 的图片下载通知来主导。
    // 返回一个特殊值或true，表示操作已启动（图片下载）。
    // 或者，如果 extractAndCopy 的返回值仅用于判断文本复制是否成功，
    // 那么这里可以返回 false，但需要确保 'noImages' 或 '所有图片下载完成' 的通知能正确显示。
    // 为了简化，如果主要目的是复制文本，且文本为空，即使有图片，也可能视为“内容未找到（用于复制）”。
    // 保持返回 false，让上层逻辑判断。
    // 如果 extractAndCopy 的返回值 true/false 严格对应文本复制，那么这里返回 false 是对的。
    // 图片下载状态由 `DownloadsPending` 和 `onChanged` 处理。
    return false; // 没有文本可复制
  }

  // 如果既没有文本内容，也没有尝试下载图片（例如，所有网站的解析都失败了）
  if (!textContent && !imagesFoundForDownload) {
    // 确保在没有任何操作发生时，也发送一个 noImages，
    // 以便 background script 可以清理 DownloadsPending（如果之前错误地设置了 hasStartedImageProcess）
    // 但这通常由每个站点处理器内部的 noImages 调用来处理。
    // 此处返回 false 即可。
  }

  return false; // 默认返回 false，表示没有文本内容被复制
}