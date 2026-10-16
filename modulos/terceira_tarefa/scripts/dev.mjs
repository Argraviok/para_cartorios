// Sobe o ambiente de desenvolvimento completo: MongoDB (Docker), API FastAPI e Angular.
// Uso: npm run dev   (Ctrl+C encerra API e frontend; o container do Mongo continua rodando)
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const backend = join(root, 'backend');
const frontend = join(root, 'frontend');
const python = join(backend, '.venv', 'bin', 'python');

function fail(msg) {
  console.error(`\n✖ ${msg}\n`);
  process.exit(1);
}

// --- Pré-requisitos --------------------------------------------------------
if (!existsSync(python)) {
  fail('Ambiente Python não encontrado. Rode antes: npm run setup');
}
if (!existsSync(join(frontend, 'node_modules'))) {
  fail('Dependências do frontend não instaladas. Rode antes: npm run setup');
}
if (!existsSync(join(backend, '.env'))) {
  console.warn('⚠ backend/.env não existe: a transcrição pela IA falhará sem ANTHROPIC_API_KEY (busca e revisão funcionam).');
}

// --- MongoDB ---------------------------------------------------------------
console.log('▶ Subindo MongoDB Atlas Local (docker compose)…');
const up = spawnSync('docker', ['compose', 'up', '-d'], { cwd: root, stdio: 'inherit' });
if (up.status !== 0) fail('Falha ao subir o MongoDB. O Docker está rodando?');

const containerId = spawnSync('docker', ['compose', 'ps', '-q', 'mongodb'], { cwd: root, encoding: 'utf8' }).stdout.trim();
process.stdout.write('  aguardando o MongoDB ficar pronto');
for (let i = 0; ; i++) {
  const health = spawnSync('docker', ['inspect', '--format', '{{.State.Health.Status}}', containerId], { encoding: 'utf8' })
    .stdout.trim();
  if (health === 'healthy') break;
  if (i >= 60) fail('MongoDB não ficou pronto em 2 minutos (veja: docker compose logs mongodb).');
  process.stdout.write('.');
  spawnSync('sleep', ['2']);
}
console.log(' ok');

// --- API + Frontend --------------------------------------------------------
const colors = { api: '\x1b[36m', web: '\x1b[35m' };
const children = [];

function run(name, cmd, args, cwd) {
  const child = spawn(cmd, args, { cwd, env: { ...process.env, FORCE_COLOR: '1' } });
  const prefix = `${colors[name]}[${name}]\x1b[0m `;
  const pipe = (stream, out) => {
    let buffer = '';
    stream.on('data', (chunk) => {
      buffer += chunk;
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) out.write(prefix + line + '\n');
    });
  };
  pipe(child.stdout, process.stdout);
  pipe(child.stderr, process.stderr);
  child.on('exit', (code, signal) => {
    if (!shuttingDown) {
      console.error(`${prefix}encerrou (${signal ?? code}). Parando o restante…`);
      shutdown(code ?? 1);
    }
  });
  children.push(child);
}

let shuttingDown = false;
function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) if (child.exitCode === null) child.kill('SIGTERM');
  setTimeout(() => process.exit(code), 1500);
}
process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));

run('api', python, ['-m', 'uvicorn', 'app.main:app', '--reload', '--port', '8050'], backend);
run('web', join(frontend, 'node_modules', '.bin', 'ng'), ['serve', '--port', '4250'], frontend);

console.log('\n  Frontend: http://localhost:4250\n  API:      http://localhost:8050/docs\n');
