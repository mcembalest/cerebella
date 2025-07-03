#!/usr/bin/env node

import { spawn } from 'child_process';
import chalk from 'chalk';
import ora from 'ora';
import open from 'open';
import { fileURLToPath } from 'url';
import { dirname } from 'path';
import process from 'process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const MAIN_SERVER_PORT = 8421;
const EMBEDDINGS_PORT = 8080;

const args = process.argv.slice(2);
const showHelp = args.includes('--help') || args.includes('-h');
const enableEmbeddings = args.includes('--embeddings') || args.includes('-e');
const noEmbeddings = args.includes('--no-embeddings');
const shouldStartEmbeddings = enableEmbeddings && !noEmbeddings;

if (showHelp) {
  console.log(`
${chalk.cyan.bold('Cerebella')} - this is how coding with AI should feel

${chalk.yellow('Usage:')}
  cerebella [options]

${chalk.yellow('Options:')}
  --embeddings, -e    Start with embeddings server (requires text-embeddings-router)
  --no-embeddings     Explicitly disable embeddings server
  --help, -h          Show this help message

${chalk.gray('By default, Cerebella runs without the embeddings server.')}
${chalk.gray('To install text-embeddings-router: cargo install text-embeddings-router')}
`);
  process.exit(0);
}

const pythonArgs = ['run', 'main.py'];
if (shouldStartEmbeddings) {
  pythonArgs.push('--embeddings');
}

const mainProcess = spawn('uv', pythonArgs, {
  cwd: __dirname,
  stdio: 'inherit',
  shell: true
});

let embeddingsProcess = null;
let embeddingsSpinner = null;
let embeddingsReady = false;

if (shouldStartEmbeddings) {
  embeddingsSpinner = ora({text: 'Starting embeddings server...', color: 'yellow'}).start();
  embeddingsProcess = spawn('text-embeddings-router', [
    '--model-id', 'Qwen/Qwen3-Embedding-0.6B',
    '--port', EMBEDDINGS_PORT.toString()
  ], {cwd: __dirname, shell: true});
  
  embeddingsProcess.stdout.on('data', (data) => {
    const output = data.toString();
    if (output.includes('Ready') || output.includes('Listening') || output.includes('Started')) {
      if (!embeddingsReady) {
        embeddingsReady = true;
        embeddingsSpinner.succeed(chalk.green('Embeddings server ready'));
        displayRunningMessage(true);
      }
    }
    if (process.env.DEBUG) {
      console.log(chalk.gray('[embeddings]'), output.trim());
    }
  });
  
  embeddingsProcess.stderr.on('data', (data) => {
    const error = data.toString();
    if (!embeddingsReady) {
      embeddingsSpinner.text = `Starting embeddings server: ${error.trim()}`;
    } else if (process.env.DEBUG) {
      console.error(chalk.red('[embeddings error]'), error.trim());
    }
  });
  
  embeddingsProcess.on('error', (err) => {
    if (embeddingsSpinner) embeddingsSpinner.fail(chalk.red('Failed to start embeddings server'));
    console.error(chalk.red('Error:'), err.message);
    console.error(chalk.yellow('\nMake sure text-embeddings-router is installed:'));
    console.error(chalk.gray('  cargo install text-embeddings-router\n'));
    console.error(chalk.yellow('You can continue without embeddings by running: cerebella --no-embeddings\n'));
    
    if (mainProcess && !mainProcess.killed) {
      mainProcess.kill();
    }
    process.exit(1);
  });
  
  embeddingsProcess.on('exit', (code, signal) => {
    if (code !== null && code !== 0 && !embeddingsReady) {
      if (embeddingsSpinner) embeddingsSpinner.fail(chalk.red(`Embeddings server exited with code ${code}`));
      cleanup('SIGTERM');
    }
  });
} else {
  setTimeout(() => displayRunningMessage(false), 100);
}

function displayRunningMessage(withEmbeddings) {
  console.log(chalk.cyan('\nCerebella is running!\n'));
  console.log(chalk.gray(`  Main server: http://localhost:${MAIN_SERVER_PORT}`));
  if (withEmbeddings) {
    console.log(chalk.gray(`  Embeddings: http://localhost:${EMBEDDINGS_PORT}`));
  } else {
    console.log(chalk.gray(`  Embeddings: ${chalk.yellow('disabled')}`));
  }
  console.log(chalk.yellow('\nPress Ctrl+C to stop\n'));
  
  // Automatically open the browser
  const url = `http://localhost:${MAIN_SERVER_PORT}`;
  open(url).catch(err => {
    console.log(chalk.gray(`Could not auto-open browser: ${err.message}`));
    console.log(chalk.gray(`Please manually open: ${url}`));
  });
}

const cleanup = (signal) => {
  const processes = [mainProcess, embeddingsProcess].filter(Boolean);
  processes.forEach(proc => {
    if (!proc.killed) {
      proc.kill(signal);
    }
  });
  
  setTimeout(() => process.exit(0), 1000);
};
['SIGINT', 'SIGTERM', 'SIGHUP'].forEach(signal => {
  process.on(signal, () => cleanup(signal));
});
mainProcess.on('error', (err) => {
  console.error(chalk.red('Failed to start main server:'), err.message);
  process.exit(1);
});

mainProcess.on('exit', (code, signal) => {
  if (code !== null && code !== 0) {
    cleanup('SIGTERM');
  }
});
