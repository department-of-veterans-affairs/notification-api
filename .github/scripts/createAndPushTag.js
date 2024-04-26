// File: .github/scripts/createAndPushTag.js
const prData = require('./prData');

async function createAndPushTag({ github, context, core }) {
    const owner = context.repo.owner;
    const repo = context.repo.repo;
    const ref = "heads/release"; // Ensure this refers to the branch name

    try {
        // First, get the latest SHA from the release branch:
        const { data } = await github.rest.repos.getCommit({
            owner,
            repo,
            ref
        });

        if (data && data.sha) {
            console.log("The release branch head SHA is: " + data.sha);
        } else {
            throw new Error("No SHA found in the response");
        }
    } catch (error) {
        core.setFailed("Failed to retrieve the release branch SHA: " + error.message);
        console.error(error);
    }

	const { releaseBranchSha, currentVersion, newVersion, label, prNumber } = await prData({github, context, core});

	try {
		// Create a tag in the repository
		const { data: tagData } = await github.rest.git.createTag({
			owner: owner,
			repo: repo,
			tag: `${newVersion}`,
			message: `Release version ${newVersion}`,
			object: releaseBranchSha, // Commit SHA from environment variable
			type: "commit",
			tagger: {
				name: "TEST",
				email: "test@example.com",
				date: new Date().toISOString()
			}
		});

		console.log("Tag created successfully. Tag details:", tagData);

		// Push the created tag to the remote repository
		await github.rest.git.createRef({
			owner: owner,
			repo: repo,
			// ref: `refs/tags/${newVersion}`,
			ref: `${newVersion}`,
			sha: releaseBranchSha
		});

		console.log("Tag pushed to the remote repository successfully.");
	} catch (error) {
		console.error("Error creating and pushing the tag:", error.message);
	}
};

// Exporting createAndPushTag function directly
module.exports = { createAndPushTag };

