// File: .github/scripts/postQA.js
const fs = require('fs');
const prData = require('./prData');

async function generatePRSummary({ github, context, core }) {
    try {
        const { currentVersion, newVersion, label, prNumber } = await prData({ github, context, core });

        const summaryContent = `
### Update Details
- Latest Version: ${currentVersion}
- New Version: ${newVersion} (${label} update)
- PR Number: #${prNumber}
`;

        fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
    } catch (error) {
        core.setFailed(`Failed to generate PR summary: ${error.message}`);
    }
}

module.exports = { generatePRSummary };

