// Roda antes de `npm run dev`: falha com mensagem clara se as portas já estiverem em uso.
import net from 'node:net';
import { execSync } from 'node:child_process';

const PORTS = { 8040: 'API (FastAPI)', 4240: 'frontend (Angular)' };

const isFree = (port) =>
  new Promise((resolve) => {
    const srv = net.createServer().once('error', () => resolve(false)).once('listening', () => srv.close(() => resolve(true)));
    srv.listen(port, '127.0.0.1');
  });

const run = (cmd) => {
  try {
    return execSync(cmd, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
  } catch {
    return '';
  }
};

// ss é o mais confiável no Linux; lsof como alternativa (macOS)
const owner = (port) => {
  const m = run(`ss -ltnpH 'sport = :${port}'`).match(/users:\(\("([^"]+)",pid=(\d+)/);
  if (m) return { cmd: m[1], pid: m[2] };
  return run(`lsof -nP -iTCP:${port} -sTCP:LISTEN -Fpc`)
    .split('\n')
    .reduce((acc, l) => (l[0] === 'p' ? { ...acc, pid: l.slice(1) } : l[0] === 'c' ? { ...acc, cmd: l.slice(1) } : acc), {});
};

let busy = false;
for (const [port, name] of Object.entries(PORTS)) {
  if (await isFree(Number(port))) continue;
  busy = true;
  const { pid, cmd } = owner(port);
  console.error(`✗ Porta ${port} (${name}) já está em uso${pid ? ` pelo processo ${pid} (${cmd})` : ''}.`);
  if (pid) console.error(`  Para liberar: kill ${pid}`);
}
if (busy) {
  console.error('\nProvavelmente o projeto já está rodando em outro terminal.');
  process.exit(1);
}
