import { execSync } from 'child_process';
import { readFileSync } from 'fs';
import { join } from 'path';
import https from 'https';
import chalk from 'chalk';
import ora from 'ora';
import { spawn } from 'child_process';

/**
 * Check for updates and auto-update if a newer version is available
 * @param {string} packageDir - Directory containing package.json
 * @returns {Promise<boolean>} - Returns true if update check completed (whether updated or not)
 */
export async function checkForUpdates(packageDir) {
  const packageJsonPath = join(packageDir, 'package.json');
  let currentVersion;
  
  try {
    const packageJson = JSON.parse(readFileSync(packageJsonPath, 'utf8'));
    currentVersion = packageJson.version;
  } catch (error) {
    console.error(chalk.yellow('Could not read package.json, skipping update check'));
    return false;
  }

  return new Promise((resolve) => {
    const spinner = ora('Checking for updates...').start();
    
    https.get('https://registry.npmjs.org/cerebella/latest', (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const latestPackage = JSON.parse(data);
          const latestVersion = latestPackage.version;
          
          if (latestVersion && latestVersion !== currentVersion) {
            spinner.succeed(chalk.green(`Update available: ${currentVersion} → ${latestVersion}`));
            console.log(chalk.yellow('\nUpdating cerebella...'));
            
            const updateSpinner = ora('Installing latest version...').start();
            
            try {
              // Try to update globally
              execSync('npm install -g cerebella@latest', { stdio: 'pipe' });
              updateSpinner.succeed(chalk.green('Successfully updated to version ' + latestVersion));
              console.log(chalk.cyan('\nRestarting with the new version...\n'));
              
              // Restart the process with the same arguments
              const args = process.argv.slice(2);
              const child = spawn('cerebella', args, {
                stdio: 'inherit',
                shell: true,
                detached: true
              });
              
              child.unref();
              process.exit(0);
            } catch (updateError) {
              updateSpinner.fail(chalk.red('Failed to auto-update'));
              console.log(chalk.yellow('\nPlease update manually:'));
              console.log(chalk.gray('  npm install -g cerebella@latest\n'));
              resolve(false);
            }
          } else {
            spinner.succeed(chalk.gray(`cerebella is up to date (v${currentVersion})`));
            resolve(true);
          }
        } catch (error) {
          spinner.fail(chalk.yellow('Could not check for updates'));
          resolve(false);
        }
      });
    }).on('error', (error) => {
      spinner.fail(chalk.yellow('Could not check for updates (no internet connection)'));
      resolve(false);
    });
  });
}
