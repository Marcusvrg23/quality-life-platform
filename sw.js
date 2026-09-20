const CACHE="quality-life-v8";
const ASSETS=["./","./index.html","./styles.css?v=8.0","./app.js?v=8.0","./manifest.webmanifest","./icon.svg","./assets/quality-life-logo-dark-arc.png","./assets/quality-life-logo-dark-arc-small.png","./assets/activity-frames/frame-1-cervical.png","./assets/activity-frames/frame-2-ombros.png","./assets/activity-frames/frame-3-peitoral.png","./assets/activity-frames/frame-4-respiracao.png","./assets/people-scenes/mulher-alongando.png","./assets/people-scenes/homem-cervical.png","./assets/people-scenes/homem-lombar.png","./assets/people-scenes/mulher-respiracao.png","./assets/ui-home/hero-card.png","./assets/ui-home/card-mobilidade.png","./assets/ui-home/card-respiracao.png","./assets/ui-home/card-alongamento.png","./assets/ui-home/banner-transformacoes.png","./assets/ui-home/home-preview-full.png","./assets/mascot-ui/card-mobilidade.png","./assets/mascot-ui/card-respiracao.png","./assets/mascot-ui/card-alongamento.png","./assets/mascot-ui/step-1-mobilidade-cervical.png","./assets/mascot-ui/step-2-elevacao-ombros.png","./assets/mascot-ui/step-3-abertura-peitoral.png","./assets/mascot-ui/step-4-respiracao.png","./assets/posters/inicio-trabalho.jpg","./assets/posters/durante-trabalho.jpg","./assets/posters/final-trabalho.jpg"];

self.addEventListener("install",event=>{
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)));
});

self.addEventListener("activate",event=>{
  event.waitUntil(
    caches.keys()
      .then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key))))
      .then(()=>self.clients.claim())
  );
});

self.addEventListener("fetch",event=>{
  if(event.request.mode==="navigate"){
    event.respondWith(
      fetch(event.request)
        .then(response=>{
          const clone=response.clone();
          caches.open(CACHE).then(cache=>cache.put("./index.html",clone));
          return response;
        })
        .catch(()=>caches.match("./index.html"))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then(cached=>{
      return cached || fetch(event.request).then(response=>{
        if(event.request.method==="GET"){
          const clone=response.clone();
          caches.open(CACHE).then(cache=>cache.put(event.request,clone));
        }
        return response;
      });
    })
  );
});
