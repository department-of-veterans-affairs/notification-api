// File: .github/scripts/postQA.js
const fs = require('fs');
const prData = require('./prData');

async function generatePRSummary({ github, context, core }) {
  try {
    // Retrieve necessary data from prData.js
    const { releaseBranchSha, currentVersion, newVersion, label, prNumber } = await prData({ github, context, core });

    // Determine the semver update type based on the label
    const semverValue = label.includes('breaking change') ? 'major' :
                        label.includes('hotfix') || label.includes('security') || label.includes('bug') ? 'patch' : 
                        'minor';

    // Assemble the message content
    const summaryContent = `
      ### Update Details
      - Release Branch SHA: ${releaseBranchSha}
      - PR Number: #${prNumber}
      - The PR label used for versioning is ${label}
      This will bump up from the previous release tag will be a ${semverValue} value
      This tag will not be created until a merge to the release branch. 
    `;

    // Append the summary to the GitHub step summary file
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
    console.log('PR summary generated and appended successfully.');
  } catch (error) {
    core.setFailed(`Failed to generate PR summary: ${error.message}`);
    console.error(error);
  }
}

module.exports = { generatePRSummary };

