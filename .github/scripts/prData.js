// File: prData.js
// This module handles fetching and processing data related to pull requests from GitHub.

const fetchPullRequests = async (github, owner, repo, sha) => {
    // Fetches pull requests associated with a specific commit SHA
    return await github.rest.repos.listPullRequestsAssociatedWithCommit({
        owner,
        repo,
        commit_sha: sha,
    });
};

const fetchCurrentReleaseVersion = async (github, owner, repo, variableName) => {
    // Retrieves the current release version from repository secrets or environment variables
    const { data } = await github.rest.actions.getRepoVariable({
        owner,
        repo,
        name: variableName,
    });
    return data.value;
};

const fetchReleaseBranchSha = async (github, owner, repo) => {
    // Fetches the latest commit SHA of the release branch
    try {
        const { data } = await github.rest.repos.getCommit({
            owner,
            repo,
            ref: "heads/release",
        });
        return data.sha;
    } catch (error) {
        console.error('Failed to fetch release branch SHA:', error);
        throw error;
    }
};

const processLabelsAndVersion = (labels, currentVersion) => {
    // Processes labels to determine the type of version update needed and calculates the new version
    let versionParts = currentVersion.split('.').map(x => parseInt(x, 10));
    let appliedLabel = '';

    // Determine the version increment based on the label type
    if (labels.some(label => label.name === 'breaking-change')) {
        versionParts[0] += 1; versionParts[1] = 0; versionParts[2] = 0;
        appliedLabel = 'breaking change';
    } else if (labels.some(label => ['hotfix', 'security', 'bug'].includes(label.name))) {
        versionParts[2] += 1;
        appliedLabel = labels.find(label => ['hotfix', 'security', 'bug'].includes(label.name)).name;
    } else {
        versionParts[1] += 1; versionParts[2] = 0;
        appliedLabel = labels.find(label => label).name; // Default to first label if none matched
    }

    return {
        newVersion: versionParts.join('.'),
        appliedLabel
    };
};

// Main function to get all required PR data
const getPRData = async ({ github, context, core }) => {
    const owner = context.repo.owner;
    const repo = context.repo.repo;
    const sha = context.payload.after;

    try {
        const pullRequestData = await fetchPullRequests(github, owner, repo, sha);
        const currentVersion = await fetchCurrentReleaseVersion(github, owner, repo, "RELEASE_VERSION");
        const releaseBranchSha = await fetchReleaseBranchSha(github, owner, repo);
        const labels = pullRequestData.data[0].labels.map(label => ({
            id: label.id,
            name: label.name,
            description: label.description,
            color: label.color,
        }));
        const prNumber = pullRequestData.data[0].number;
        const { newVersion, appliedLabel } = processLabelsAndVersion(labels, currentVersion);

        return {
            releaseBranchSha,
            currentVersion,
            newVersion,
            label: appliedLabel,
            prNumber
        };
    } catch (error) {
        core.setFailed(`Error processing PR data: ${error.message}`);
        console.error('Error processing PR data:', error);
        return null; // Ensure this is handled in postQA.js
    }
};

// Export the main function
module.exports = { getPRData };

