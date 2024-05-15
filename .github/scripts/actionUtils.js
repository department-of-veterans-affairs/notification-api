// actionUtils.js

// This module provides various utilities that are used by multiple other scripts

const fs = require("fs"); // NodeJs module provides an API for interacting with the file system

/**
 * Appends a provided summary content to the GitHub step summary file.
 * This function is designed to be reused across different modules or scripts.
 *
 * @param {string} summaryContent The content to append to the GitHub step summary.
 * @returns {Promise<void>} A Promise that resolves with no value (undefined) if the append operation succeeds,
 *                          or rejects if an error occurs during the append operation.
 *
 */
async function appendSummary(core, summaryContent) {
  try {
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
    console.log("Summary appended successfully.");
  } catch (error) {
    core.setFailed("Failed to append summary due to: " + error.message);
    console.error(error);
  }
}

async function getReleaseVersionValue(github, owner, repo) {
  const { data } = await github.rest.actions.getRepoVariable({
    owner,
    repo,
    name: "RELEASE_VERSION",
  });
  return data.value;
}

module.exports = { 
  appendSummary,
  getReleaseVersionValue,
}

