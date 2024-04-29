// File: .github/scripts/createAndPushTag.js
const prData = require('./prData');

async function createAndPushTag({ github, context, core }) {
    const owner = context.repo.owner;
    const repo = context.repo.repo;
    const ref = "heads/release"; // This should match your branch name accurately

    try {
        // Retrieve the latest commit SHA from the release branch
        const { data } = await github.rest.repos.getCommit({
            owner,
            repo,
            ref
        });

        if (!data || !data.sha) {
            throw new Error("No SHA found for the release branch");
        }

        console.log("Release branch SHA: " + data.sha);

        // Retrieve PR data to decide the new version tag
        const { releaseBranchSha, currentVersion, newVersion, label, prNumber } = await prData({github, context, core});

        // Logging the data retrieved from prData for verification
        console.log(`Retrieved release branch SHA: ${releaseBranchSha}`);
        console.log(`Current version from tag associated with latest Release: ${currentVersion}`);
        console.log(`Calculated new version: ${newVersion}`);
        console.log(`Label applied for changes: ${label}`);
        console.log(`PR Number: ${prNumber}`);

        // Verify the completeness and correctness of the data before proceeding
        if (!releaseBranchSha || !currentVersion || !newVersion || !label || !prNumber) {
            throw new Error("One or more required pieces of information are missing, cannot proceed with tagging.");
        }

        // Additional logic could go here for creating and pushing a tag if all checks are passed
        // For example, you might check that the newVersion is indeed higher than the currentVersion using semver.compare()

    } catch (error) {
        core.setFailed("Failed to process due to: " + error.message);
        console.error(error);
    }
}

module.exports = { createAndPushTag };

