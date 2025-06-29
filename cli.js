#!/usr/bin/env node

import { spawn } from 'child_process';
import chalk from 'chalk'; 
import ora from 'ora';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

console.log(chalk.cyan.bold('\n✨ Starting Cerebella...\n'));

// Start the main Python server
const mainProcess = spawn('uv', ['run', 'main.py'], {
  cwd: __dirname,
  stdio: 'inherit',
  shell: true
});

// Start the embeddings server with progress indicator
const embeddingsSpinner = ora({
  text: 'Starting embeddings server (this may take a moment)...',
  color: 'yellow'
}).start();

const embeddingsProcess = spawn('text-embeddings-router', [
  '--model-id', 'Qwen/Qwen3-Embedding-0.6B',
  '--port', '8080'
], {
  cwd: __dirname,
  shell: true
});

let embeddingsReady = false;

// Monitor embeddings server output
embeddingsProcess.stdout.on('data', (data) => {
  const output = data.toString();
  
  // Check for ready signal (adjust based on actual output)
  if (output.includes('Ready') || output.includes('Started') || output.includes('Listening')) {
    if (!embeddingsReady) {
      embeddingsReady = true;
      embeddingsSpinner.succeed(chalk.green('Embeddings server ready!'));
      console.log(chalk.cyan('\n🚀 Cerebella is running!\n'));
      console.log(chalk.gray('  Main server: http://localhost:5000 (adjust if different)'));
      console.log(chalk.gray('  Embeddings: http://localhost:8080\n'));
      console.log(chalk.yellow('Press Ctrl+C to stop\n'));
    }
  }
  
  // Show embeddings server output in debug mode
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

// Handle process termination
const cleanup = (signal) => {
  console.log(chalk.yellow(`\n\nReceived ${signal}, shutting down gracefully...`));
  
  // Kill both processes
  if (mainProcess && !mainProcess.killed) {
    mainProcess.kill(signal);
  }
  if (embeddingsProcess && !embeddingsProcess.killed) {
    embeddingsProcess.kill(signal);
  }
  
  // Give processes time to clean up
  setTimeout(() => {
    process.exit(0);
  }, 1000);
};

// Handle various termination signals
process.on('SIGINT', () => cleanup('SIGINT'));
process.on('SIGTERM', () => cleanup('SIGTERM'));
process.on('SIGHUP', () => cleanup('SIGHUP'));

// Handle process errors
mainProcess.on('error', (err) => {
  console.error(chalk.red('Failed to start main server:'), err.message);
  process.exit(1);
});

embeddingsProcess.on('error', (err) => {
  embeddingsSpinner.fail(chalk.red('Failed to start embeddings server'));
  console.error(chalk.red('Error:'), err.message);
  console.error(chalk.yellow('\nMake sure text-embeddings-router is installed:'));
  console.error(chalk.gray('  cargo install text-embeddings-router\n'));
  
  if (mainProcess && !mainProcess.killed) {
    mainProcess.kill();
  }
  process.exit(1);
});

// Handle unexpected exits
mainProcess.on('exit', (code, signal) => {
  if (code !== null && code !== 0) {
    console.error(chalk.red(`Main server exited with code ${code}`));
    cleanup('SIGTERM');
  }
});

embeddingsProcess.on('exit', (code, signal) => {
  if (code !== null && code !== 0 && !embeddingsReady) {
    embeddingsSpinner.fail(chalk.red(`Embeddings server exited with code ${code}`));
    cleanup('SIGTERM');
  }
});