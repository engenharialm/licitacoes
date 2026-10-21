/* Logo LM + ciclo PDCA animada (Diretoria de Planejamento e Orçamento).
   Mesma coreografia da "Logo PDCA Animada" (LM surge com glitch → P azul →
   setas e letras D, C, A formam o ciclo → P fica branco → nome do setor
   digitado → pausa → glitch de saída), refeita sem bibliotecas.
   Uso: LogoPDCA.montar(elemento, { nome:true, loop:true, pausa:0.8, base:"logo-anim/" })
   - nome:false  → só a marca (para o topo das páginas)
   - loop:false  → toca uma vez e fica parada na logo completa                       */
(function(){
  const W = 380, SC = W / 1285, H = 1224 * SC;          // caixa da logo (imagem original 1285 x 1224)
  const CX = 645 * SC, CY = 610 * SC, R_IN = 270 * SC, START = 15;
  const POS = { P:[605,175], D:[1100,565], C:[683,1015], A:[183,620] };
  const GAP = 56, NOME_W = 470;
  const L1 = "Diretoria de", L2a = "Planejamento", L2b = "e Orçamento";
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const easeOut = t => 1 - Math.pow(1 - clamp(t, 0, 1), 3);
  const easeInOut = t => { t = clamp(t, 0, 1); return t < .5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3) / 2; };
  const rnd = (n, s = 1) => { const x = Math.sin(n * 127.1 + s * 311.7) * 43758.5453; return x - Math.floor(x); };
  const inWin = (T, ws) => ws.some(([a, b]) => T >= a && T < b);
  const pos = k => `${POS[k][0] * SC}px ${POS[k][1] * SC}px`;

  function cues(pausa){
    const d = [["Centro",.8],["Planejar",.7],["Ciclo",2.6],["Setor",1],["Pausa",pausa],["Saida",.4]];
    const c = {}; let t = 0; for (const [k, v] of d){ c[k] = t; t += v; } c.total = t; return c;
  }

  function montar(el, op){
    op = Object.assign({ nome:true, loop:true, pausa:.8, base:"logo-anim/" }, op || {});
    const reduz = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const CU = cues(op.pausa);
    const SW = op.nome ? W + GAP + NOME_W : W, SH = H;
    const img = (f, extra = "") => `<img src="${op.base}${f}.webp" alt="" draggable="false" style="position:absolute;inset:0;width:100%;height:100%;${extra}">`;
    el.classList.add("lmpdca");
    el.innerHTML = `<div class="lmpdca-palco" style="position:relative;width:${SW}px;height:${SH}px;transform-origin:0 0">
      <div class="lmpdca-logo" style="position:absolute;top:0;width:${W}px;height:${H}px">
        <div class="lmpdca-lm" style="position:absolute;inset:0;transform-origin:${CX}px ${CY}px">
          ${img("lm", "mix-blend-mode:screen;filter:sepia(1) saturate(8) hue-rotate(-40deg)")}${img("lm", "mix-blend-mode:screen;filter:sepia(1) saturate(6) hue-rotate(140deg)")}${img("lm")}
        </div>
        ${img("ring", "")}
        <div class="lmpdca-scan" style="position:absolute;left:${CX - 1}px;top:${CY - 205}px;width:2px;height:205px;transform-origin:50% 100%">
          <div style="position:absolute;left:0;top:0;width:2px;height:${205 - R_IN + 6}px;background:var(--lmpdca-acc,#3DF2FF);box-shadow:0 0 14px 3px rgba(61,242,255,.45)"></div></div>
        ${img("d")}${img("c")}${img("a")}${img("pblue", "filter:drop-shadow(0 0 10px rgba(10,110,240,.55))")}${img("p")}
      </div>
      ${op.nome ? `<div class="lmpdca-nome" style="position:absolute;left:${W + GAP}px;top:0;bottom:0;width:${NOME_W}px;display:flex;flex-direction:column;justify-content:center;gap:10px">
        <div class="lmpdca-k" style="font-size:20px;letter-spacing:.18em;text-transform:uppercase;min-height:26px"></div>
        <div style="display:flex;align-items:flex-end;gap:8px"><div class="lmpdca-t" style="font-size:44px;font-weight:700;line-height:1.02;text-transform:uppercase;min-height:92px"></div>
        <div class="lmpdca-cur" style="width:14px;height:40px;margin-bottom:4px;background:var(--lmpdca-acc,#3DF2FF)"></div></div></div>` : ""}
    </div>`;
    const q = s => el.querySelector(s), qa = s => [...el.querySelectorAll(s)];
    const palco = q(".lmpdca-palco"), logo = q(".lmpdca-logo"), lmBox = q(".lmpdca-lm");
    const [lmR, lmB, lmM] = qa(".lmpdca-lm img"), soltos = qa(".lmpdca-logo > img");
    const [ring, D, C, A, Pb, Pw] = soltos, scan = q(".lmpdca-scan");
    const kick = q(".lmpdca-k"), tit = q(".lmpdca-t"), cur = q(".lmpdca-cur");

    // ajusta o palco ao tamanho do elemento
    const ajusta = () => { const k = Math.min(el.clientWidth / SW, el.clientHeight / SH || Infinity); palco.style.transform = `scale(${k})`;
      palco.style.marginLeft = ((el.clientWidth - SW * k) / 2) + "px"; palco.style.marginTop = (((el.clientHeight || SH * k) - SH * k) / 2) + "px"; };
    new ResizeObserver(ajusta).observe(el); ajusta();

    function quadro(T){
      const f = Math.floor(T * 24), exitG = T >= CU.Saida, alive = T < CU.total - .08;
      // posição da logo: centralizada e depois desliza para a esquerda quando o nome entra
      const x = op.nome ? (SW - W) / 2 + (0 - (SW - W) / 2) * easeOut((T - CU.Setor) / .5) : 0;
      logo.style.left = x + "px";
      // LM central com glitch
      const t0 = CU.Centro + .1, g = inWin(T, [[t0, t0 + .55]]) || exitG;
      const on = alive && T >= t0 && (!g || rnd(f, 3) > .3);
      const intro = .85 + .15 * easeOut((T - t0) / .5), cycEnd = CU.Setor - .1;
      const shrink = easeInOut((T - CU.Planejar) / .5) * (1 - easeOut((T - cycEnd) / .45));
      lmBox.style.transform = `scale(${intro * (1 - .3 * shrink)})`;
      const dx = g ? (rnd(f, 5) - .5) * 26 : 0;
      lmM.style.opacity = on ? 1 : 0; lmM.style.transform = `translateX(${dx * .3}px)`;
      lmR.style.opacity = lmB.style.opacity = g && on ? .8 : 0;
      lmR.style.transform = `translateX(${-8 - Math.abs(dx) * .5}px)`; lmB.style.transform = `translateX(${8 + Math.abs(dx) * .5}px)`;
      // anel de setas varrendo em 4 etapas
      const Cc = CU.Ciclo, step = (CU.Setor - Cc) / 4, arc = step * .72;
      const a = [0,1,2,3].reduce((s, i) => s + 90 * easeInOut((T - Cc - i * step) / arc), 0);
      const m = `conic-gradient(from ${START}deg at ${CX}px ${CY}px, #000 0deg ${a}deg, transparent ${a}deg 360deg)`;
      ring.style.maskImage = ring.style.webkitMaskImage = m;
      ring.style.opacity = alive && a > .2 && (!exitG || rnd(f, 11) > .3) ? 1 : 0;
      ring.style.transform = exitG ? `translateX(${(rnd(f, 12) - .5) * 20}px)` : "none";
      scan.style.opacity = T > Cc && a < 359.5 ? 1 : 0; scan.style.transform = `rotate(${START + a}deg)`;
      [[D,"D",0],[C,"C",1],[A,"A",2]].forEach(([im, k, i]) => {
        const tl = Cc + i * step + arc * .75, gl = inWin(T, [[tl, tl + .16]]) || exitG, d = gl ? (rnd(f, 30 + i) - .5) * 14 : 0;
        im.style.opacity = alive && T >= tl && (!gl || rnd(f, 20 + i) > .3) ? 1 : 0;
        im.style.transformOrigin = pos(k);
        im.style.transform = `translate(${d}px, ${gl ? (rnd(f, 31 + i) - .5) * 6 : 0}px) scale(${1.35 - .35 * easeOut((T - tl) / .22)})`;
      });
      // P: azul e maior, ajusta ao tamanho; fica branco quando o ciclo fecha
      const tp = CU.Planejar + .05, tw = Cc + 3 * step + arc * .85;
      const gp = inWin(T, [[tp, tp + .14], [tw, tw + .14]]) || exitG, pIn = alive && T >= tp && (!gp || rnd(f, 40) > .3);
      const dp = gp ? (rnd(f, 50) - .5) * 14 : 0;
      for (const [im, vis, sc] of [[Pb, pIn && T < tw, 1.6 - .6 * easeOut((T - tp) / .45)], [Pw, pIn && T >= tw, 1]]){
        im.style.opacity = vis ? 1 : 0; im.style.transformOrigin = pos("P"); im.style.transform = `translate(${dp}px,0) scale(${sc})`;
      }
      // nome do setor digitado
      if (op.nome){
        const tn = CU.Setor + .3, total = L1.length + L2a.length + L2b.length;
        const typed = Math.floor(total * clamp((T - tn) / .6, 0, 1));
        const cut = (s, from) => s.slice(0, clamp(typed - from, 0, s.length));
        kick.textContent = cut(L1, 0); tit.innerHTML = cut(L2a, L1.length) + "<br>" + cut(L2b, L1.length + L2a.length);
        q(".lmpdca-nome").style.opacity = alive && (!exitG || rnd(f, 7) > .35) ? 1 : 0;
        q(".lmpdca-nome").style.transform = `translateX(${exitG ? (rnd(f, 8) - .5) * 16 : 0}px)`;
        cur.style.opacity = alive && T > tn - .1 && Math.floor(T * 4) % 2 === 0 ? 1 : 0;
      }
    }
    if (reduz){ quadro(CU.Saida - .01); if (cur) cur.style.opacity = 0; return; }
    let t0 = null;
    const fimSemLoop = CU.Saida - .01;
    function tick(ts){
      if (t0 === null) t0 = ts;
      let T = (ts - t0) / 1000;
      if (op.loop) T = T % CU.total;
      else if (T >= fimSemLoop){ quadro(fimSemLoop); if (cur) cur.style.opacity = 0; return; }
      quadro(T); requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
    // pausa quando a aba não está visível (economiza bateria)
    document.addEventListener("visibilitychange", () => { if (!document.hidden && op.loop){ t0 = null; } });
  }
  window.LogoPDCA = { montar };
})();
