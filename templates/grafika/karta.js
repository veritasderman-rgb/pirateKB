/*
 * Sestaví kartu z dat. Data se berou (v tomto pořadí):
 *   1. window.KARTA_DATA (vkládá scripts/render_grafika.py),
 *   2. URL parametr ?data=<URL-kódovaný JSON>,
 *   3. jednotlivé URL parametry (?sablona=podano&nadpis=...&predmet=...&jmeno=...&obec=...).
 * Formát: data.format nebo ?format=1080x1350 (1080x1080 | 1080x1350 | 1080x1920 | 1920x1080).
 * Po vykreslení nastaví window.KARTA_READY = {ok, fit, preteceni: [...]}.
 * Veškerý text se vkládá přes textContent (žádné innerHTML z dat).
 */
(function () {
  'use strict';

  var LOGO_BILE = 'https://pirati.cz/documents/228/logo_napis_white.svg';   // pirati.cz/download, Logotyp – Bílý (inverzní) SVG

  var FORMATY = {
    '1080x1080': 'f-ctverec',
    '1080x1350': 'f-na-vysku',
    '1080x1920': 'f-story',
    '1920x1080': 'f-sirka'
  };

  var VYCHOZI = {
    podano: {
      faze: 'Podáno',
      kicker: 'Žádost podle zákona č. 106/1999 Sb.',
      nadpis: 'Podali jsme *žádost* o informace'
    },
    odpoved: {
      faze: 'Odpověď',
      kicker: 'Odpověď na žádost podle zákona č. 106/1999 Sb.',
      nadpis: 'Úřad odpověděl. *Co jsme zjistili*'
    },
    stiznost: {
      faze: 'Stížnost',
      kicker: 'Stížnost podle § 16a zákona č. 106/1999 Sb.',
      nadpis: 'Úřad mlčí. Podali jsme *stížnost*'
    },
    dotaz: {
      faze: 'Dotaz',
      kicker: 'Dotaz zastupitele',
      nadpis: '*Dotaz* zastupitele'
    }
  };

  // ------------------------------------------------------------------ data
  function nactiData() {
    if (window.KARTA_DATA && typeof window.KARTA_DATA === 'object') return window.KARTA_DATA;
    var q = new URLSearchParams(window.location.search);
    if (q.get('data')) {
      try { return JSON.parse(q.get('data')); } catch (e) { console.error('Neplatný JSON v ?data', e); }
    }
    var d = {};
    ['sablona', 'format', 'faze', 'kicker', 'nadpis', 'predmet', 'urad', 'text', 'zdroj', 'datum',
      'datum_podani', 'lhuta', 'lhuta_do', 'datum_odpovedi', 'datum_stiznosti', 'dni_bez_odpovedi',
      'adresat', 'dotaz', 'logo'].forEach(function (k) {
      if (q.get(k) !== null) d[k] = q.get(k);
    });
    if (q.get('fiktivni') !== null) d.fiktivni = q.get('fiktivni') !== '0';
    d.autor = { jmeno: q.get('jmeno') || '', funkce: q.get('funkce') || '', strana: q.get('strana') || 'Piráti', obec: q.get('obec') || '' };
    var fakta = [];
    for (var i = 1; i <= 3; i++) {
      if (q.get('cislo' + i)) fakta.push({ cislo: q.get('cislo' + i), jednotka: q.get('jednotka' + i) || '', popis: q.get('popis' + i) || '' });
    }
    if (fakta.length) d.fakta = fakta;
    var otazky = q.getAll('otazka');
    if (otazky.length) d.otazky = otazky;
    return d;
  }

  // ------------------------------------------------------------------ DOM pomocníci
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null && text !== '') e.textContent = String(text);
    return e;
  }

  // *slovo* v nadpisu = žluté zvýraznění (jen přes textové uzly)
  function textSeZvyraznenim(rodic, text) {
    String(text || '').split(/(\*[^*]+\*)/).forEach(function (cast) {
      if (!cast) return;
      if (cast.charAt(0) === '*' && cast.charAt(cast.length - 1) === '*' && cast.length > 2) {
        rodic.appendChild(el('span', 'zvyrazneni', cast.slice(1, -1)));
      } else {
        rodic.appendChild(document.createTextNode(cast));
      }
    });
    return rodic;
  }

  function kroky(seznam) {
    var box = el('div', 'kroky');
    box.style.setProperty('--pocet', String(seznam.length));
    seznam.forEach(function (k) {
      var krok = el('div', 'krok ' + (k.stav || 'ceka'));
      krok.appendChild(el('span', 'bod'));
      krok.appendChild(el('div', 'stitek', k.stitek));
      krok.appendChild(el('div', 'datum', k.datum || '—'));
      box.appendChild(krok);
    });
    return box;
  }

  function vychoziKroky(s, d) {
    if (s === 'podano') return [
      { stitek: 'Podáno', datum: d.datum_podani, stav: 'hotovo' },
      { stitek: 'Lhůta ' + (d.lhuta || '15 dní'), datum: d.lhuta_do ? 'do ' + d.lhuta_do : '', stav: 'aktivni' },
      { stitek: 'Odpověď', datum: '', stav: 'ceka' }
    ];
    if (s === 'stiznost') return [
      { stitek: 'Podáno', datum: d.datum_podani, stav: 'hotovo' },
      { stitek: 'Lhůta uplynula', datum: d.lhuta_do, stav: 'varovani' },
      { stitek: 'Stížnost', datum: d.datum_stiznosti, stav: 'aktivni' }
    ];
    if (s === 'dotaz') return [
      { stitek: 'Položeno', datum: d.datum_podani, stav: 'hotovo' },
      { stitek: 'Lhůta ' + (d.lhuta || '30 dní'), datum: d.lhuta_do ? 'do ' + d.lhuta_do : '', stav: 'aktivni' },
      { stitek: 'Odpověď', datum: '', stav: 'ceka' }
    ];
    return [
      { stitek: 'Podáno', datum: d.datum_podani, stav: 'hotovo' },
      { stitek: 'Lhůta ' + (d.lhuta || '15 dní'), datum: d.lhuta_do, stav: 'hotovo' },
      { stitek: 'Odpověď', datum: d.datum_odpovedi, stav: 'hotovo' }
    ];
  }

  function fakta(seznam) {
    var box = el('div', 'fakta' + (seznam.length === 1 ? ' jeden' : ''));
    seznam.slice(0, 3).forEach(function (f) {
      var r = el('div', 'fakt');
      var h = el('div', 'hodnota');
      h.appendChild(el('span', 'cislo', f.cislo));
      if (f.jednotka) h.appendChild(el('span', 'jednotka', f.jednotka));
      r.appendChild(h);
      r.appendChild(el('div', 'popis', f.popis));
      box.appendChild(r);
    });
    return box;
  }

  // ------------------------------------------------------------------ sestavení
  function sestav(d) {
    var s = VYCHOZI[d.sablona] ? d.sablona : 'podano';
    var v = VYCHOZI[s];
    var format = FORMATY[d.format] ? d.format : '1080x1350';
    var wh = format.split('x');
    var root = document.documentElement;
    root.style.setProperty('--w', wh[0] + 'px');
    root.style.setProperty('--h', wh[1] + 'px');

    var karta = document.getElementById('karta');
    karta.className = 'karta ' + FORMATY[format] + ' s-' + s;
    karta.textContent = '';
    karta.appendChild(el('div', 'mrizka'));

    // horní lišta
    var lista = el('header', 'lista');
    var vlevo = el('div', 'lista-vlevo');
    vlevo.appendChild(el('span', 'faze', d.faze || v.faze));
    if (d.autor && d.autor.obec) vlevo.appendChild(el('span', 'misto', d.autor.obec));
    lista.appendChild(vlevo);
    if (d.fiktivni) lista.appendChild(el('span', 'fiktivni', 'Ukázka · fiktivní data'));
    karta.appendChild(lista);

    // obsah
    var obsah = el('main', 'obsah');
    var hlava = el('section', 'hlava');
    hlava.appendChild(el('p', 'kicker', d.kicker || v.kicker));
    hlava.appendChild(textSeZvyraznenim(el('h1', 'nadpis'), d.nadpis || v.nadpis));
    hlava.appendChild(el('div', 'linka'));
    if (d.predmet) hlava.appendChild(el('p', 'predmet', d.predmet));
    if (d.urad || d.adresat) {
      var u = el('p', 'urad');
      u.appendChild(document.createTextNode((s === 'dotaz' ? 'Adresát: ' : 'Úřad: ')));
      u.appendChild(el('strong', '', d.adresat || d.urad));
      hlava.appendChild(u);
    }
    obsah.appendChild(hlava);

    var telo = el('section', 'telo');
    if (s === 'odpoved') {
      if (Array.isArray(d.fakta) && d.fakta.length) telo.appendChild(fakta(d.fakta));
      if (d.text) telo.appendChild(el('p', 'text', d.text));
      if (d.zobrazit_kroky) telo.appendChild(kroky(d.kroky || vychoziKroky(s, d)));
    } else if (s === 'stiznost') {
      if (d.dni_bez_odpovedi) {
        var p = el('div', 'pocitadlo');
        p.appendChild(el('span', 'cislo', d.dni_bez_odpovedi));
        var pp = el('span', 'popis');
        pp.appendChild(document.createTextNode('dní'));
        pp.appendChild(document.createElement('br'));
        pp.appendChild(document.createTextNode('bez odpovědi'));
        p.appendChild(pp);
        telo.appendChild(p);
      }
      telo.appendChild(kroky(d.kroky || vychoziKroky(s, d)));
      if (d.text) telo.appendChild(el('p', 'text', d.text));
    } else if (s === 'dotaz') {
      if (d.dotaz) telo.appendChild(el('blockquote', 'citace', '„' + String(d.dotaz).replace(/^[„"]|[“"]$/g, '') + '“'));
      telo.appendChild(kroky(d.kroky || vychoziKroky(s, d)));
      if (d.text) telo.appendChild(el('p', 'text', d.text));
    } else {
      telo.appendChild(kroky(d.kroky || vychoziKroky(s, d)));
      if (Array.isArray(d.otazky) && d.otazky.length) {
        var box = el('div', 'otazky-box');
        box.appendChild(el('p', 'otazky-nadpis', d.otazky_nadpis || 'Ptáme se'));
        var ol = el('ol', 'otazky');
        d.otazky.slice(0, 3).forEach(function (o) { ol.appendChild(el('li', '', o)); });
        box.appendChild(ol);
        telo.appendChild(box);
      }
      if (d.text) telo.appendChild(el('p', 'text', d.text));
    }
    obsah.appendChild(telo);
    karta.appendChild(obsah);

    // patička: jméno, funkce, obec, zdroj a datum, značka
    var a = d.autor || {};
    var pat = el('footer', 'paticka');
    var autor = el('div', 'autor');
    autor.appendChild(el('div', 'jmeno', a.jmeno || '[jméno zastupitele]'));
    var funkce = [a.funkce, a.strana, a.obec].filter(Boolean).join(' · ');
    autor.appendChild(el('div', 'funkce', funkce || '[funkce · Piráti · obec]'));
    pat.appendChild(autor);

    var znacka = el('div', 'znacka');
    var textova = function () { znacka.textContent = ''; znacka.appendChild(el('span', 'textova', 'PIRÁTI')); };
    if (d.logo === 'text') {
      textova();
    } else {
      var img = new Image();
      img.alt = 'Piráti';
      img.addEventListener('error', textova);
      img.src = (typeof d.logo === 'string' && d.logo) ? d.logo : LOGO_BILE;
      znacka.appendChild(img);
    }
    pat.appendChild(znacka);

    var zdroj = el('div', 'zdroj');
    zdroj.appendChild(el('b', '', 'Zdroj: '));
    zdroj.appendChild(document.createTextNode([d.zdroj || '[zdroj]', d.datum].filter(Boolean).join(' · ')));
    pat.appendChild(zdroj);
    karta.appendChild(pat);
    return karta;
  }

  // ------------------------------------------------------------------ přizpůsobení velikosti
  function pretika(e) {
    return e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1;
  }

  function prizpusob(karta) {
    var root = document.documentElement;
    var obsah = karta.querySelector('.obsah');
    var fit = 1;
    root.style.setProperty('--fit', '1');
    var nadpis = karta.querySelector('.nadpis');
    var siroky = function () { return nadpis.scrollWidth > nadpis.clientWidth + 1; };
    while (fit > 0.56 && (pretika(obsah) || siroky())) {
      fit = Math.round((fit - 0.03) * 100) / 100;
      root.style.setProperty('--fit', String(fit));
    }
    var preteceni = [];
    if (pretika(obsah)) preteceni.push('.obsah');
    if (siroky()) preteceni.push('.nadpis (dlouhé slovo)');
    ['.lista', '.autor', '.paticka'].forEach(function (sel) {
      var e = karta.querySelector(sel);
      if (e && pretika(e)) preteceni.push(sel);
    });
    var zdroj = karta.querySelector('.zdroj');
    if (zdroj && zdroj.scrollHeight > zdroj.clientHeight + 1) preteceni.push('.zdroj (zkráceno na 2 řádky)');
    return { fit: fit, preteceni: preteceni };
  }

  function obrazkyNactene(karta, limitMs) {
    var imgs = Array.prototype.slice.call(karta.querySelectorAll('img'));
    var cekani = imgs.map(function (i) {
      if (i.complete) return Promise.resolve();
      return new Promise(function (ok) { i.addEventListener('load', ok); i.addEventListener('error', ok); });
    });
    return Promise.race([Promise.all(cekani), new Promise(function (ok) { setTimeout(ok, limitMs); })]);
  }

  function hotovo(karta) {
    var vysledek = prizpusob(karta);
    window.KARTA_READY = { ok: vysledek.preteceni.length === 0, fit: vysledek.fit, preteceni: vysledek.preteceni };
    document.body.setAttribute('data-hotovo', '1');
  }

  function start() {
    var data = nactiData();
    var karta = sestav(data);
    var fonty = document.fonts ? Promise.all([
      document.fonts.load('400 100px "Bebas Neue"', 'ŘŮĚ'),
      document.fonts.load('400 30px "Roboto"', 'ěščřžýáíé'),
      document.fonts.load('700 30px "Roboto"', 'ěščřžýáíé'),
      document.fonts.load('500 30px "Roboto"', 'ěščřžýáíé'),
      document.fonts.load('700 20px "Roboto Condensed"', 'ěščřžýáíé')
    ]).then(function () { return document.fonts.ready; }) : Promise.resolve();
    Promise.race([fonty, new Promise(function (ok) { setTimeout(ok, 8000); })])
      .then(function () { return obrazkyNactene(karta, 6000); })
      .then(function () { hotovo(karta); }, function () { hotovo(karta); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
