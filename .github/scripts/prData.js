// prData.js

// Function to fetch pull requests associated with a commit
async function fetchPullRequests(github, owner, repo, sha) {
    return await github.rest.repos.listPullRequestsAssociatedWithCommit({
        owner,
        repo,
        commit_sha: sha,
    });
}

// Function to fetch the current release version
async function fetchCurrentReleaseVersion(github, owner, repo, variableName) {
    const { data } = await github.rest.actions.getRepoVariable({
        owner,
        repo,
        name: variableName,
    });
    return data.value;
}

// Function to process labels to determine new version and label
function processLabelsAndVersion(labels, currentVersion) {
    let versionParts = currentVersion.split('.').map(x => parseInt(x, 10));
    let appliedLabel;

    if (labels.some(label => label.name === 'breaking-change')) {
        versionParts[0] += 1; versionParts[1] = 0; versionParts[2] = 0;
        appliedLabel = 'breaking change';
    } else if (labels.some(label => ['hotfix', 'security', 'bug'].includes(label.name))) {
        versionParts[2] += 1;
        appliedLabel = labels.find(label => ['hotfix', 'security', 'bug'].includes(label.name)).name;
    } else {
        versionParts[1] += 1; versionParts[2] = 0;
        appliedLabel = labels.find(label => label).name; // Catch-all increment
    }

    return {
        newVersion: versionParts.join('.'),
        appliedLabel
    };
}

// Function to fetch release branch SHA
async function fetchReleaseBranchSha(github, owner, repo) {
    try {
        const { data } = await github.rest.repos.getCommit({
            owner,
            repo,
            ref: "heads/release",
        });
        if (!data || !data.sha) {
            throw new Error("Release branch SHA not found.");
        }
        return data.sha;
    } catch (error) {
        console.error('Failed to fetch release branch SHA:', error);
        throw error; // Re-throw to handle it in the calling function
    }
}

// Main function exported to handle pull request data
module.exports = async ({ github, context, core }) => {
    const owner = context.repo.owner;
    const repo = context.repo.repo;
    const sha = context.payload.after;

    try {
        const pullRequestData = await fetchPullRequests(github, owner, repo, sha);
        const currentVersion = await fetchCurrentReleaseVersion(github, owner, repo, "RELEASE_VERSION");
		const releaseBranchSha = await fetchReleaseBranchSha(github, owner, repo);

        if (!releaseBranchSha) {
            core.setFailed("Release branch SHA is undefined or null.");
            return;
        }

        const labels = pullRequestData.data[0].labels.map(label => ({
            id: label.id,
            name: label.name,
            description: label.description,
            color: label.color,
        }));
        const prNumber = pullRequestData.data[0].number;

        const { newVersion, appliedLabel } = processLabelsAndVersion(labels, currentVersion);

		console.log(`PR Data Summary:\n` +
		  `Release Branch SHA: ${releaseBranchSha}\n` +
		  `Latest Release Tag: ${latestReleaseTag}\n` +  // Assuming this is computed elsewhere
		  `Current Version: ${currentVersion}\n` +
		  `New Version: ${newVersion}\n` +
		  `Applied Label: ${appliedLabel}\n` +
		  `PR Number: ${prNumber}\n` +
		  `Labels: ${labels.map(label => label.name).join(', ')}`);

        return {
            releaseBranchSha: '', // Placeholder, adjust according to your context
            latestReleaseTag: '', // Placeholder, adjust according to your context
            currentVersion,
            newVersion,
            label: appliedLabel,
            prNumber
        };

    } catch (error) {
        core.setFailed(`Error processing PR data: ${error.message}`);
        console.error('Error processing PR data:', error);
        return null; // Ensure to handle null in postQA.js if needed
    }
};

