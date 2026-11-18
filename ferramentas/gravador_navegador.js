(() => {
  const CHAVE = 'amilGravadas';
  let G = [];
  try { G = JSON.parse(localStorage.getItem(CHAVE) || '[]'); } catch (e) { G = []; }
  const caixa = document.createElement('div');
  caixa.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:99999;background:#0d2a4f;color:#fff;' +
    'font:14px/1.4 sans-serif;padding:12px 14px;border-radius:10px;box-shadow:0 6px 20px rgba(0,0,0,.3)';
  const texto = document.createElement('div');
  const baixar = document.createElement('button');
  baixar.textContent = 'Baixar arquivo';
  baixar.style.cssText = 'margin-top:8px;padding:6px 10px;border:0;border-radius:6px;background:#d6b155;' +
    'color:#0d2a4f;font-weight:600;cursor:pointer';
  caixa.append(texto, baixar);
  document.body.appendChild(caixa);
  const mostra = () => {
    const p = G.reduce((s, g) => s + g.itens.length, 0);
    texto.textContent = 'Gravador Amil: ' + G.length + ' buscas, ' + p + ' resultados';
  };
  mostra();
  baixar.onclick = () => {
    const blob = new Blob([JSON.stringify({ gravado: new Date().toISOString(), buscas: G })], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'amil-gravadas-' + new Date().toISOString().slice(0, 10) + '.json';
    document.body.appendChild(a); a.click(); a.remove();
  };
  const P = XMLHttpRequest.prototype, abre = P.open, envia = P.send;
  P.open = function (m, u) { this.__g = String(u); return abre.apply(this, arguments); };
  P.send = function (corpo) {
    if (this.__g && this.__g.includes('RedeCredenciadaCredenciado')) {
      this.addEventListener('load', () => {
        if (this.status !== 200) return;
        let itens, c = null;
        try { itens = JSON.parse(this.responseText); } catch (e) { return; }
        if (!Array.isArray(itens)) return;
        try { c = JSON.parse(corpo); } catch (e) { /* sem corpo */ }
        const k = JSON.stringify(c);
        G = G.filter(g => JSON.stringify(g.corpo) !== k);
        G.push({ corpo: c, quando: new Date().toISOString(), itens });
        try { localStorage.setItem(CHAVE, JSON.stringify(G)); } catch (e) { console.log('memoria cheia: clique em Baixar arquivo'); }
        mostra();
      });
    }
    return envia.apply(this, arguments);
  };
  console.log('Gravador ligado: faca as buscas na pagina');
})();
