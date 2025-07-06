#!/usr/bin/env node

import { spawn, execSync } from 'child_process';
import chalk from 'chalk';
import ora from 'ora';
import open from 'open';
import { fileURLToPath } from 'url';
import { dirname } from 'path';
import { existsSync } from 'fs';
import process from 'process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const MAIN_SERVER_PORT = 8421;
const EMBEDDINGS_PORT = 8080;

const CEREBELLA_LOGO = [
  '    .....   ......  .....   ......  .....   ......  ..      ..      .',
  '   ..  ..  ..      ..  ..  ..      ..  ..  ..      ..      ..      ..',
  '  ++      ++....  ++....  ++....  ++...   ++....  ++      ++      + .',
  ' ++      ++      ++ +    ++      ++   +  ++      ++      ++      ++++',
  '**  **  **      **  *   **      **   *  **      **      **      **  *',
  '#####  ######  ##   #  ######  ######  ######  ######  ######  ##   #',
];

async function animateLogo() {
  console.clear();
  console.log('\n');  
  const logoLines = new Array(CEREBELLA_LOGO.length).fill('');
  const totalDuration = 4000;
  const totalChars = CEREBELLA_LOGO.join('').length;
  const charDelay = totalDuration / totalChars;
  
  let charIndex = 0;
  
  for (let lineIndex = 0; lineIndex < CEREBELLA_LOGO.length; lineIndex++) {
    for (let charPos = 0; charPos < CEREBELLA_LOGO[lineIndex].length; charPos++) {
      logoLines[lineIndex] += CEREBELLA_LOGO[lineIndex][charPos];      
      process.stdout.write('\x1b[H');
      console.log('\n');
      logoLines.forEach(line => {
        console.log(chalk.cyan(line));
      });
      
      for (let i = logoLines.length; i < CEREBELLA_LOGO.length; i++) {
        console.log('');
      }
      
      charIndex++;
      
      await new Promise(resolve => setTimeout(resolve, charDelay));
    }
  }
  
  await new Promise(resolve => setTimeout(resolve, 300));
}

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

try {
  execSync('uv --version', { stdio: 'ignore' });
} catch (e) {
  console.log(chalk.yellow('Installing uv package manager...'));
  const installSpinner = ora('Installing uv...').start();
  
  try {
    execSync('curl --version', { stdio: 'ignore' });
  } catch (curlError) {
    installSpinner.fail(chalk.red('curl is not installed'));
    console.error(chalk.red('\nError: curl is required to install uv.'));
    console.error(chalk.yellow('\nPlease install curl first:'));
    console.error(chalk.gray('  macOS: brew install curl'));
    console.error(chalk.gray('  Ubuntu/Debian: sudo apt-get install curl'));
    console.error(chalk.gray('  CentOS/RHEL: sudo yum install curl'));
    console.error(chalk.yellow('\nThen run cerebella again.\n'));
    process.exit(1);
  }
  
  try {
    execSync('curl -LsSf https://astral.sh/uv/install.sh | sh', { 
      stdio: 'pipe',
      shell: true
    });
    
    const uvPath = `${process.env.HOME}/.cargo/bin`;
    process.env.PATH = `${uvPath}:${process.env.PATH}`;
    
    try {
      execSync(`${uvPath}/uv --version`, { stdio: 'ignore' });
      installSpinner.succeed(chalk.green('uv installed successfully!'));
    } catch (verifyError) {
      installSpinner.warn(chalk.yellow('uv installed but not found in PATH'));
      console.log(chalk.yellow('\nPlease restart your terminal or run:'));
      console.log(chalk.gray('  source ~/.bashrc  (or ~/.zshrc on macOS)'));
      console.log(chalk.yellow('\nThen run cerebella again.\n'));
      process.exit(0);
    }
  } catch (installError) {
    installSpinner.fail(chalk.red('Failed to install uv'));
    console.error(chalk.red('\nError installing uv. Please install it manually:'));
    console.error(chalk.gray('  curl -LsSf https://astral.sh/uv/install.sh | sh\n'));
    process.exit(1);
  }
}

const venvPath = `${__dirname}/.venv`;
const isFirstRun = !existsSync(venvPath);

if (isFirstRun) {
  console.log(chalk.yellow('First time setup: Creating Python environment...'));
  console.log(chalk.gray('This may take a minute while dependencies are installed.\n'));
} else {
  console.log(chalk.cyan('Starting Cerebella...\n'));
}

// Always use the cerebella installation directory as the project root
const pythonArgs = ['run', '--project', __dirname, 'python', 'main.py'];
if (shouldStartEmbeddings) {
  pythonArgs.push('--embeddings');
}

const mainProcess = spawn('uv', pythonArgs, {
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
        displayRunningMessage(true).catch(console.error);
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
  setTimeout(() => displayRunningMessage(false).catch(console.error), 100);
}

async function displayRunningMessage(withEmbeddings) {
  await animateLogo();
  
  console.log(chalk.cyan('\nCerebella is running!\n'));
  console.log(chalk.gray(`  Main server: http://localhost:${MAIN_SERVER_PORT}`));
  if (withEmbeddings) {
    console.log(chalk.gray(`  Embeddings: http://localhost:${EMBEDDINGS_PORT}`));
  } else {
    console.log(chalk.gray(`  Embeddings: ${chalk.yellow('disabled')}`));
  }
  console.log(chalk.yellow('\nPress Ctrl+C to stop\n'));
  
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
