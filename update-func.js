// Auto-update cerebella
async function checkAndUpdate() {
  // Skip update check in CI environments
  if (process.env.CI || process.env.CEREBELLA_NO_UPDATE) {
    return false;
  }
  
  const currentVersion = getCurrentVersion();
  if (!currentVersion) return false;
  
  const updateSpinner = ora('Checking for updates...').start();
  
  try {
    const latestVersion = await fetchLatestVersion();
    
    if (!latestVersion) {
      // Silently fail if we can't fetch the latest version
      updateSpinner.stop();
      return false;
    }
    
    if (isNewerVersion(currentVersion, latestVersion)) {
      updateSpinner.text = `Updating cerebella from v${currentVersion} to v${latestVersion}...`;
      
      // Check if npm or yarn is available
      let packageManager = 'npm';
      try {
        execSync('yarn --version', { stdio: 'ignore' });
        // Check if we're in a yarn global directory
        const globalBin = execSync('yarn global bin', { encoding: 'utf8' }).trim();
        const cerebellaPath = execSync('which cerebella', { encoding: 'utf8' }).trim();
        if (cerebellaPath.startsWith(globalBin)) {
          packageManager = 'yarn';
        }
      } catch (e) {
        // npm is the fallback
      }
      
      // Update using the appropriate package manager
      const updateCommand = packageManager === 'yarn' 
        ? 'yarn global add cerebella@latest' 
        : 'npm install -g cerebella@latest';
      
      execSync(updateCommand, { stdio: 'pipe' });
      
      updateSpinner.succeed(chalk.green(`Updated to cerebella v${latestVersion}!`));
      console.log(chalk.yellow('\nPlease run cerebella again to use the new version.\n'));
      process.exit(0);
    } else {
      // Clear the spinner without any message when already up to date
      updateSpinner.stop();
      return false;
    }
  } catch (error) {
    // Silently fail on update errors
    updateSpinner.stop();
    if (process.env.DEBUG) {
      console.error(chalk.gray('Update check error:'), error.message);
    }
    return false;
  }
}