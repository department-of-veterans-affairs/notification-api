// File: .github/scripts/createAndPushTag.js
const prData = require('./prData');

async function createAndPushTag({github, context, core}) {
    // Extract PR data
    const owners = context.repo.owner;
    const repos = context.repo.repo;
    const refs = "release";

    // First, get latest SHA from release branch:
    const releaseBranchHeadSHA = await github.rest.repos.listCommitStatusesForRef({
        owners,
        repos,
        refs,
    }).then(response => response.data);
    console.log("The release branch head SHA is: " + releaseBranchHeadSHA);

	// const { currentVersion, newVersion, label, prNumber } = await prData({ github, context, core });
    // const commitSha = context.sha;

    // try {
        // // Create a tag in the repository
        // const { data: tagData } = await github.rest.git.createTag({
            // owner: owner,
            // repo: repo,
            // tag: `${newVersion}`,
            // message: `Release version ${newVersion}`,
            // object: commitSha, // Commit SHA from environment variable
            // type: "commit",
            // tagger: {
                // name: "TEST",
                // email: "test@example.com",
                // date: new Date().toISOString()
            // }
        // });

        // console.log("Tag created successfully. Tag details:", tagData);

        // // Push the created tag to the remote repository
        // await github.rest.git.createRef({
            // owner: owner,
            // repo: repo,
            // ref: `refs/tags/${newVersion}`,
            // sha: commitSha
        // });

        // console.log("Tag pushed to the remote repository successfully.");
    // } catch (error) {
        // console.error("Error creating and pushing the tag:", error.message);
    // }
};

// Exporting createAndPushTag function directly
module.exports = { createAndPushTag };

