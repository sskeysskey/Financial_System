// 专用 Worker 里的计时：控制台页在后台时，主线程定时器会被 Chrome 节流（最严重时每分钟才触发一次）
self.onmessage = (e) => {
  const { id, ms } = e.data || {};
  setTimeout(() => self.postMessage(id), ms);
};