// preTagSummary.js
const { prData, getReleaseVersionValue } = require('./prData');
const fs = require('fs');

const preTagSummary = async ({ github, context, core }) => {
    try {
        // Retrieve the current release version and proposed new version from prData
        const { currentVersion, newVersion } = await prData({ github, context, core });

        // Construct the summary content
        const summaryContent = `
### Pre-Tag Release Summary
- Current Release Version: ${currentVersion}
- New Version upon Merge: ${newVersion}
`;

        // Append the summary to the GitHub step summary file or log it
        fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
        console.log('Pre-tag release summary generated and appended successfully.');
    } catch (error) {
        core.setFailed(`Failed to generate pre-tag release summary: ${error.message}`);
        console.error(error);
    }
}

module.exports = preTagSummary;

