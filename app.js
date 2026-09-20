const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
let currentUser = null;
let mood = null;

const users = {
  "cliente@qualitylife.com": {password:"demo123",role:"client",name:"Mariana Alves",first:"Mariana"},
  "profissional@qualitylife.com": {password:"admin123",role:"professional",name:"Renata Martins",first:"Renata"}
};

function toast(msg){
  const t=$("#toast"); t.textContent=msg; t.classList.add("show");
  clearTimeout(window.__t); window.__t=setTimeout(()=>t.classList.remove("show"),2600);
}
$$("[data-toast]").forEach(b=>b.onclick=()=>toast(b.dataset.toast));

$("#showPassword").onclick=()=>{
  const p=$("#password"); p.type=p.type==="password"?"text":"password";
};

$("#demoClient")?.addEventListener("click", ()=>{
  $("#email").value="cliente@qualitylife.com";
  $("#password").value="demo123";
  authenticate("cliente@qualitylife.com","demo123",false);
});

$("#demoProfessional")?.addEventListener("click", ()=>{
  $("#email").value="profissional@qualitylife.com";
  $("#password").value="admin123";
  authenticate("profissional@qualitylife.com","admin123",false);
});

function authenticate(emailRaw, passwordRaw, remember=false){
  const email = String(emailRaw || "").trim().toLowerCase();
  const password = String(passwordRaw || "").trim();
  const u = users[email];

  if(!u || u.password !== password){
    toast("E-mail ou senha inválidos. Confira as credenciais de demonstração.");
    return false;
  }

  currentUser = {...u, email};

  try{
    sessionStorage.setItem("ql_session", JSON.stringify(currentUser));
    if(remember){
      localStorage.setItem("ql_session", JSON.stringify(currentUser));
    }else{
      localStorage.removeItem("ql_session");
    }
  }catch(e){}

  openApp();
  return true;
}

$("#loginForm").addEventListener("submit", e=>{
  e.preventDefault();
  authenticate($("#email").value, $("#password").value, $("#remember").checked);
});

$("#logout").onclick=()=>{
  localStorage.removeItem("ql_session"); sessionStorage.removeItem("ql_session"); currentUser=null;
  $("#app").classList.add("hidden"); $("#loginScreen").classList.remove("hidden");
  $("#password").value="";
};
$("#menuBtn").onclick=()=>$("#sidebar").classList.toggle("open");

function openApp(){
  $("#loginScreen").classList.add("hidden"); $("#app").classList.remove("hidden");
  $("#sideName").textContent=currentUser.name;
  $("#sideRole").textContent=currentUser.role==="client"?"Cliente":"Profissional";
  $("#avatar").textContent=currentUser.first[0]; $("#sideAvatar").textContent=currentUser.first[0];
  buildNav(); renderHome();
}

