(async () => {
  // Varredura da busca avancada da Amil (rede credenciada, saude), feita pela propria pagina:
  // https://www.amil.com.br/institucional/#/servicos/saude/rede-credenciada/amil/busca-avancada
  // Para cada estado, plano e municipio: tipos de servico, especialidades e prestadores. A busca
  // de uma cidade traz a regiao: a cidade com as mesmas listas de outra ja varrida e conferida
  // com 3 buscas; se bate, fica no grupo dela, sem refazer tudo. No fim de cada estado baixa
  // amil-<UF>-<data>.json.gz. amilSalvar('PR') baixa o que ja veio, a qualquer momento.
  const UFS = window.__amilUfs || ['PR', 'SC', 'SP'];
  const PRODUTOS = {
    PR: { bronze: [1123], prata: [1079], ouro: [1074], platinum: [1081], s80: [877], s380: [884],
          s450: [879], s750: [880], black: [1134, 1136], s2500: [881], s6500black: [882] },
    SC: { prata: [1079], ouro: [1074], platinum: [1081], platmais: [1069], s80sc: [1004], s380: [884],
          s450: [879], s750: [880] },
    SP: { prata: [1079], ouro: [1074], platinum: [1081], s380: [884], s450: [879], s750: [880],
          black: [1134, 1136], s2500: [881], s6500black: [882] },
  };
  const API = 'api/InstitucionalMiddleware/', BAIRRO = 'TODOS OS BAIRROS', PARALELO = 3;
  const ESPERA = window.__amilEspera || [3000, 10000, 30000, 60000, 120000];
  const ip = decodeURIComponent((document.cookie.match(/(?:^|; )clientIp=([^;]*)/) || [])[1] || '');
  const dorme = ms => new Promise(r => setTimeout(r, ms));
  const enc = s => encodeURI(String(s).replace(/\./g, '@').replace(/\//g, '$'));
  const lista = x => (Array.isArray(x) ? x : []);
  const inicio = Date.now();
  let feitas = 0, falhas = 0, seguidas = 0, parar = false, onde = '';
  const log = m => console.log('[Amil ' + Math.round((Date.now() - inicio) / 60000) + ' min] ' + m);
  window.__amil = window.__amil || {};

  function xhr(metodo, url, corpo) {
    return new Promise(ok => {
      const x = new XMLHttpRequest();
      x.open(metodo, API + url);
      x.setRequestHeader('Accept', 'application/json, text/plain, */*');
      if (corpo) x.setRequestHeader('Content-Type', 'application/json;charset=utf-8');
      x.setRequestHeader('CorrelationId', crypto.randomUUID());
      x.setRequestHeader('Authorization', 'Bearer undefined');
      if (ip) x.setRequestHeader('clientIp', ip);
      x.setRequestHeader('Access-Control-Allow-Origin', '*');
      x.timeout = 120000;
      x.onloadend = () => {
        let j = null;
        try { j = JSON.parse(x.responseText); } catch (e) { /* vazio */ }
        ok({ status: x.status, j });
      };
      x.send(corpo ? JSON.stringify(corpo) : null);
    });
  }
  // 200: a resposta; 404: nada encontrado; o resto e tentado de novo com pausa. Muitas falhas
  // seguidas: pausa de 5 minutos; se continuar, para e baixa o que ja veio.
  async function pede(metodo, url, corpo) {
    for (let t = 0; t <= ESPERA.length && !parar; t++) {
      const r = await xhr(metodo, url, corpo);
      feitas++;
      if (r.status === 200) { seguidas = 0; return r.j; }
      if (r.status === 404) { seguidas = 0; return []; }
      falhas++; seguidas++;
      if (seguidas === 40) {
        log('muitas falhas seguidas (' + r.status + '); pausa de 5 minutos');
        await dorme(300000);
      } else if (seguidas >= 80) {
        log('a busca continua recusando (' + r.status + '); parando e baixando o que ja veio');
        parar = true;
        break;
      }
      if (t < ESPERA.length) await dorme(ESPERA[t]);
    }
    return null;
  }
  async function emParalelo(itens, f) {
    let i = 0;
    const out = new Array(itens.length);
    await Promise.all(Array.from({ length: PARALELO }, async () => {
      while (i < itens.length && !parar) { const k = i++; out[k] = await f(itens[k]); }
    }));
    return out;
  }
  const chave = (it, a) => [it.codigoInterno, a.cep || '', a.numero || '', a.logradouro || ''].join('|');
  function assinatura(itens) {
    const s = [...new Set(itens.flatMap(it => lista(it.enderecoRedeCredenciada).map(a => chave(it, a))))].sort().join('\n');
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return (h >>> 0).toString(36) + ':' + s.length;
  }

  async function estado(uf) {
    const D = window.__amil[uf] = { uf, data: new Date().toISOString().slice(0, 10), fonte: location.href,
      produtos: PRODUTOS[uf], redes: {}, municipios: {}, grupos: {}, unidades: {}, erros: [], completo: false };
    const add = (rede, rep, tipo, esp, itens) => {
      for (const it of itens) {
        for (const a of lista(it.enderecoRedeCredenciada)) {
          const k = chave(it, a);
          const u = D.unidades[k] || (D.unidades[k] = {
            cod: it.codigoInterno, nome: it.nomeFantasia || it.nomePrestador, prestador: it.nomePrestador,
            razao: it.nomeRazaoSocial, doc: it.documento, pessoa: it.tipoPessoa,
            registro: it.registroConselhoProfissional, titulo: it.tituloEspecializacao, site: it.site,
            vip: it.prestadorVip, oneBlack: it.indOneBlack, descred: it.emDescredenciamento,
            horario: it.horarioEspecial, classif: it.classificacoes, acomod: it.acomodacao,
            proprio: it.indRedePropria, subregiao: it.subRegiao,
            tipoLog: a.tipoLogradouro, end: a.logradouro, num: a.numero, compl: a.complemento, cep: a.cep,
            bairro: a.bairroRedeCredenciada, cidade: a.municipio, uf: a.uf, lat: a.coordenadaY,
            lon: a.coordenadaX, tel: a.telefones, whats: a.whatsapps, ref: a.referenciaLocalizacao,
            esp: {}, pp: {} });
          const es = u.esp[tipo] || (u.esp[tipo] = []);
          if (!es.includes(esp)) es.push(esp);
          const pp = u.pp[rede] || (u.pp[rede] = []);
          if (!pp.includes(rep)) pp.push(rep);
        }
      }
    };
    const planos = lista(await pede('GET', 'RedeCredenciadaPlanos?operadora=SAUDE'));
    const redes = [...new Set(Object.values(PRODUTOS[uf]).flat())];
    for (const [n, rede] of redes.entries()) {
      if (parar) break;
      const p = planos.filter(x => x.codigoRede === rede);
      const ctx = await pede('GET', 'RedeCredenciadaContexto?modalidade=SAUDE&codigoRede=' + rede);
      const R = D.redes[rede] = { nomes: [...new Set(p.map(x => x.nomeDoPlano).filter(Boolean))].slice(0, 5),
        contexto_resposta: ctx, corpo: null };
      // contexto e operadora do pedido: o da pagina (AMIL / "AMIL, AMIL_PLANOS"); se nao trouxer
      // ninguem, os do plano e os da resposta de contexto
      const opcoes = [{ operadora: 'AMIL, AMIL_PLANOS', contexto: 'AMIL' }];
      for (const x of [p[0], Array.isArray(ctx) ? ctx[0] : ctx]) {
        if (x && x.contexto && x.operadora) opcoes.push({ operadora: x.operadora, contexto: x.contexto });
      }
      const busca = (mun, tipo, esp, corpo) => pede('POST', 'RedeCredenciadaCredenciado', {
        codigoRede: rede, uf, municipio: mun, bairro: BAIRRO, especialidade: esp, tipoServico: tipo,
        operadora: (corpo || R.corpo).operadora, modalidade: 'SAUDE', contexto: (corpo || R.corpo).contexto });
      const muns = lista(await pede('GET', 'RedeCredenciadaMunicipio/' + rede + '/SAUDE/' + uf))
        .map(m => m.Municipio).filter(Boolean);
      D.municipios[rede] = muns;
      D.grupos[rede] = {};
      const reps = [];
      for (const [m, mun] of muns.entries()) {
        if (parar) break;
        onde = uf + ' · plano ' + rede + ' (' + (n + 1) + '/' + redes.length + ') · ' + mun + ' (' + (m + 1) + '/' + muns.length + ')';
        const tipos = lista(await pede('GET', 'RedeCredenciadaTipoServico/' + rede + '/SAUDE/' + uf + '/' + enc(mun) + '/' + enc(BAIRRO)))
          .map(t => t.NIVEL1_CAPITULO).filter(t => t && t !== 'NOME DO PROCEDIMENTO');
        const listas = {};
        await emParalelo(tipos, async t => {
          listas[t] = lista(await pede('GET', 'RedeCredenciadaEspecialidade/' + rede + '/SAUDE/' + uf + '/' + enc(mun) +
            '/' + enc(BAIRRO) + '/' + enc(t))).map(e => e.NIVEL2_ELEMENTODIVULGACAO).filter(Boolean);
        });
        const sig = JSON.stringify(Object.keys(listas).sort().map(t => [t, listas[t].slice().sort()]));
        const pares = [];
        for (const t of Object.keys(listas).sort()) for (const e of listas[t]) pares.push([t, e]);
        if (!R.corpo && pares.length) {
          const prova = pares.find(x => x[0] === 'HOSPITAIS PARA INTERNACAO') || pares[0];
          for (const o of opcoes) {
            const r = await busca(mun, prova[0], prova[1], o);
            if (r && lista(r).length) { R.corpo = o; break; }
          }
          R.corpo = R.corpo || opcoes[0];
        }
        // mesma regiao de uma cidade ja varrida? 3 buscas conferem
        let grupo = null;
        for (const X of reps.filter(r => r.sig === sig && r.checks.length).slice(0, 6)) {
          let igual = true;
          for (const c of X.checks) {
            const r = await busca(mun, c.tipo, c.esp);
            if (r === null || assinatura(lista(r)) !== c.h) { igual = false; break; }
          }
          if (igual) { grupo = X; break; }
        }
        if (grupo) { D.grupos[rede][grupo.mun].push(mun); continue; }
        const res = await emParalelo(pares, async ([t, e]) => {
          const r = await busca(mun, t, e);
          if (r === null) { D.erros.push({ rede, mun, tipo: t, esp: e }); return null; }
          add(rede, mun, t, e, lista(r));
          return { tipo: t, esp: e, n: lista(r).length, h: assinatura(lista(r)) };
        });
        const checks = [], vistos = new Set();
        for (const x of res.filter(x => x && x.n).sort((a, b) => b.n - a.n)) {
          if (!vistos.has(x.tipo)) { vistos.add(x.tipo); checks.push(x); }
          if (checks.length === 3) break;
        }
        reps.push({ mun, sig, checks });
        D.grupos[rede][mun] = [mun];
      }
    }
    D.completo = !parar;
    D.consultas = feitas;
    D.minutos = Math.round((Date.now() - inicio) / 60000);
    return D;
  }

  async function salvar(uf) {
    const D = window.__amil[uf];
    if (!D) return console.log('nada de ' + uf + ' ainda');
    const saida = Object.assign({}, D, { unidades: Object.values(D.unidades) });
    let blob = new Blob([JSON.stringify(saida)], { type: 'application/json' }), nome = 'amil-' + uf + '-' + D.data + '.json';
    if (window.CompressionStream) {
      blob = await new Response(blob.stream().pipeThrough(new CompressionStream('gzip'))).blob();
      nome += '.gz';
    }
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    a.remove();
    log('baixado ' + nome + ' (' + Object.keys(D.unidades).length + ' enderecos, ' + Math.round(blob.size / 1024) + ' KB)');
  }
  window.amilSalvar = salvar;

  const relogio = setInterval(() => {
    log(onde + ' · ' + feitas + ' consultas · ' + falhas + ' falhas');
    document.title = 'Amil ' + onde;
  }, 30000);
  log('comecando: ' + UFS.join(', ') + (ip ? '' : ' (sem clientIp no cookie)'));
  for (const uf of UFS) {
    if (parar) break;
    const D = await estado(uf);
    log(uf + (D.completo ? ' completo' : ' interrompido') + ': ' + Object.keys(D.unidades).length + ' enderecos, ' +
        D.erros.length + ' buscas com erro');
    await salvar(uf);
  }
  clearInterval(relogio);
  document.title = 'Amil: varredura terminada';
  log(parar ? 'varredura interrompida: mande os arquivos baixados' : 'varredura terminada: mande os arquivos baixados');
})();
