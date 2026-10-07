/*
 * Animační šablona řízená scénářem (scenar.json). Vlastní kód, GSAP 3 z CDN.
 *
 * Vstup:  window.SCENAR (vkládá scripts/render_video.py) nebo ?scenar=<URL-kódovaný JSON>.
 * Výstup: window.VIDEO_READY = {ok, delka, fps, sirka, vyska, preteceni, sceny}
 *         window.seek(t)  – nastaví animaci na čas t (s); deterministické, bez reálného času
 *         window.prehrat() – náhled v prohlížeči (reálný čas), jen pro ladění
 *
 * Typy scén: titulek | fakt | citace | casova-osa | vyzva | zaver (popis v templates/video/README.md).
 * Text z dat se vkládá jen přes textContent / textové uzly.
 */
(function () {
  'use strict';

  var LOGO_BILE = 'https://pirati.cz/documents/228/logo_napis_white.svg'; // pirati.cz/download – Logotyp bílý (inverzní)
  var VYSTUP = 0.35;   // délka odchodu scény (s)

  // ------------------------------------------------------------------ pomocníci
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null && text !== '') e.textContent = String(text);
    return e;
  }

  // *zvýraznění* → [{text, zv: bool}]
  function casti(text) {
    var out = [];
    String(text || '').split(/(\*[^*]+\*)/).forEach(function (c) {
      if (!c) return;
      if (c.length > 2 && c.charAt(0) === '*' && c.charAt(c.length - 1) === '*') out.push({ text: c.slice(1, -1), zv: true });
      else out.push({ text: c, zv: false });
    });
    return out;
  }

  // Vloží text jako slova (span.slovo) se zachováním zvýraznění.
  function vlozSlova(rodic, text, trida) {
    rodic.textContent = '';
    var mezera = false;   // předchází slovu mezera? (interpunkce za zvýrazněním se nesmí oddělit)
    casti(text).forEach(function (c) {
      c.text.split(/(\s+)/).forEach(function (s) {
        if (!s) return;
        if (/^\s+$/.test(s)) { rodic.appendChild(document.createTextNode(' ')); mezera = true; return; }
        var w = el('span', 'slovo' + (c.zv ? ' ' + trida : ''), s);
        w.setAttribute('data-zv', c.zv ? '1' : '0');
        w.setAttribute('data-m', mezera ? '1' : '0');
        rodic.appendChild(w);
        mezera = false;
      });
    });
    return rodic;
  }

  // Po přizpůsobení velikosti rozdělí slova do řádků: .maska > .radek (pro maskované odhalení).
  function rozdelNaRadky(rodic, trida) {
    var slova = Array.prototype.slice.call(rodic.querySelectorAll('.slovo'));
    if (!slova.length) return [];
    var radky = [];
    var posledni = null;
    slova.forEach(function (w) {
      var top = Math.round(w.offsetTop);
      if (posledni === null || Math.abs(top - posledni) > 4) { radky.push([]); posledni = top; }
      radky[radky.length - 1].push(w);
    });
    rodic.textContent = '';
    var vnitrni = [];
    radky.forEach(function (r) {
      var m = el('span', 'maska');
      var radek = el('span', 'radek');
      var skupina = null;
      r.forEach(function (w, i) {
        var zv = w.getAttribute('data-zv') === '1';
        var mezera = (i > 0 && w.getAttribute('data-m') === '1') ? ' ' : '';
        if (zv) {
          if (!skupina) { if (mezera) radek.appendChild(document.createTextNode(mezera)); skupina = el('span', trida); radek.appendChild(skupina); skupina.textContent = w.textContent; }
          else skupina.textContent += mezera + w.textContent;
        } else {
          skupina = null;
          radek.appendChild(document.createTextNode(mezera + w.textContent));
        }
      });
      m.appendChild(radek);
      rodic.appendChild(m);
      vnitrni.push(radek);
    });
    return vnitrni;
  }

  function cisloZTextu(s) {
    var t = String(s).replace(/\s| /g, '');
    if (!/^[+-]?\d+(,\d+)?$/.test(t)) return null;
    var des = t.indexOf(',') >= 0 ? t.split(',')[1].length : 0;
    return { hodnota: parseFloat(t.replace(',', '.')), desetin: des };
  }
  function formatujCislo(v, desetin) {
    var s = v.toFixed(desetin).split('.');
    s[0] = s[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    return s.join(',');
  }

  // ------------------------------------------------------------------ scény (DOM)
  function scenaTitulek(s) {
    var e = el('section', 'scena titulek');
    if (s.kicker) e.appendChild(vlozSlova(el('p', 'kicker'), s.kicker, ''));
    e.appendChild(vlozSlova(el('h1', 'nadpis'), s.nadpis, 'zluty'));
    e.appendChild(el('div', 'linka'));
    if (s.podnadpis) e.appendChild(vlozSlova(el('p', 'podnadpis'), s.podnadpis, ''));
    return e;
  }
  function scenaFakt(s) {
    var e = el('section', 'scena fakt');
    if (s.kicker) e.appendChild(vlozSlova(el('p', 'kicker'), s.kicker, ''));
    var h = el('div', 'fakt-hodnota');
    var c = el('span', 'fakt-cislo', s.cislo);
    h.appendChild(c);
    if (s.jednotka) h.appendChild(el('span', 'fakt-jednotka', s.jednotka));
    e.appendChild(h);
    e.appendChild(el('div', 'linka'));
    e.appendChild(vlozSlova(el('p', 'fakt-popis'), s.popis, 'zluty'));
    e.appendChild(zdrojSceny(s.zdroj));
    return e;
  }
  function scenaCitace(s) {
    var e = el('section', 'scena citace-scena');
    if (s.kicker) e.appendChild(vlozSlova(el('p', 'kicker'), s.kicker, ''));
    e.appendChild(vlozSlova(el('blockquote', 'citace'), '„' + String(s.text).replace(/^[„"]|[“"]$/g, '') + '“', 'podtrzeni'));
    e.appendChild(zdrojSceny(s.zdroj));
    return e;
  }
  function scenaOsa(s) {
    var e = el('section', 'scena casova-osa');
    if (s.kicker) e.appendChild(vlozSlova(el('p', 'kicker'), s.kicker, ''));
    if (s.nadpis) e.appendChild(vlozSlova(el('h2', 'nadpis'), s.nadpis, 'zluty'));
    var osa = el('div', 'osa');
    osa.appendChild(el('div', 'osa-cara'));
    osa.appendChild(el('div', 'osa-cara-plna'));
    (s.body || []).forEach(function (b) {
      var bod = el('div', 'osa-bod' + (b.zvyraznit ? ' zvyraznit' : ''));
      bod.appendChild(el('span', 'osa-znacka'));
      var d = el('div', 'maska');
      d.appendChild(el('div', 'radek osa-datum', b.datum));
      bod.appendChild(d);
      bod.appendChild(el('div', 'osa-popis', b.popis));
      if (b.poznamka) bod.appendChild(el('div', 'osa-poznamka', b.poznamka));
      osa.appendChild(bod);
    });
    e.appendChild(osa);
    return e;
  }
  function scenaVyzva(s) {
    var e = el('section', 'scena vyzva');
    var p = el('div', 'vyzva-panel');
    if (s.kicker) p.appendChild(vlozSlova(el('p', 'kicker'), s.kicker, ''));
    p.appendChild(vlozSlova(el('h2', 'nadpis'), s.nadpis, ''));
    if (s.text) p.appendChild(vlozSlova(el('p', 'vyzva-text'), s.text, ''));
    if (s.odkaz) p.appendChild(el('p', 'vyzva-odkaz', s.odkaz));
    e.appendChild(p);
    return e;
  }
  function scenaZaver(s, sc) {
    var e = el('section', 'scena zaver');
    e.appendChild(znacka('zaver-logo', 'zaver-logo-text'));
    e.appendChild(el('div', 'linka'));
    if (s.text) e.appendChild(vlozSlova(el('p', 'zaver-text'), s.text, 'zluty'));
    var zdroj = s.zdroj || sc.zdroj;
    var pozn = [zdroj ? 'Zdroj: ' + zdroj : '', sc.fiktivni ? 'Ukázka s fiktivními daty.' : ''].filter(Boolean).join(' · ');
    if (pozn) e.appendChild(el('p', 'zaver-zdroj', pozn));
    return e;
  }
  function zdrojSceny(text) {
    var z = el('p', 'zdroj-sceny');
    z.appendChild(el('b', '', 'Zdroj: '));
    z.appendChild(document.createTextNode(text || '[doplnit zdroj]'));
    return z;
  }
  function znacka(trida, tridaText) {
    var box = el('div', 'znacka');
    var img = new Image();
    img.className = trida;
    img.alt = 'Piráti';
    img.addEventListener('error', function () { box.textContent = ''; box.appendChild(el('span', tridaText || 'textova', 'PIRÁTI')); });
    img.src = (window.SCENAR && typeof window.SCENAR.logo === 'string' && window.SCENAR.logo !== 'text') ? window.SCENAR.logo : LOGO_BILE;
    if (window.SCENAR && window.SCENAR.logo === 'text') { box.appendChild(el('span', tridaText || 'textova', 'PIRÁTI')); return box; }
    box.appendChild(img);
    return box;
  }

  var STAVITELE = { 'titulek': scenaTitulek, 'fakt': scenaFakt, 'citace': scenaCitace, 'casova-osa': scenaOsa, 'vyzva': scenaVyzva, 'zaver': scenaZaver };

  // ------------------------------------------------------------------ přizpůsobení velikosti
  function prizpusob(scena) {
    var fit = 1;
    var pretika = function () { return scena.scrollHeight > scena.clientHeight + 1 || scena.scrollWidth > scena.clientWidth + 1; };
    scena.style.setProperty('--fit', '1');
    while (fit > 0.5 && pretika()) {
      fit = Math.round((fit - 0.03) * 100) / 100;
      scena.style.setProperty('--fit', String(fit));
    }
    return { fit: fit, pretika: pretika() };
  }

  // ------------------------------------------------------------------ animace
  var pocitadla = [];

  function animujTextRadky(tl, radky, t, stagger) {
    if (!radky.length) return;
    tl.from(radky, { yPercent: 112, duration: 0.8, ease: 'power4.out', stagger: stagger || 0.08 }, t);
  }

  function animuj(tl, typ, e, s, t0, d) {
    var kicker = e.querySelector('.kicker');
    var kr = kicker ? rozdelNaRadky(kicker, '') : [];
    animujTextRadky(tl, kr, t0 + 0.05, 0.05);

    if (typ === 'titulek') {
      animujTextRadky(tl, rozdelNaRadky(e.querySelector('.nadpis'), 'zluty'), t0 + 0.2, 0.09);
      tl.from(e.querySelector('.linka'), { scaleX: 0, duration: 0.7, ease: 'power3.inOut' }, t0 + 0.6);
      var pn = e.querySelector('.podnadpis');
      if (pn) animujTextRadky(tl, rozdelNaRadky(pn, ''), t0 + 0.9, 0.07);
    } else if (typ === 'fakt') {
      var c = e.querySelector('.fakt-cislo');
      tl.from(c, { y: 60, autoAlpha: 0, duration: 0.7, ease: 'power3.out' }, t0 + 0.15);
      var j = e.querySelector('.fakt-jednotka');
      if (j) tl.from(j, { x: -24, autoAlpha: 0, duration: 0.6, ease: 'power3.out' }, t0 + 0.55);
      var n = cisloZTextu(s.cislo);
      if (n) pocitadla.push({ el: c, cil: n.hodnota, desetin: n.desetin, start: t0 + 0.15, delka: Math.min(1.4, d * 0.4), text: s.cislo });
      tl.from(e.querySelector('.linka'), { scaleX: 0, duration: 0.7, ease: 'power3.inOut' }, t0 + 0.7);
      animujTextRadky(tl, rozdelNaRadky(e.querySelector('.fakt-popis'), 'zluty'), t0 + 0.85, 0.07);
      tl.from(e.querySelector('.zdroj-sceny'), { autoAlpha: 0, y: 12, duration: 0.6, ease: 'power2.out' }, t0 + 1.3);
    } else if (typ === 'citace') {
      tl.from(e.querySelector('.citace'), { '--cara': 0, duration: 0.6, ease: 'power3.out' }, t0 + 0.1);
      var radky = rozdelNaRadky(e.querySelector('.citace'), 'podtrzeni');
      animujTextRadky(tl, radky, t0 + 0.3, 0.1);
      var konecTextu = t0 + 0.3 + radky.length * 0.1 + 0.6;
      var podtrzeni = e.querySelectorAll('.podtrzeni');
      if (podtrzeni.length) tl.to(podtrzeni, { backgroundSize: '100% 0.16em', duration: 0.7, ease: 'power2.inOut', stagger: 0.25 }, konecTextu);
      tl.from(e.querySelector('.zdroj-sceny'), { autoAlpha: 0, y: 12, duration: 0.6, ease: 'power2.out' }, konecTextu + 0.2);
    } else if (typ === 'casova-osa') {
      var nad = e.querySelector('.nadpis');
      if (nad) animujTextRadky(tl, rozdelNaRadky(nad, 'zluty'), t0 + 0.15, 0.08);
      var body = Array.prototype.slice.call(e.querySelectorAll('.osa-bod'));
      var start = t0 + (nad ? 0.6 : 0.3);
      var trvani = Math.max(1.2, Math.min(d * 0.55, d - 1.6));
      var plna = e.querySelector('.osa-cara-plna');
      var naSirku = document.getElementById('video').classList.contains('na-sirku');
      tl.fromTo(plna, naSirku ? { scaleX: 0 } : { scaleY: 0 }, naSirku ? { scaleX: 1, duration: trvani, ease: 'none' } : { scaleY: 1, duration: trvani, ease: 'none' }, start);
      body.forEach(function (b, i) {
        var tb = start + (body.length > 1 ? (i / (body.length - 1)) * trvani : 0);
        tl.from(b.querySelector('.osa-znacka'), { scale: 0, duration: 0.35, ease: 'power3.out' }, tb);
        tl.from(b.querySelector('.osa-datum'), { yPercent: 112, duration: 0.6, ease: 'power4.out' }, tb + 0.05);
        tl.from(b.querySelector('.osa-popis'), { autoAlpha: 0, y: 14, duration: 0.5, ease: 'power2.out' }, tb + 0.2);
        var pz = b.querySelector('.osa-poznamka');
        if (pz) tl.from(pz, { autoAlpha: 0, x: -16, duration: 0.45, ease: 'power2.out' }, tb + 0.35);
      });
    } else if (typ === 'vyzva') {
      tl.fromTo(e.querySelector('.vyzva-panel'), { clipPath: 'inset(100% 0% 0% 0%)' }, { clipPath: 'inset(0% 0% 0% 0%)', duration: 0.7, ease: 'power3.inOut' }, t0 + 0.05);
      animujTextRadky(tl, rozdelNaRadky(e.querySelector('.vyzva-panel .nadpis'), ''), t0 + 0.45, 0.08);
      var vt = e.querySelector('.vyzva-text');
      if (vt) animujTextRadky(tl, rozdelNaRadky(vt, ''), t0 + 0.8, 0.06);
      var od = e.querySelector('.vyzva-odkaz');
      if (od) tl.from(od, { autoAlpha: 0, y: 14, duration: 0.5, ease: 'power2.out' }, t0 + 1.1);
    } else if (typ === 'zaver') {
      tl.from(e.querySelector('.znacka'), { autoAlpha: 0, y: 20, duration: 0.8, ease: 'power3.out' }, t0 + 0.1);
      tl.from(e.querySelector('.linka'), { scaleX: 0, duration: 0.6, ease: 'power3.inOut' }, t0 + 0.45);
      var zt = e.querySelector('.zaver-text');
      if (zt) animujTextRadky(tl, rozdelNaRadky(zt, 'zluty'), t0 + 0.6, 0.07);
      var zz = e.querySelector('.zaver-zdroj');
      if (zz) tl.from(zz, { autoAlpha: 0, duration: 0.6 }, t0 + 1.0);
    }
  }

  // ------------------------------------------------------------------ sestavení
  function nactiScenar() {
    if (window.SCENAR) return window.SCENAR;
    var q = new URLSearchParams(window.location.search);
    if (q.get('scenar')) {
      try { window.SCENAR = JSON.parse(q.get('scenar')); return window.SCENAR; } catch (e) { console.error('Neplatný ?scenar', e); }
    }
    throw new Error('Chybí scénář (window.SCENAR nebo ?scenar=).');
  }

  function rozmer(sc) {
    var f = String(sc.format || '1080x1920');
    if (f === '9:16') f = '1080x1920';
    if (f === '16:9') f = '1920x1080';
    var m = /^(\d+)x(\d+)$/.exec(f);
    return m ? [parseInt(m[1], 10), parseInt(m[2], 10)] : [1080, 1920];
  }

  function sestav() {
    var sc = nactiScenar();
    var wh = rozmer(sc);
    var root = document.documentElement;
    root.style.setProperty('--w', wh[0] + 'px');
    root.style.setProperty('--h', wh[1] + 'px');
    var v = document.getElementById('video');
    v.className = 'video ' + (wh[0] > wh[1] ? 'na-sirku' : 'na-vysku');
    v.textContent = '';
    v.appendChild(el('div', 'mrizka'));

    var a = sc.autor || {};
    var hl = el('header', 'hlavicka');
    hl.appendChild(el('span', 'faze', sc.stitek || 'Zákon 106/1999 Sb.'));
    hl.appendChild(el('span', 'misto', a.obec || ''));
    if (sc.fiktivni) hl.appendChild(el('span', 'fiktivni', 'Ukázka · fiktivní data'));
    var pr = el('div', 'prubeh');
    var prI = el('i');
    pr.appendChild(prI);
    hl.appendChild(pr);
    v.appendChild(hl);

    var jev = el('main', 'jeviste');
    v.appendChild(jev);
    var tit = el('div', 'titulky');
    v.appendChild(tit);

    var pat = el('footer', 'paticka');
    var au = el('div', 'autor');
    au.appendChild(el('div', 'jmeno', a.jmeno || ''));
    au.appendChild(el('div', 'funkce', [a.funkce, a.strana, a.obec].filter(Boolean).join(' · ')));
    pat.appendChild(au);
    pat.appendChild(znacka('', 'textova'));
    v.appendChild(pat);

    var sceny = [];
    var t = 0;
    (sc.sceny || []).forEach(function (s, i) {
      var stav = STAVITELE[s.typ];
      if (!stav) { console.warn('Neznámý typ scény', s.typ); return; }
      var e = stav(s, sc);
      e.setAttribute('data-index', String(i));
      jev.appendChild(e);
      var box = null;
      if (s.titulky) { box = el('div', 'box', s.titulky); tit.appendChild(box); }
      var d = Number(s.delka) || 4;
      sceny.push({ typ: s.typ, el: e, data: s, start: t, delka: d, titulky: box });
      t += d;
    });
    return { sc: sc, sceny: sceny, delka: t, wh: wh, prubeh: prI, paticka: pat };
  }

  function postavTimeline(st) {
    var tl = gsap.timeline({ paused: true, defaults: { overwrite: false } });
    var preteceni = [];
    st.sceny.forEach(function (s, i) {
      var f = prizpusob(s.el);
      if (f.pretika) preteceni.push('scéna ' + (i + 1) + ' (' + s.typ + ')');
      tl.set(s.el, { autoAlpha: 1 }, s.start);
      animuj(tl, s.typ, s.el, s.data, s.start, s.delka);
      var posledni = i === st.sceny.length - 1;
      if (!posledni) tl.to(s.el, { autoAlpha: 0, y: -28, duration: VYSTUP, ease: 'power2.in' }, s.start + s.delka - VYSTUP);
      if (s.titulky) {
        tl.fromTo(s.titulky, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.25, ease: 'none' }, s.start + 0.15);
        if (!posledni) tl.to(s.titulky, { autoAlpha: 0, duration: 0.2, ease: 'none' }, s.start + s.delka - 0.25);
        if (s.titulky.scrollHeight > s.titulky.clientHeight + 1) preteceni.push('titulky scény ' + (i + 1));
      }
      if (s.typ === 'zaver') tl.to(st.paticka, { autoAlpha: 0, duration: 0.4, ease: 'power2.out' }, s.start);
    });
    tl.fromTo(st.prubeh, { scaleX: 0 }, { scaleX: 1, duration: st.delka, ease: 'none' }, 0);
    tl.set({}, {}, st.delka);   // přesná délka timeline
    return { tl: tl, preteceni: preteceni };
  }

  function nastavPocitadla(t) {
    pocitadla.forEach(function (p) {
      var x = Math.max(0, Math.min(1, (t - p.start) / p.delka));
      if (x >= 1) { p.el.textContent = p.text; return; }
      var e = 1 - Math.pow(1 - x, 3);
      p.el.textContent = formatujCislo(p.cil * e, p.desetin);
    });
  }

  function obrazky(limit) {
    var imgs = Array.prototype.slice.call(document.querySelectorAll('img'));
    return Promise.race([
      Promise.all(imgs.map(function (i) {
        return i.complete ? Promise.resolve() : new Promise(function (ok) { i.addEventListener('load', ok); i.addEventListener('error', ok); });
      })),
      new Promise(function (ok) { setTimeout(ok, limit); })
    ]);
  }

  function start() {
    var st;
    try { st = sestav(); } catch (e) { window.VIDEO_READY = { ok: false, chyba: String(e) }; return; }
    var fonty = Promise.all([
      document.fonts.load('400 100px "Bebas Neue"', 'ŘŮĚ0123'),
      document.fonts.load('400 30px "Roboto"', 'ěščřžýáíé'),
      document.fonts.load('500 30px "Roboto"', 'ěščřžýáíé'),
      document.fonts.load('700 30px "Roboto"', 'ěščřžýáíé'),
      document.fonts.load('700 24px "Roboto Condensed"', 'ěščřžýáíé'),
      document.fonts.load('500 24px "Roboto Condensed"', 'ěščřžýáíé')
    ]).then(function () { return document.fonts.ready; });
    Promise.race([fonty, new Promise(function (ok) { setTimeout(ok, 8000); })])
      .then(function () { return obrazky(6000); })
      .then(function () {
        if (typeof gsap === 'undefined') throw new Error('GSAP se nenačetl (CDN nedostupné?)');
        gsap.ticker.lagSmoothing(0);
        var r = postavTimeline(st);
        window.seek = function (t) {
          r.tl.totalTime(Math.max(0, Math.min(t, st.delka)), true);
          nastavPocitadla(t);
          return t;
        };
        window.prehrat = function () {
          var t0 = performance.now();
          (function krok() {
            var t = (performance.now() - t0) / 1000;
            window.seek(t);
            if (t < st.delka) requestAnimationFrame(krok);
          })();
        };
        window.seek(0);
        window.VIDEO_READY = {
          ok: r.preteceni.length === 0,
          delka: st.delka,
          fps: Number(st.sc.fps) || 30,
          sirka: st.wh[0],
          vyska: st.wh[1],
          preteceni: r.preteceni,
          sceny: st.sceny.map(function (s) { return { typ: s.typ, start: s.start, delka: s.delka }; })
        };
        if (/[?&]prehrat=1/.test(location.search)) window.prehrat();
      })
      .catch(function (e) { window.VIDEO_READY = { ok: false, chyba: String(e) }; });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
