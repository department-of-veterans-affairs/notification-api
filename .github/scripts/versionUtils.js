// path/filename: src/versionUtils.js
// Utilities for managing version updates

// Enhanced version bump function that determines update type and performs version increment
function bumpVersion(labels, versionParts) {
    const updateType = getUpdateType(labels);

    switch (updateType) {
        case 'major':
            versionParts[0] += 1; // Increment major version
            versionParts[1] = 0; // Reset minor version
            versionParts[2] = 0; // Reset patch version
            break;
        case 'minor':
            versionParts[1] += 1; // Increment minor version
            versionParts[2] = 0; // Reset patch version
            break;
        case 'patch':
            versionParts[2] += 1; // Increment patch version
            break;
    }
    return versionParts.join('.');
}

// Determines the type of semver update based on labels
function getUpdateType(labels) {
    if (labels.includes('breaking change')) return 'major';
    if (labels.some(label => label === 'feature')) return 'minor';
    if (labels.some(label => ['hotfix', 'security', 'bug'].includes(label))) return 'patch';
    return 'patch'; // Default to patch if no specific label is found
}

// Exporting for usage in other modules
module.exports = {
    bumpVersion,
    getUpdateType
};