function navItems(){
  return currentUser.role==="client"
    ? [["Hoje","●"],["Minhas atividades","▶"],["Aulas","▣"],["Meu progresso","◒"],["Minha avaliação","◇"],["Perfil","○"]]
    : [["Visão geral","●"],["Clientes","○"],["Anamneses","◇"],["Programas","▶"],["Biblioteca","▣"],["Relatórios","◒"]];
}
function buildNav(){
  const nav=$("#nav"); nav.innerHTML="";
  navItems().forEach((it,i)=>{
    const b=document.createElement("button");
    b.className=i===0?"active":"";
    b.innerHTML=`<span class="nav-icon">${it[1]}</span><span>${it[0]}</span>`;
    b.onclick=()=>{
      $$("#nav button").forEach(x=>x.classList.remove("active")); b.classList.add("active");
      $("#sidebar").classList.remove("open"); $("#pageTitle").textContent=it[0];
      $("#crumb").textContent=`Quality Life / ${it[0]}`;
      renderSection(it[0]);
    };
    nav.appendChild(b);
  });
}
function renderHome(){
  $("#pageTitle").textContent=currentUser.role==="client"?"Hoje":"Visão geral";
  $("#crumb").textContent=`Quality Life / ${$("#pageTitle").textContent}`;
  $("#content").innerHTML=currentUser.role==="client"?clientHome():professionalHome();
  bindPage();
}
function renderSection(name){
  if((currentUser.role==="client"&&name==="Hoje")||(currentUser.role==="professional"&&name==="Visão geral")) return renderHome();
  $("#content").innerHTML=currentUser.role==="client"?clientModule(name):professionalModule(name);
  bindPage();
}
function bindPage(){
  $$("[data-mood]").forEach(b=>b.onclick=()=>{
    $$("[data-mood]").forEach(x=>x.classList.remove("selected")); b.classList.add("selected"); mood=b.dataset.mood;
    toast("Check-in registrado para hoje.");
  });
  $$('[data-start]').forEach(b=>b.onclick=openPlayer);
  $$('[data-open-step]').forEach(b=>b.onclick=()=>openPlayerAt(Number(b.dataset.openStep)||0));
  $$('[data-open-section]').forEach(b=>b.onclick=()=>openClientSection(b.dataset.openSection));
  $$("[data-demo-video]").forEach(b=>b.onclick=()=>openDemoVideo(b.dataset.demoVideo));
  $$("[data-toast-local]").forEach(b=>b.onclick=()=>toast(b.dataset.toastLocal));
}
function clientHome(){
 return `
 <div class="mascot-home">
   <div class="mascot-home-intro">
     <div>
       <span class="mascot-kicker">MINHA ÁREA</span>
       <h1>Escolha sua atividade</h1>
       <p>Rotinas rápidas de ginástica laboral organizadas para o seu dia.</p>
     </div>
   </div>

   <div class="mascot-home-stack">
     <button class="mascot-card-button" type="button" data-open-step="0" aria-label="Abrir mobilidade">
       <img src="assets/mascot-ui/card-mobilidade.png" alt="Mobilidade - 7 minutos">
     </button>
     <button class="mascot-card-button" type="button" data-open-step="3" aria-label="Abrir respiração">
       <img src="assets/mascot-ui/card-respiracao.png" alt="Respiração - 3 minutos">
     </button>
     <button class="mascot-card-button" type="button" data-open-step="2" aria-label="Abrir alongamento">
       <img src="assets/mascot-ui/card-alongamento.png" alt="Alongamento - 6 minutos">
     </button>
   </div>

   <section class="posture-video-shortcut card">
     <div>
       <span class="mascot-kicker">AULAS DEMONSTRATIVAS</span>
       <h3>Vídeos de ginástica laboral</h3>
       <p>Assim como no fluxo de referência, você também pode escolher o momento da jornada e assistir à prática em vídeo.</p>
     </div>
     <button type="button" class="start-btn" data-open-section="Aulas">Ver vídeos</button>
   </section>
 </div>`;
}

const demoVideos={inicio:{title:"Início do trabalho",category:"PREPARAÇÃO",src:"assets/videos/inicio-trabalho.mp4",poster:"assets/posters/inicio-trabalho.jpg",description:"Exemplo de atividade curta para ativar o corpo antes de iniciar a jornada de trabalho."},durante:{title:"Durante o trabalho",category:"PAUSA ATIVA",src:"assets/videos/durante-trabalho.mp4",poster:"assets/posters/durante-trabalho.jpg",description:"Demonstração de uma pausa guiada para recuperar mobilidade e reduzir a tensão acumulada durante o expediente."},final:{title:"Final do trabalho",category:"RECUPERAÇÃO",src:"assets/videos/final-trabalho.mp4",poster:"assets/posters/final-trabalho.jpg",description:"Exemplo de sequência leve para desacelerar o corpo e encerrar a jornada com uma rotina de recuperação."}};
function demoVideoCard(key,label,subtitle){const v=demoVideos[key];return `<button class="demo-video-card" type="button" data-demo-video="${key}"><div class="demo-video-thumb"><img src="${v.poster}" alt="${label}"><span class="demo-video-play">▶</span><span class="demo-video-label">${label}</span></div><div class="demo-video-card-copy"><strong>${label}</strong><small>${subtitle}</small><span class="demo-video-badge">VÍDEO DEMO • 10S</span></div></button>`;}
function openDemoVideo(key){const v=demoVideos[key];if(!v)return;const p=$("#demoVideoPlayer");$("#demoVideoTitle").textContent=v.title;$("#demoVideoCategory").textContent=v.category;$("#demoVideoDescription").textContent=v.description;p.pause();p.src=v.src;p.poster=v.poster;p.load();$("#demoVideoModal").classList.remove("hidden");}
function closeDemoVideo(){const p=$("#demoVideoPlayer");p.pause();p.removeAttribute("src");p.load();$("#demoVideoModal").classList.add("hidden");}

