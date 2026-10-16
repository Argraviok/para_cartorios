// Servidor do portal único (http://localhost:4000).
// Só serve a casca (menu + iframes) e informa o status de cada módulo; os módulos rodam nas próprias portas.
import { createServer } from 'node:http';
import { execFile } from 'node:child_process';
import { readFile, readlink } from 'node:fs/promises';
import { createConnection } from 'node:net';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const PORTA = Number(process.env.PORTAL_PORT || 4000);
const portal = dirname(fileURLToPath(import.meta.url));
const raiz = dirname(portal);
const modulos = join(raiz, 'modulos');

function aberta(port) {
  const tenta = (host) => new Promise((ok) => {
    const s = createConnection({ port, host });
    s.setTimeout(600);
    s.once('connect', () => { s.destroy(); ok(true); });
    s.once('error', () => ok(false));
    s.once('timeout', () => { s.destroy(); ok(false); });
  });
  return Promise.all([tenta('127.0.0.1'), tenta('::1')]).then((r) => r.some(Boolean));
}

// porta -> pasta de trabalho do processo que escuta nela (para saber se é a cópia do portal ou o original)
function donosDasPortas() {
  return new Promise((ok) => {
    execFile('ss', ['-ltnpH'], async (err, out) => {
      const donos = {};
      if (err) return ok(donos);
      for (const linha of out.split('\n')) {
        const m = linha.match(/:(\d+)\s.*pid=(\d+)/);
        if (!m) continue;
        try { donos[m[1]] = await readlink(`/proc/${m[2]}/cwd`); } catch { donos[m[1]] = ''; }
      }
      ok(donos);
    });
  });
}

async function publico() {
  try { return JSON.parse(await readFile(join(portal, 'publico.json'), 'utf8')); } catch { return null; }
}

async function status(viaTunel) {
  const projetos = JSON.parse(await readFile(join(raiz, 'projetos.json'), 'utf8'));
  const pub = viaTunel ? await publico() : null;
  const donos = await donosDasPortas();
  return Promise.all(projetos.map(async (p) => {
    const [api, web] = await Promise.all([aberta(p.api), aberta(p.web)]);
    const dono = donos[p.web] || donos[p.api] || '';
    const origem = !dono ? null : dono.startsWith(join(modulos, p.dir)) ? 'portal'
      : dono.includes(`/${p.dir}`) ? 'original' : 'outro';
    return { ...p, no_ar: { api, web }, origem, publico: pub?.modulos?.[p.slug] ?? null, via_tunel: !!viaTunel };
  }));
}

const TIPOS = { '.html': 'text/html; charset=utf-8', '.json': 'application/json; charset=utf-8' };

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  // Acesso pelo túnel chega com Host *.trycloudflare.com; local chega com localhost.
  const viaTunel = !/^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(req.headers.host || '');
  try {
    if (url.pathname === '/api/modulos') {
      res.writeHead(200, { 'Content-Type': TIPOS['.json'], 'Cache-Control': 'no-store' });
      return res.end(JSON.stringify(await status(viaTunel)));
    }
    // O relatório técnico mostra caminhos e detalhes desta máquina: só para acesso local.
    const arquivo = url.pathname === '/relatorio' && !viaTunel ? join(raiz, 'dashboard.html') : join(portal, 'index.html');
    res.writeHead(200, { 'Content-Type': TIPOS['.html'], 'Cache-Control': 'no-store' });
    res.end(await readFile(arquivo));
  } catch (e) {
    res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end(`Erro no portal: ${e.message}`);
  }
}).listen(PORTA, '127.0.0.1', () => {
  console.log(`Portal no ar: http://localhost:${PORTA}`);
});
