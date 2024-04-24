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
        return latestRelease.data.tag_name.split('.').map(num => parseInt(num, 10));
    } catch (error) {
        console.error('Error fetching latest release tag:', error);
        return [0, 0, 0]; // Return a default version if no release is found
    }
}

function bumpVersion(labels, versionParts) {
    const updateType = getUpdateType(labels);
    let newVersion = [...versionParts]; // Use a copy to prevent mutating the original array

    switch (updateType) {
        case 'major':
            newVersion[0] += 1;
            newVersion[1] = 0;
            newVersion[2] = 0;
            break;
        case 'minor':
            newVersion[1] += 1;
            newVersion[2] = 0;
            break;
        case 'patch':
            newVersion[2] += 1;
            break;
    }

    newVersion = newVersion.join('.');
    return { newVersion, updateType };  // Return both new version and update type
}

module.exports = {
    bumpVersion,
    getUpdateType,
    getLatestReleaseTag  // Export the new function
};


