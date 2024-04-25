// This script will create a tag utilizing the prData.js
// File: .github/scripts/createTag.js

const prData = require("./prData");

async function createTag({ github, context, core }) {
  try {
    // Retrieve PR data
    const prDetails = await prData({ github, context, core });

    // Create a new tag using GitHub API
    const response = await github.rest.git.createRef({
      owner: context.repo.owner,
      repo: context.repo.repo,
      ref: `refs/tags/v${prDetails.newVersion}`,
      sha: context.sha // Assuming context.sha is the commit SHA to be tagged
    });

    // Optionally update a changelog or release notes if necessary
    // This could be another function call here

    console.log("Tag created successfully:", response.data.ref);

  } catch (error) {
    core.setFailed(`Failed to create tag: ${error.message}`);
  }
}

module.exports = createTag;

