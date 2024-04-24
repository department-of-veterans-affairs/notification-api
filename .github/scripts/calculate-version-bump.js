// Version bump utility function
function bumpVersion(labels, versionParts) {
    const isBreakingChange = labels.includes('breaking change');
    const isPatch = labels.some(label => ['hotfix', 'security', 'bug'].includes(label));

    if (isBreakingChange) {
        versionParts[0] += 1;
        versionParts[1] = 0;
        versionParts[2] = 0;
    } else if (labels.some(label => label !== 'hotfix' && label !== 'security' && label !== 'bug' && label !== 'breaking change')) {
        versionParts[1] += 1;
        versionParts[2] = 0;
    } else if (isPatch) {
        versionParts[2] += 1;
    }

    return versionParts.join('.');
}

// Main function to process PR data
const prData = async ({ github, context, core }) => {
    const { owner, repo } = context.repo;

    const latestRelease = await github.rest.repos.getLatestRelease({ owner, repo });
    let currentVersion = latestRelease.data.tag_name.replace(/^v/, '');

    if (!currentVersion.match(/^\d+\.\d+\.\d+$/)) {
        throw new Error("Invalid tag format");
    }

    const labels = context.payload.pull_request.labels.map(label => label.name.toLowerCase());
    let versionParts = currentVersion.split('.').map(x => parseInt(x));

    // Use the bumpVersion function to update version based on labels
    const newVersion = bumpVersion(labels, versionParts);

    core.setOutput("new_version", newVersion);

    const summaryContent = `
	  [insert summary here]
    `;
    require('fs').appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
};

module.exports = prData;

