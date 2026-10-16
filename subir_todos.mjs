// Sobe o portal (http://localhost:4000) e todos os módulos de modulos/, cada um com o próprio
// `npm run dev` e nas próprias portas.
// Uso:  node subir_todos.mjs                 → todos
//       node subir_todos.mjs fraude lgpd     → só esses (pelo slug ou parte do nome da pasta)
// Projeto cuja porta já está ocupada é pulado (provavelmente já está rodando).
// Ctrl+C encerra tudo o que este script iniciou.
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { createConnection } from 'node:net';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const projetos = JSON.parse(readFileSync(join(here, 'projetos.json'), 'utf8'));
const filtro = process.argv.slice(2).map((s) => s.toLowerCase());
const escolhidos = filtro.length
  ? projetos.filter((p) => filtro.some((f) => p.slug === f || p.dir.toLowerCase().includes(f)))
  : projetos;

const CORES = [36, 35, 33, 32, 34, 91, 96, 95];

function portaOcupada(port) {
  const tenta = (host) => new Promise((ok) => {
    const s = createConnection({ port, host });
    s.setTimeout(800);
    s.once('connect', () => { s.destroy(); ok(true); });
    s.once('error', () => ok(false));
    s.once('timeout', () => { s.destroy(); ok(false); });
  });
  return Promise.all([tenta('127.0.0.1'), tenta('::1')]).then((r) => r.some(Boolean));
}

const filhos = [];
let encerrando = false;

function prefixar(stream, out, prefixo) {
  let buf = '';
  stream.on('data', (chunk) => {
    buf += chunk;
    const linhas = buf.split('\n');
    buf = linhas.pop();
    for (const l of linhas) out.write(prefixo + l + '\n');
  });
}

const PORTAL = 4000;
if (await portaOcupada(PORTAL)) {
  console.log(`[portal        ] porta ${PORTAL} já em uso — pulando`);
} else {
  const portal = spawn(process.execPath, [join(here, 'portal', 'server.mjs')], { detached: true });
  prefixar(portal.stdout, process.stdout, '\x1b[1m[portal        ]\x1b[0m ');
  prefixar(portal.stderr, process.stderr, '\x1b[1m[portal        ]\x1b[0m ');
  filhos.push(portal);
}

for (const [i, p] of escolhidos.entries()) {
  const prefixo = `\x1b[${CORES[i % CORES.length]}m[${p.slug.padEnd(14)}]\x1b[0m `;
  const ocupadas = [];
  for (const porta of [p.api, p.web]) if (await portaOcupada(porta)) ocupadas.push(porta);
  if (ocupadas.length) {
    console.log(`${prefixo}porta ${ocupadas.join('/')} já em uso — pulando (já está rodando?)`);
    continue;
  }
  // detached: cada projeto no próprio grupo de processos, para o Ctrl+C derrubar API + web + filhos.
  const filho = spawn('npm', ['run', 'dev'], {
    cwd: join(here, 'modulos', p.dir),
    detached: true,
    env: { ...process.env, FORCE_COLOR: '1' },
  });
  prefixar(filho.stdout, process.stdout, prefixo);
  prefixar(filho.stderr, process.stderr, prefixo);
  filho.on('exit', (code, signal) => {
    if (!encerrando) console.error(`${prefixo}encerrou (${signal ?? code}). Os demais continuam.`);
  });
  filhos.push(filho);
  console.log(`${prefixo}iniciando → web http://localhost:${p.web}${p.web_path}  api http://localhost:${p.api}/docs`);
}

if (!filhos.length) {
  console.log('Nada para iniciar.');
  process.exit(0);
}
console.log(`\n  ▶ Abra o sistema: http://localhost:${PORTAL}   (Ctrl+C encerra tudo)\n`);

function encerrar() {
  if (encerrando) return;
  encerrando = true;
  console.log('\nEncerrando…');
  for (const f of filhos) {
    try { process.kill(-f.pid, 'SIGTERM'); } catch {}
  }
  setTimeout(() => {
    for (const f of filhos) {
      try { process.kill(-f.pid, 'SIGKILL'); } catch {}
    }
    process.exit(0);
  }, 4000);
}
process.on('SIGINT', encerrar);
process.on('SIGTERM', encerrar);
