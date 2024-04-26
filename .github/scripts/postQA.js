// File: .github/scripts/postQA.js
const fs = require('fs');
const prData = require('./prData');

async function generatePRSummary({ github, context, core }) {
  try {
    const { releaseBranchSha, currentVersion, newVersion, label, prNumber } = await prData({ github, context, core });

    // Determine semver value based on version changes
    const semverValue = label.includes('breaking') ? 'major' : label.includes('hotfix') || label.includes('security') || label.includes('bug') ? 'patch' : 'minor';

    const summaryContent = `
      ### Update Details
      - Release Branch SHA: ${releaseBranchSha}
      - Latest Version: ${currentVersion}
      - New Version: ${newVersion} (${label} update)
      - PR Number: #${prNumber}
      The PR label used for versioning is ${label}
      This will bump up from the previous release tag a ${semverValue} update
      PR Number: #${prNumber}
      This tag will not be created until a merge to the release branch. 
    `;

    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
    console.log('PR summary generated and appended successfully.');
  } catch (error) {
    core.setFailed(`Failed to generate PR summary: ${error.message}`);
    console.error(error);
  }
}

module.exports = { generatePRSummary };

