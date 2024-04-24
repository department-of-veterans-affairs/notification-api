// File: .github/scripts/postQA.js

const { getLatestReleaseTag, bumpVersion } = require('./versionUtils');
const fs = require('fs');

module.exports = async ({ github, context, core }) => {
    try {
        const prNumber = context.issue.number;
        const { data: pr } = await github.rest.pulls.get({
            owner: context.repo.owner,
            repo: context.repo.repo,
            pull_number: prNumber
        });

        const labels = pr.labels.map(label => label.name);
        const versionParts = await getLatestReleaseTag(github, context);
        const { newVersion, updateType } = bumpVersion(labels, versionParts);

        const summaryContent = `
### Update Details
- Latest Version: ${versionParts.join('.')}
- New Version: ${newVersion} (${updateType} update)
- PR labels: ${labels.join(", ")}
        `;

        fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
        core.setOutput("summary-posted", "true");
    } catch (error) {
        core.setFailed(`Failed to post QA summary: ${error.message}`);
    }
};

