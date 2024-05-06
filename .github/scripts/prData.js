// prData.js

// Function to fetch pull requests associated with a commit
async function fetchPullRequests(github, owner, repo, sha) {
  return await github.rest.repos.listPullRequestsAssociatedWithCommit({
    owner,
    repo,
    commit_sha: sha,
  });
}

// Function to fetch the current release version
async function getReleaseVersionValue(github, owner, repo) {
  const { data } = await github.rest.actions.getRepoVariable({
    owner,
    repo,
    name: "RELEASE_VERSION",
  });
  return data.value;
}

async function fetchReleaseBranchSha(github, owner, repo) {
  const { data } = await github.rest.repos.getCommit({
    owner,
    repo,
    ref: "heads/release",
  });

  if (data && data.sha) {
    console.log("The release branch head SHA is: " + data.sha);
    return data.sha;
  } else {
    throw new Error("No SHA found in the response");
  }
}

// Function to process labels to determine new version and label
function processLabelsAndVersion(labels, currentVersion) {
  let versionParts = currentVersion.split(".").map((x) => parseInt(x, 10));
  let appliedLabel;

  if (labels.some((label) => label.name === "breaking-change")) {
    versionParts[0] += 1;
    versionParts[1] = 0;
    versionParts[2] = 0;
    appliedLabel = "breaking change";
  } else if (
    labels.some((label) => ["hotfix", "security", "bug"].includes(label.name))
  ) {
    versionParts[2] += 1;
    appliedLabel = labels.find((label) =>
      ["hotfix", "security", "bug"].includes(label.name),
    ).name;
  } else {
    versionParts[1] += 1;
    versionParts[2] = 0;
    appliedLabel = labels.find((label) => label).name; // Catch-all increment
  }

  return {
    newVersion: versionParts.join("."),
    appliedLabel,
  };
}

// Main function exported to handle pull request data
const prData = async ({ github, context, core }) => {
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const sha = context.payload.after;

  try {
    const pullRequestData = await fetchPullRequests(github, owner, repo, sha);
    const currentVersion = await getReleaseVersionValue(github, owner, repo);
    const releaseBranchSha = await fetchReleaseBranchSha(github, owner, repo);

    // const checkTag = await verifyNoExistingTag(github, owner, repo, releaseBranchSha)

    const labels = pullRequestData.data[0].labels.map((label) => ({
      id: label.id,
      name: label.name,
      description: label.description,
      color: label.color,
    }));
    const prNumber = pullRequestData.data[0].number;
    const prUrl = pullRequestData.data[0].html_url;

    const { newVersion, appliedLabel } = processLabelsAndVersion(
      labels,
      currentVersion,
    );

    return {
      releaseBranchSha,
      currentVersion,
      newVersion,
      label: appliedLabel,
      prNumber,
      prUrl,
    };
  } catch (error) {
    core.setFailed(`Error processing PR data: ${error.message}`);
    console.error("Error processing PR data:", error);
    return null; // Ensure to handle null in postQA.js if needed
  }
};

module.exports = {
  prData,
  getReleaseVersionValue,
};

// Export the getReleaseVersionValue function so other files can use it
// module.exports.getReleaseVersionValue = getReleaseVersionValue;
