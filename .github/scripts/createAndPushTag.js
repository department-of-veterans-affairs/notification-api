// File: .github/scripts/createAndPushTag.js
const fs = require("fs");
const prData = require("./prData");

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
    type: "commit",
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

async function updateReleaseVersion(github, owner, repo, newVersion) {
  const oldReleaseVarValue = await getReleaseVersionValue(github, owner, repo)
  console.log(`Updating RELEASE_VERSION from its current value of ${oldReleaseVarValue}`);

  await github.rest.actions.updateRepoVariable({
    owner,
    repo,
    name: "RELEASE_VERSION",
    value: newVersion,
  });

  const newReleaseVarValue = await getReleaseVersionValue(github, owner, repo)
  console.log(`Updated RELEASE_VERSION to ${newReleaseVarValue}`);

  return {
	oldReleaseVarValue,
	newReleaseVarValue
  }
}

async function createAndPushTag({ github, context, core }) {
  const owner = context.repo.owner;
  const repo = context.repo.repo;

  try {
    // Retrieve PR data to decide the new version tag
    const { releaseBranchSha, currentVersion, newVersion, label, prNumber } =
      await prData({ github, context, core });

    // Logging the data retrieved from prData for verification
    console.log(`Release branch SHA to use for tag: ${releaseBranchSha}`);
    console.log(
      `Current version from RELEASE_VERSION repo variable: ${currentVersion}`,
    );
    console.log(
      `Calculated new version (for creating tag and updating RELEASE_VERSION): ${newVersion}`,
    );
    console.log(`Label applied for changes: ${label}`);
    console.log(`PR Number associated with this commit: ${prNumber}`);

    // Verify the completeness and correctness of the data before proceeding
    if (
      !releaseBranchSha ||
      !currentVersion ||
      !newVersion ||
      !label ||
      !prNumber
    ) {
      throw new Error(
        "One or more required pieces of information are missing, cannot proceed with tagging.",
      );
    }

    // Call the function to create and push the tag using the SHA from releaseBranchSha
    await createTag(github, owner, repo, newVersion, releaseBranchSha);

    // Upon successful tag creation, update the RELEASE_VERSION variable
    await updateReleaseVersion(github, owner, repo, newVersion);

    const summaryContent = `
### Successful tag creation!
Old version was ${oldReleaseVarValue}
New version is ${newReleaseVarValue}
New tag successfully created for version ${newVersion} // This should be an actual tag get for sha call verification
The SHA used for this tag creation was the latest merge to the release branch: ${releaseBranchSha}
	`;

    // Append the summary to the GitHub step summary file
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
    console.log("Summary generated and appended successfully.");
  } catch (error) {
    core.setFailed("Failed to process due to: " + error.message);
    console.error(error);
  }
}

module.exports = { createAndPushTag };
