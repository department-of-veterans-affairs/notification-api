// actionUtils.js

// This module provides various utilities that are used by multiple other scripts

const fs = require('fs'); // NodeJs module provides an API for interacting with the file system
const { execSync } = require('child_process');

/**
 * Appends a provided summary content to the GitHub step summary file.
 *
 * @param {object} core A reference to the @actions/core package
 * @param {string} summaryContent The content to append to the GitHub step summary.
 * @returns {Promise<void>} A Promise that resolves with no value (undefined) if the append operation succeeds,
 *                          or rejects if an error occurs during the append operation.
 */
async function appendSummary(core, summaryContent) {
  try {
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
    console.log('Summary appended successfully.');
  } catch (error) {
    core.setFailed('Failed to append summary due to: ' + error.message);
    console.error(error);
  }
}

/**
 * Retrieves the latest version from git tags using git describe.
 * This eliminates the race condition by not relying on a shared environment variable.
 * @returns {string} - The latest version from git tags.
 */
function getLatestVersionFromTags() {
  try {
    // Get the latest tag using git describe
    const latestTag = execSync('git describe --tags `git rev-list --tags --max-count=1`', { encoding: 'utf8' }).trim();
    
    // Return the tag as-is (no "v" prefix to remove)
    return latestTag;
  } catch (error) {
    console.error('Error fetching latest tag:', error);
    // Fallback to 0.0.0 if there's an error or no tags exist
    return '0.0.0';
  }
}

module.exports = {
  appendSummary,
  getLatestVersionFromTags,
};
