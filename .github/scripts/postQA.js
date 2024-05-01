// File: postQA.js
// This script generates a summary for a pull request and appends it to the GitHub Actions step summary.

const fs = require('fs');
const { getPRData } = require('./prData'); // Import the function from prData.js

const generatePRSummary = async ({ github, context, core }) => {
    try {
		const prDataResult = await getPRData({ github, context, core });
		if (!prDataResult) {
			console.error("Failed to fetch pull request data.");
			return;
		}

        const { releaseBranchSha, currentVersion, newVersion, label, prNumber } = await getPRData({ github, context, core });

        // Determine the semantic versioning update type based on the label
        const semverValue = label.includes('breaking change') ? 'MAJOR' :
                            label.includes('hotfix') || label.includes('security') || label.includes('bug') ? 'PATCH' : 
                            'MINOR';

        // Convert label to uppercase for display
        const allCapsLabel = label.toUpperCase();

        // Prepare the summary content with placeholders filled by dynamic data
        const summaryContent = `
### Update Details
- PR Number: #${prNumber}
- The PR label used for versioning is ${allCapsLabel}
This will bump up from the previous release tag will be a ${semverValue} value
This tag will not be created until a merge to the release branch. 
- At the time of this message Release Branch SHA is: ${releaseBranchSha}
        `;

        // Append the generated summary to the GitHub step summary file
        fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
        console.log('PR summary generated and appended successfully.');
    } catch (error) {
        core.setFailed(`Failed to generate PR summary: ${error.message}`);
        console.error(error);
    }
};

// Export the function for use in GitHub Actions
module.exports = { generatePRSummary };