function contentCard(title,meta,icon,image,badge="VÍDEO DEMO"){
  return `<article class="card content-card">
    <div class="content-thumb">
      <img src="${image}" alt="${title}">
      <span class="content-play">${icon}</span>
      <span class="content-badge">${badge}</span>
    </div>
    <div class="card-line">
      <strong>${title}</strong>
      <small>${meta}</small>
    </div>
  </article>`;
}
function openClientSection(name){
  const buttons=$$("#nav button");
  const target=buttons.find(b=>b.textContent.trim().includes(name));
  if(target){ target.click(); return; }
  renderSection(name);
}

function clientModule(name){
 if(name==="Minha avaliação") return `
   <div class="page-intro"><div><h1>Minha avaliação</h1><p>Seu perfil de trabalho e informações liberadas para acompanhamento.</p></div><span class="pill">Atualizada em 12/08/2026</span></div>
   <div class="profile-panel">
     <section class="profile-card"><div class="person-big">${currentUser.first[0]}</div><h3>${currentUser.name}</h3><p>Administrativo • jornada predominantemente sentada</p>
       <div class="info-list">
        <div class="info-line"><span>Tempo sentada</span><strong>6–7 h/dia</strong></div>
        <div class="info-line"><span>Foco atual</span><strong>Cervical / ombros</strong></div>
        <div class="info-line"><span>Rotina indicada</span><strong>3 pausas/dia</strong></div>
        <div class="info-line"><span>Revisão</span><strong>19/08/2026</strong></div>
       </div>
     </section>
     <section class="form-card"><h3 style="margin-top:0">Como está sua rotina?</h3>
       <div class="field"><label>Principal desconforto hoje</label><select><option>Cervical</option><option>Ombros</option><option>Lombar</option><option>Punhos</option><option>Sem desconforto</option></select></div>
       <div class="field"><label>Observação</label><textarea placeholder="Conte algo importante para a profissional..."></textarea></div>
       <button class="start-btn" data-toast-local="Atualização salva no protótipo. Em produção, será registrada no banco.">Enviar atualização</button>
     </section>
   </div>`;
 if(name==="Meu progresso") return `
   <div class="page-intro"><div><h1>Meu progresso</h1><p>Consistência, tempo de prática e evolução da sua rotina.</p></div><span class="pill">Últimos 30 dias</span></div>
   <div class="stats">
     <article class="stat"><small>Atividades</small><strong>18</strong><span>+4 nesta semana</span></article>
     <article class="stat"><small>Tempo total</small><strong>1h 42</strong><span>média de 5m40s</span></article>
     <article class="stat"><small>Sequência</small><strong>4 dias</strong><span>melhor: 8 dias</span></article>
     <article class="stat"><small>Adesão</small><strong>72%</strong><span>meta: 80%</span></article>
   </div>
   <div class="progress-row"><section class="card progress-card"><h3>Meta semanal</h3><div class="progress-line"><span>4 de 6</span><strong>68%</strong></div><div class="bar"><i style="width:68%"></i></div></section><section class="card progress-card"><h3>Percepção de bem-estar</h3><p style="font-size:12px;color:var(--muted);line-height:1.6">Seu check-in será usado para mostrar tendência ao longo do tempo, sem substituir avaliação profissional.</p></section></div>`;
 if(name==="Minhas atividades") return `
   <div class="page-intro"><div><h1>Minhas atividades</h1><p>Sua rotina personalizada de pausas ao longo da jornada.</p></div><span class="pill">Plano atual</span></div>
   <div class="module-grid">
    ${moduleCard("Preparação","3 min • antes de iniciar","Sequência leve para ativar mobilidade e respiração.","▶ Iniciar")}
    ${moduleCard("Pausa cervical","6 min • manhã","Foco em cervical, ombros e postura sentada.","▶ Iniciar")}
    ${moduleCard("Punhos e mãos","4 min • tarde","Mobilidade para rotina de teclado e mouse.","▶ Iniciar")}
    ${moduleCard("Recuperação lombar","5 min • tarde","Movimentos leves para finalizar o expediente.","▶ Iniciar")}
   </div>`;
 if(name==="Aulas") return `
   <div class="page-intro"><div><h1>Aulas</h1><p>Conteúdos organizados por momento da jornada e objetivo.</p></div><span class="pill">Biblioteca demo</span></div>
   <section class="posture-inspired-intro" style="margin-top:0"><div class="demo-video-grid">
     ${demoVideoCard("inicio","Início do trabalho","Preparação e ativação leve.")}
     ${demoVideoCard("durante","Durante do trabalho","Pausa ativa e mobilidade.")}
     ${demoVideoCard("final","Final do trabalho","Recuperação ao encerrar a jornada.")}
   </div></section>
   <div class="module-grid" style="margin-top:18px">
    ${moduleCard("Trabalho sentado","12 aulas","Cervical, ombros, coluna e quadril.","Explorar")}
    ${moduleCard("Trabalho em pé","9 aulas","Pernas, tornozelos e mobilidade global.","Explorar")}
    ${moduleCard("Punhos e mãos","7 aulas","Rotinas para computador e movimentos repetitivos.","Explorar")}
   </div>`;
 if(name==="Perfil") return `
   <div class="page-intro"><div><h1>Perfil</h1><p>Preferências de acesso e dados básicos.</p></div></div>
   <div class="profile-panel"><section class="profile-card"><div class="person-big">${currentUser.first[0]}</div><h3>${currentUser.name}</h3><p>${currentUser.email}</p></section><section class="form-card"><div class="field"><label>Nome</label><input value="${currentUser.name}"></div><div class="field"><label>E-mail</label><input value="${currentUser.email}"></div><button class="start-btn" data-toast-local="Alterações salvas no protótipo.">Salvar alterações</button></section></div>`;
 return `<div class="page-intro"><div><h1>${name}</h1><p>Canal da Quality Life para apoiar sua experiência.</p></div></div><section class="card progress-card"><h3>Precisa de ajuda?</h3><p style="color:var(--muted);font-size:12px;line-height:1.6">A versão final poderá integrar WhatsApp, e-mail ou atendimento interno da equipe.</p><button class="start-btn" data-toast-local="Canal de suporte preparado para integração.">Falar com a equipe</button></section>`;
}
function moduleCard(title,meta,text,action){
 return `<article class="module-card"><strong>${title}</strong><small style="font-size:9px;color:var(--teal)">${meta}</small><p>${text}</p><button ${action.includes("Iniciar")?"data-start":"data-toast-local='Biblioteca aberta no protótipo.'" }>${action} →</button></article>`;
}
function professionalHome(){
 return `
 <div class="welcome-row"><div><h1>Painel da profissional</h1><p>Acompanhe adesão, anamneses e programas individuais.</p></div><div class="streak">● Operação ativa</div></div>
 <div class="stats">
  <article class="stat"><small>Colaboradores ativos</small><strong>124</strong><span>7 empresas vinculadas</span></article>
  <article class="stat"><small>Anamneses pendentes</small><strong style="color:var(--coral)">18</strong><span>6 prioritárias</span></article>
  <article class="stat"><small>Atividades concluídas</small><strong>1.420</strong><span>últimos 30 dias</span></article>
  <article class="stat"><small>Adesão média</small><strong>71%</strong><span>meta corporativa: 80%</span></article>
 </div>
 <div class="admin-grid">
  <section class="panel"><h3>Clientes para revisar</h3>
   <table class="table"><thead><tr><th>Cliente</th><th>Contexto</th><th>Programa</th><th>Status</th></tr></thead><tbody>
    <tr><td><strong>Mariana Alves</strong></td><td>Cervical • sentada</td><td>3 pausas/dia</td><td class="risk">Prioridade</td></tr>
    <tr><td><strong>Carlos Lima</strong></td><td>Lombar • em pé</td><td>2 pausas/dia</td><td><span class="status">Revisar</span></td></tr>
    <tr><td><strong>Ana Rocha</strong></td><td>Pausa mental</td><td>2 práticas/dia</td><td><span class="status">Acompanhando</span></td></tr>
    <tr><td><strong>Bruno Dias</strong></td><td>Home office</td><td>3 pausas/dia</td><td><span class="status">Nova avaliação</span></td></tr>
   </tbody></table>
  </section>
  <aside class="panel"><h3>Nova recomendação</h3>
   <div class="field"><label>Cliente</label><select><option>Mariana Alves</option><option>Carlos Lima</option><option>Ana Rocha</option></select></div>
   <div class="field"><label>Programa</label><select><option>Cervical e ombros</option><option>Lombar</option><option>Punhos e mãos</option><option>Pausa mental</option></select></div>
   <div class="field"><label>Orientação</label><textarea placeholder="Orientação liberada ao cliente..."></textarea></div>
   <button class="start-btn" data-toast-local="Recomendação preparada para persistência no backend.">Publicar</button>
  </aside>
 </div>`;
}
function professionalModule(name){
 if(name==="Clientes") return `
   <div class="page-intro"><div><h1>Clientes</h1><p>Pessoas vinculadas às empresas atendidas.</p></div><span class="pill">124 ativos</span></div>
   <section class="panel"><table class="table"><thead><tr><th>Nome</th><th>Empresa</th><th>Foco</th><th>Adesão</th><th>Status</th></tr></thead><tbody>
   <tr><td>Mariana Alves</td><td>Empresa Alpha</td><td>Cervical</td><td>76%</td><td><span class="status">Ativo</span></td></tr>
   <tr><td>Carlos Lima</td><td>Empresa Alpha</td><td>Lombar</td><td>61%</td><td><span class="status">Ativo</span></td></tr>
   <tr><td>Ana Rocha</td><td>Grupo Beta</td><td>Pausa mental</td><td>82%</td><td><span class="status">Ativo</span></td></tr>
   </tbody></table></section>`;
 if(name==="Anamneses") return `
   <div class="page-intro"><div><h1>Anamneses</h1><p>Avaliações recebidas para análise profissional.</p></div><span class="pill">18 pendentes</span></div>
   <div class="module-grid">${moduleCard("Mariana Alves","Recebida hoje","Relata desconforto cervical e jornada predominantemente sentada.","Revisar")}${moduleCard("Carlos Lima","Recebida ontem","Rotina prolongada em pé e desconforto lombar.","Revisar")}${moduleCard("Bruno Dias","Nova avaliação","Home office e baixa frequência de pausas.","Revisar")}</div>`;
 if(name==="Programas") return `
   <div class="page-intro"><div><h1>Programas</h1><p>Rotinas de ginástica laboral que podem ser atribuídas e personalizadas.</p></div><span class="pill">Biblioteca profissional</span></div>
   <div class="module-grid">${moduleCard("Administrativo sentado","3 pausas/dia","Cervical, ombros, punhos e lombar.","Editar")}${moduleCard("Operação em pé","2 pausas/dia","Pernas, coluna e mobilidade global.","Editar")}${moduleCard("Home office","3 pausas/dia","Ergonomia, coluna e recuperação visual.","Editar")}</div>`;
 if(name==="Relatórios") return `
   <div class="page-intro"><div><h1>Relatórios</h1><p>Indicadores agregados de adesão e participação.</p></div><span class="pill">Sem exposição clínica individual</span></div>
   <div class="stats"><article class="stat"><small>Adesão</small><strong>71%</strong><span>+6% no mês</span></article><article class="stat"><small>Práticas</small><strong>1.420</strong><span>30 dias</span></article><article class="stat"><small>Tempo médio</small><strong>6m</strong><span>por atividade</span></article><article class="stat"><small>Ativos</small><strong>124</strong><span>7 empresas</span></article></div>`;
 return `
   <div class="page-intro"><div><h1>${name}</h1><p>Gerencie conteúdos e materiais disponíveis na plataforma.</p></div></div>
   <div class="module-grid">${moduleCard("Cervical e ombros","12 conteúdos","Vídeos e práticas guiadas.","Abrir")}${moduleCard("Lombar e quadril","10 conteúdos","Mobilidade e alongamentos.","Abrir")}${moduleCard("Respiração e pausa","8 conteúdos","Bem-estar e desaceleração.","Abrir")}</div>`;
}

