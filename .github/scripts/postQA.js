// File: .github/scripts/postQA.js

const prData = require('./prData'); // Ensure the path is correct based on your project's directory structure

const fs = require('fs');

// Function to fetch PR data and write a summary
async function generatePRSummary(github, context, core) {
    try {
        const { currentVersion, newVersion, label, prNumber } = await prData({ github, context, core });

        const summaryContent = `
### Update Details
- Latest Version: ${currentVersion}
- New Version: ${newVersion} (${label} update)
- PR Number: #${prNumber}
`;

        // Append the summary to GitHub step summary or any other file used for logs
        fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
    } catch (error) {
        core.setFailed(`Failed to generate PR summary: ${error.message}`);
    }
}

