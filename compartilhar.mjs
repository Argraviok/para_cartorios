// Publica o portal e os módulos que estão rodando via Cloudflare Quick Tunnel (grátis, sem conta).
// Uso: com o sistema no ar (npm run dev), em outro terminal:  npm run compartilhar
// Imprime o link público do portal. Ctrl+C derruba os túneis (o sistema local continua rodando).
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync, rmSync, existsSync } from 'node:fs';
import { createConnection } from 'node:net';
import { homedir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const projetos = JSON.parse(readFileSync(join(here, 'projetos.json'), 'utf8'));
const ARQ_PUBLICO = join(here, 'portal', 'publico.json');
const BIN = [join(homedir(), '.local/bin/cloudflared'), '/usr/local/bin/cloudflared', '/usr/bin/cloudflared'].find(existsSync);
if (!BIN) {
  console.error('cloudflared não encontrado. Instale em ~/.local/bin/cloudflared.');
  process.exit(1);
}

function aberta(port) {
  const tenta = (host) => new Promise((ok) => {
    const s = createConnection({ port, host });
    s.setTimeout(800);
    s.once('connect', () => { s.destroy(); ok(true); });
    s.once('error', () => ok(false));
    s.once('timeout', () => { s.destroy(); ok(false); });
  });
  return Promise.all([tenta('127.0.0.1'), tenta('::1')]).then((r) => r.some(Boolean));
}

const tuneis = [];

// hostHeader: os servidores do Angular só aceitam Host "localhost"; o túnel reescreve o cabeçalho.
function abrirTunel(nome, port, hostHeader) {
  return new Promise((ok, falha) => {
    const args = ['tunnel', '--no-autoupdate', '--url', `http://localhost:${port}`];
    if (hostHeader) args.push('--http-host-header', hostHeader);
    const t = spawn(BIN, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    tuneis.push(t);
    const timer = setTimeout(() => falha(new Error(`${nome}: túnel não respondeu em 60 s`)), 60000);
    const ler = (chunk) => {
      const m = String(chunk).match(/https:\/\/[a-z0-9-]+\.trycloudflare\.com/);
      if (m) { clearTimeout(timer); ok(m[0]); }
    };
    t.stdout.on('data', ler);
    t.stderr.on('data', ler);
    t.on('exit', (code) => { clearTimeout(timer); falha(new Error(`${nome}: cloudflared saiu (${code})`)); });
  });
}

function encerrar() {
  for (const t of tuneis) { try { t.kill('SIGTERM'); } catch {} }
  rmSync(ARQ_PUBLICO, { force: true });
  console.log('\nTúneis encerrados. O sistema continua rodando só nesta máquina.');
  process.exit(0);
}
process.on('SIGINT', encerrar);
process.on('SIGTERM', encerrar);

if (!(await aberta(4000))) {
  console.error('O portal não está no ar. Rode antes, em outro terminal:  cd ~/MVP_Cartorio && npm run dev');
  process.exit(1);
}

const ativos = [];
for (const p of projetos) if (await aberta(p.web)) ativos.push(p);
console.log(`Abrindo túneis para o portal + ${ativos.length} módulo(s)…`);

try {
  const [portal, ...urls] = await Promise.all([
    abrirTunel('portal', 4000),
    ...ativos.map((p) => abrirTunel(p.slug, p.web, `localhost:${p.web}`)),
  ]);
  const publico = { portal, modulos: Object.fromEntries(ativos.map((p, i) => [p.slug, urls[i]])) };
  writeFileSync(ARQ_PUBLICO, JSON.stringify(publico, null, 2));
  console.log(`\n  ▶ Link para enviar:  ${portal}\n`);
  for (const p of ativos) console.log(`    ${p.nome.padEnd(22)} ${publico.modulos[p.slug]}`);
  const fora = projetos.filter((p) => !ativos.includes(p));
  if (fora.length) console.log(`\n  Fora do ar (não publicados): ${fora.map((p) => p.nome).join(', ')}`);
  console.log('\n  Qualquer pessoa com o link acessa — use só dados fictícios. Ctrl+C encerra os túneis.\n');
} catch (e) {
  console.error(`Falha ao abrir os túneis: ${e.message}`);
  encerrar();
}
