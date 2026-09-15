/* 合规卫士 · Service Worker
 * ============================================================
 *
 * 这个页面本来就不发任何网络请求（无 fetch、无后端、无埋点），
 * 所以 SW 在这里解决的不是"加速"，而是另一件事：
 * **第一次打开之后，断网也能用，并且可以装到桌面/手机主屏。**
 *
 * 缓存策略刻意分成两路：
 *
 *   1. 导航请求（HTML）→ network-first，失败回退缓存
 *      保证打开时拿到的是最新版本；只有离线时才吃缓存。
 *
 *   2. 静态资源 → stale-while-revalidate
 *      先给缓存保证秒开，同时后台悄悄拉一份新的更新缓存，
 *      下次访问就是最新的。这样就不必把版本号手写进缓存名——
 *      手写版本号意味着"同一件事存了两处"，早晚会对不上。
 */

const CACHE = 'adcompli-static';

/* 预缓存清单：首次安装就把整站拉下来，之后离线可用。
   注意 ./data/rules.js 有 180KB+，正是它让"断网也能查"成立。 */
const ASSETS = [
  './',
  './index.html',
  './css/style.css',
  './js/engine.js',
  './js/app.js',
  './data/rules.js',
  './manifest.webmanifest',
  './icon-192.png',
  './icon-512.png',
  './apple-touch-icon.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => Promise.all(
        ASSETS.map((url) => cache
          // cache: 'reload' 绕过 HTTP 缓存，确保预缓存的是服务器上的当前版本
          .add(new Request(url, { cache: 'reload' }))
          // 单个资源失败不该让整个安装失败（比如某个图标暂时 404）
          .catch(() => null))
      ))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // 只处理 GET；POST 之类直接放行（本页本来也没有）
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  // 跨域资源不插手，交回浏览器
  if (url.origin !== self.location.origin) return;

  // ---- 1. 页面导航：network-first ----
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE)
            .then((c) => c.put('./index.html', copy))
            .catch(() => {});
          return res;
        })
        .catch(() => caches.match('./index.html').then(
          (hit) => hit || caches.match('./')
        ))
    );
    return;
  }

  // ---- 2. 静态资源：stale-while-revalidate ----
  event.respondWith(
    caches.match(req).then((cached) => {
      const fromNetwork = fetch(req)
        .then((res) => {
          // 只缓存正常的基本响应，避免把 404 / opaque 响应写进缓存
          if (res && res.status === 200 && res.type === 'basic') {
            const copy = res.clone();
            caches.open(CACHE)
              .then((c) => c.put(req, copy))
              .catch(() => {});
          }
          return res;
        })
        .catch(() => cached);

      return cached || fromNetwork;
    })
  );
});
