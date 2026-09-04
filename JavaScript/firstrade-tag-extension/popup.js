const fileInput = document.getElementById('fileInput');
const pasteArea = document.getElementById('pasteArea');
const pasteBtn = document.getElementById('pasteBtn');
const clearBtn = document.getElementById('clearBtn');
const maxTagsInput = document.getElementById('maxTags');
const statusEl = document.getElementById('status');

function setStatus(text, isError) {
  statusEl.style.color = isError ? '#b91c1c' : '#059669';
  statusEl.innerText = text;
}

/* ---------- 初始化：显示当前缓存状态 ---------- */
chrome.storage.local.get(['stockData', 'maxTags'], (res) => {
  if (res.maxTags) maxTagsInput.value = res.maxTags;
  if (res.stockData) {
    const keys = Object.keys(res.stockData);
    setStatus(`已缓存 ${keys.length} 个标的\n示例：${keys.slice(0, 8).join(', ')}`);
  } else {
    setStatus('尚未导入数据，请选择 description.json');
  }
});

/* ---------- 核心：把 JSON 解析成 { SYMBOL: [tag...] } ---------- */
function buildMap(json) {
  const map = {};
  // 兼容 stocks / etfs / 以及任何顶层数组（比如以后新增 crypto、bonds 等）
  Object.keys(json).forEach((key) => {
    const arr = json[key];
    if (!Array.isArray(arr)) return;
    arr.forEach((item) => {
      if (!item || typeof item !== 'object') return;
      const sym = (item.symbol || '').toString().trim().toUpperCase();
      if (!sym) return;
      let tags = item.tag;
      if (typeof tags === 'string') tags = [tags];
      if (!Array.isArray(tags)) return;
      tags = tags.map(t => String(t).trim()).filter(Boolean);
      if (tags.length) map[sym] = tags;
    });
  });
  return map;
}

function save(map) {
  const count = Object.keys(map).length;
  if (!count) {
    setStatus('解析成功，但没有找到任何含 tag 的 symbol，请检查 JSON 结构', true);
    return;
  }
  const maxTags = Math.max(1, Math.min(20, parseInt(maxTagsInput.value, 10) || 4));
  chrome.storage.local.set({ stockData: map, maxTags }, () => {
    if (chrome.runtime.lastError) {
      setStatus('写入失败：' + chrome.runtime.lastError.message, true);
      return;
    }
    setStatus(`导入成功！共 ${count} 个标的\n示例：${Object.keys(map).slice(0, 8).join(', ')}`);
    notifyActiveTab();
  });
}

// content.js 监听了 storage 变化，这里再补一条消息做双保险（失败也不报错）
function notifyActiveTab() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs || !tabs[0] || !tabs[0].id) return;
    chrome.tabs.sendMessage(tabs[0].id, { action: 'refreshTags' }, () => {
      void chrome.runtime.lastError; // 页面没有 content script 时忽略报错
    });
  });
}

function handleText(text) {
  try {
    const json = JSON.parse(text);
    save(buildMap(json));
  } catch (err) {
    setStatus('解析 JSON 失败：' + err.message, true);
  }
}

/* ---------- 事件绑定 ---------- */
fileInput.addEventListener('change', (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  setStatus('读取中…');
  const reader = new FileReader();
  reader.onerror = () => setStatus('文件读取失败，请改用下方“粘贴 JSON”方式', true);
  reader.onload = (ev) => handleText(ev.target.result);
  reader.readAsText(file, 'utf-8');
});

pasteBtn.addEventListener('click', () => {
  const text = pasteArea.value.trim();
  if (!text) { setStatus('粘贴框是空的', true); return; }
  handleText(text);
});

maxTagsInput.addEventListener('change', () => {
  const maxTags = Math.max(1, Math.min(20, parseInt(maxTagsInput.value, 10) || 4));
  chrome.storage.local.set({ maxTags }, () => {
    setStatus(`已设置为每行最多显示 ${maxTags} 个标签（页面会自动刷新）`);
    notifyActiveTab();
  });
});

clearBtn.addEventListener('click', () => {
  chrome.storage.local.remove('stockData', () => {
    setStatus('已清空缓存数据');
    notifyActiveTab();
  });
});