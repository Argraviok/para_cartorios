// Antes do `npm run dev`: encerra instâncias antigas DESTE projeto que ainda ocupam as portas.
// Processos de outros projetos nunca são encerrados — apenas reportados.
import { execSync } from 'node:child_process';
import { readlinkSync } from 'node:fs';
import { resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const PORTS = [8010, 4210];

function holders(port) {
  let out = '';
  try {
    out = execSync(`ss -ltnpH 'sport = :${port}'`, { encoding: 'utf8' });
  } catch {
    return [];
  }
  return [...new Set([...out.matchAll(/pid=(\d+)/g)].map((m) => Number(m[1])))];
}

function describe(pid) {
  try {
    return execSync(`ps -o args= -p ${pid}`, { encoding: 'utf8' }).trim().slice(0, 100);
  } catch {
    return '?';
  }
}

function cwdOf(pid) {
  try {
    return readlinkSync(`/proc/${pid}/cwd`);
  } catch {
    return '';
  }
}

let blocked = false;
for (const port of PORTS) {
  for (const pid of holders(port)) {
    if (cwdOf(pid).startsWith(ROOT)) {
      console.log(`[predev] porta ${port}: encerrando instância anterior (pid ${pid}) — ${describe(pid)}`);
      try {
        process.kill(pid, 'SIGTERM');
      } catch {}
    } else {
      blocked = true;
      console.error(`[predev] porta ${port} ocupada por outro programa (pid ${pid}): ${describe(pid)}`);
    }
  }
}
if (blocked) process.exit(1);

// Aguarda as portas liberarem (até ~5 s)
for (let i = 0; i < 25 && PORTS.some((p) => holders(p).length); i++) {
  execSync('sleep 0.2');
}