$("#closeDemoVideo")?.addEventListener("click",closeDemoVideo);$$("[data-close-demo-video]").forEach(el=>el.addEventListener("click",closeDemoVideo));document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("#demoVideoModal")?.classList.contains("hidden"))closeDemoVideo();});

/* activity player */
const steps=[
  {
    title:"Mobilidade cervical",
    text:"Movimente lentamente a cabeça para os lados, mantendo os ombros relaxados.",
    time:"00:45",
    image:"assets/mascot-ui/step-1-mobilidade-cervical.png"
  },
  {
    title:"Elevação de ombros",
    text:"Eleve os ombros de forma suave e solte lentamente, aliviando a tensão do pescoço e da parte superior das costas.",
    time:"00:40",
    image:"assets/mascot-ui/step-2-elevacao-ombros.png"
  },
  {
    title:"Abertura de peitoral",
    text:"Alongue a parte frontal do corpo e abra o peito, respirando de forma confortável durante o movimento.",
    time:"00:50",
    image:"assets/mascot-ui/step-3-abertura-peitoral.png"
  },
  {
    title:"Respiração consciente",
    text:"Respire profundamente, inspirando pelo nariz e expirando lentamente pela boca.",
    time:"00:50",
    image:"assets/mascot-ui/step-4-respiracao.png"
  }
];

