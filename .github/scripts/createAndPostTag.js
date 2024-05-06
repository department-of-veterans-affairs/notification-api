// createAndPostTag.js
const { prData, getReleaseVersionValue } = require('./prData');
const fs = require('fs');

async function createTag(github, owner, repo, newVersion, sha) {
    const tagName = `${newVersion}`;
    const tagMessage = `Release for version ${newVersion}`;

    // Create the tag object
    const { data: tagData } = await github.rest.git.createTag({
        owner,
        repo,
        tag: tagName,
        message: tagMessage,
        object: sha,
        type: 'commit',
    });

    // Create the reference in the repository
    await github.rest.git.createRef({
        owner,
        repo,
        ref: `refs/tags/${tagName}`,
        sha: tagData.sha,
    });

    console.log(`Tag ${tagName} created and pushed successfully.`);
}

const createAndPostTag = async ({ github, context, core }) => {
    const owner = context.repo.owner;
    const repo = context.repo.repo;

    try {
        // Retrieve PR data to decide the new version tag
        const { releaseBranchSha, newVersion } = await prData({ github, context, core });

        // Create and push the tag using the SHA from releaseBranchSha
        await createTag(github, owner, repo, newVersion, releaseBranchSha);

        // Update the RELEASE_VERSION variable
        await github.rest.actions.updateRepoVariable({
            owner,
            repo,
            name: 'RELEASE_VERSION',
            value: newVersion,
        });

        const summaryContent = `
### Successful Tag Creation!
- New version is ${newVersion}
- Tag created for version ${newVersion} using SHA: ${releaseBranchSha}
`;

        // Append the summary to the GitHub step summary file
        fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
        console.log('Tag summary generated and appended successfully.');
    } catch (error) {
        core.setFailed('Failed to process due to: ' + error.message);
        console.error(error);
    }
}

module.exports = createAndPostTag;

