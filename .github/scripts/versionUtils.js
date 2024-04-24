// path/filename: src/versionUtils.js

// Determines the type of semver update based on labels
function getUpdateType(labels) {
    if (labels.includes('breaking change')) return 'major';
    if (labels.some(label => label === 'feature')) return 'minor';
    if (labels.some(label => ['hotfix', 'security', 'bug'].includes(label))) return 'patch';
    return 'patch'; // Default to patch if no specific label is found
}

async function getLatestReleaseTag(github, context) {
    const owner = context.repo.owner;
    const repo = context.repo.repo;

    try {
        const latestRelease = await github.rest.repos.getLatestRelease({
            owner,
            repo,
        });
        return latestRelease.data.tag_name;
    } catch (error) {
        console.error('Error fetching latest release tag:', error);
        return null; // Handle error appropriately or throw it
    }
}

// still need to add logic for preferring semver values by major, minor, patch
function bumpVersion(labels, versionParts) {
    const updateType = getUpdateType(labels);
    let newVersion = versionParts.join('.');  // Preserve the original version format

    switch (updateType) {
        case 'major':
            versionParts[0] += 1;
            versionParts[1] = 0;
            versionParts[2] = 0;
            break;
        case 'minor':
            versionParts[1] += 1;
            versionParts[2] = 0;
            break;
        case 'patch':
            versionParts[2] += 1;
            break;
    }

    newVersion = versionParts.join('.');
    return { newVersion, updateType };  // Return both new version and update type
}

module.exports = {
    bumpVersion,
    getUpdateType,
    getLatestReleaseTag  // Export the new function
};