let step=0;
let sequencePlaying=false;
let sequenceTimer=null;

function stopSequence(){
  sequencePlaying=false;
  clearTimeout(sequenceTimer);
  sequenceTimer=null;
  const btn=$("#playSequence");
  if(btn){
    btn.classList.remove("playing");
    btn.textContent="▶";
    btn.setAttribute("aria-label","Reproduzir sequência");
  }
}

function closePlayer(){
  stopSequence();
  $("#activityPlayer").classList.add("hidden");
}

function playSequence(){
  const btn=$("#playSequence");
  if(!btn) return;

  if(sequencePlaying){
    stopSequence();
    return;
  }

  sequencePlaying=true;
  btn.classList.add("playing");
  btn.textContent="❚❚";
  btn.setAttribute("aria-label","Pausar sequência");

  const advance=()=>{
    if(!sequencePlaying) return;
    if(step<steps.length-1){
      step++;
      updateStep();
      sequenceTimer=setTimeout(advance, 1700);
    }else{
      stopSequence();
    }
  };

  sequenceTimer=setTimeout(advance, 1700);
}

function openPlayerAt(index=0){
  step=Math.max(0,Math.min(steps.length-1,Number(index)||0));
  stopSequence();
  updateStep();
  $("#activityPlayer").classList.remove("hidden");
}

