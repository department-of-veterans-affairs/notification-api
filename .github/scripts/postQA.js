// File: .github/scripts/postQA.js
const fs = require('fs');
const prData = require('./prData');

const postQA = async ({ github, context, core }) => {
  try {

	// Retrieve necessary data from prData.js
	const { releaseBranchSha, currentVersion, newVersion, label, prNumber } = await prData({ github, context, core });
	// Logging the data retrieved from prData for verification
	console.log(`Release branch SHA to use for tag: ${releaseBranchSha}`);
	console.log(`Current version from RELEASE_VERSION repo variable: ${currentVersion}`);
	console.log(`Calculated new version (for creating tag and updating RELEASE_VERSION): ${newVersion}`);
	console.log(`Label applied for changes: ${label}`);
	console.log(`PR Number associated with this commit: ${prNumber}`);

	// Determine the semver update type based on the label
	const semverValue = label.includes('breaking change') ? 'MAJOR' :
						label.includes('hotfix') || label.includes('security') || label.includes('bug') ? 'PATCH' : 
						'MINOR';

	const allCapsLabel = label.toUpperCase();

	// Assemble the message content
	const summaryContent = `
### Update Details
- PR Number: #${prNumber}
- The PR label used for versioning is ${allCapsLabel}
This will bump up from the previous release tag will be a ${semverValue} value
This tag will not be created until a merge to the release branch. 
- At the time of this message Release Branch SHA is: ${releaseBranchSha}
	`;

	// Append the summary to the GitHub step summary file
	fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
	console.log('PR summary generated and appended successfully.');
  } catch (error) {
	core.setFailed(`Failed to generate PR summary: ${error.message}`);
	console.error(error);
  }
}

module.exports = postQA;

