// This script creates a tag using the GitHub API with data from prData.js
// File: .github/scripts/createTag.js

const { Octokit } = require("@octokit/rest");
const prData = require("./prData");

async function createTag({ github, context, core }) {
    try {
        const prDetails = await prData({ github, context, core });

        const octokit = new Octokit({ auth: `token ${process.env.GITHUB_TOKEN}` });

        const tagCreateResponse = await octokit.rest.git.createTag({
            owner: "owner_username",
            repo: "repository_name",
            tag: "tag_name",
            message: "Tag message",
            object: "commit_sha",
            type: "commit",
            tagger: {
                name: "Your Name",
                email: "your_email@example.com",
                date: new Date().toISOString()
            }
        });

        const refCreateResponse = await github.rest.git.createRef({
            owner: context.repo.owner,
            repo: context.repo.repo,
            ref: `refs/tags/${prDetails.newVersion}`,
            sha: context.sha
        });

        console.log("Tag created successfully:", refCreateResponse.data.ref);
    } catch (error) {
        core.setFailed(`Failed to create tag: ${error.message}`);
    }
}

module.exports = createTag;