function openPlayer(){
  openPlayerAt(0);
}

$("#closePlayer").onclick=closePlayer;
$("#playSequence")?.addEventListener("click",playSequence);

$("#prevStep").onclick=()=>{
  if(step>0){
    stopSequence();
    step--;
    updateStep();
  }
};

$("#nextStep").onclick=()=>{
  if(step<steps.length-1){
    stopSequence();
    step++;
    updateStep();
  }else{
    closePlayer();
    toast("Atividade concluída! +1 sessão registrada.");
  }
};

function updateStep(){
  $("#stepCounter").textContent=`${step+1} de ${steps.length}`;
  $("#activityTitle").textContent=steps[step].title;
  $("#activityText").textContent=steps[step].text;
  $("#timer").textContent=steps[step].time;
  $("#timerbar").style.width=`${25*(step+1)}%`;
  $("#activityFrame").src=steps[step].image;
  $("#activityFrame").alt=steps[step].title;
  $("#nextStep").textContent=step===steps.length-1?"Concluir atividade":"Próximo exercício";
  $("#prevStep").disabled=step===0;
  $("#prevStep").style.opacity=step===0?".45":"1";
}

/* session + PWA */
try{
 const saved=sessionStorage.getItem("ql_session") || localStorage.getItem("ql_session");
 if(saved){currentUser=JSON.parse(saved);openApp();}
}catch(e){
 localStorage.removeItem("ql_session");
 sessionStorage.removeItem("ql_session");
}

if("serviceWorker" in navigator){
 window.addEventListener("load", async ()=>{
   try{
     const reg=await navigator.serviceWorker.register("sw.js?v=8.0",{updateViaCache:"none"});
     await reg.update();
   }catch(e){}
 });
}
