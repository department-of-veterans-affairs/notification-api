// actionUtils.js

// This module provides various utilities that are used by multiple other scripts

const fs = require('fs'); // NodeJs module provides an API for interacting with the file system

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
 * Retrieves the latest version from git tags using the GitHub API.
 * This eliminates the race condition by not relying on a shared environment variable.
 * @param {Object} github - The GitHub client instance.
 * @param {string} owner - The owner of the GitHub repository.
 * @param {string} repo - The repository name.
 * @returns {Promise<string>} - A promise resolving to the latest version from git tags.
 */
async function getLatestVersionFromTags(github, owner, repo) {
  try {
    // Fetch up to 100 tags (default to empty array if no data)
    const { data: tags = [] } = await github.rest.repos.listTags({
      owner,
      repo,
      per_page: 100,
    });

    // Extract just the names, keep only strict X.Y.Z, sort descending, grab first
    const latest = tags
      .map(t => t.name)
      .filter(name => /^\d+\.\d+\.\d+$/.test(name))
      .sort((a, b) =>
        // localeCompare with numeric sorting handles "10" > "2" correctly
        b.localeCompare(a, undefined, { numeric: true })
      )[0];

    return latest || '0.0.0';
  } catch (e) {
    console.error('Error fetching tags:', e);
    return '0.0.0';
  }
}

module.exports = {
  appendSummary,
  getLatestVersionFromTags,
};
