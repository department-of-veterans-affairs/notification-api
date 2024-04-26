// File: .github/scripts/prData.js
const prData = async ({ github, context, core }) => {
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const ref = "heads/release";
  let releaseBranchSha;

  try {
    // First, get the latest SHA from the release branch:
    const { data } = await github.rest.repos.getCommit({
      owner,
      repo,
      ref
    });

    if (data && data.sha) {
      console.log("The release branch head SHA is: " + data.sha);
      releaseBranchSha = data.sha; // Store the SHA to export
      console.log("Release branch SHA set for export.");
    } else {
      throw new Error("No SHA found in the response");
    }
  } catch (error) {
    core.setFailed("Failed to retrieve the release branch SHA: " + error.message);
    console.error(error);
  }

  // Placeholder to confirm the above block executes correctly
  console.log("SHA retrieval block executed");

  // Additional processing to simulate omitted logic
  try {
    // Placeholder for getting the latest release (omitted in provided code)
    const latestRelease = {}; // Placeholder object
    let currentVersion = latestRelease.data?.tag_name.replace(/^v/, '');

    if (!currentVersion || !currentVersion.match(/^\d+\.\d+\.\d+$/)) {
      throw new Error("Invalid tag format");
    }

    const pullRequestData = context.payload.pull_request;
    const labels = pullRequestData.labels.map(label => label.name.toLowerCase());
    let versionParts = currentVersion.split('.').map(x => parseInt(x));
    let appliedLabel = '';

    // Version bump logic
    if (labels.includes('breaking-change')) {
      versionParts[0] += 1; versionParts[1] = 0; versionParts[2] = 0;
      appliedLabel = 'breaking change';
    } else if (labels.some(label => ['hotfix', 'security', 'bug'].includes(label))) {
      versionParts[2] += 1;
      appliedLabel = labels.find(label => ['hotfix', 'security', 'bug'].includes(label));
    } else {
      versionParts[1] += 1; versionParts[2] = 0;
      appliedLabel = labels.find(label => label);
    }

    const newVersion = versionParts.join('.');
    const prNumber = pullRequestData.number;

    // Return detailed response, including the releaseBranchSha
    return {
      releaseBranchSha,
      currentVersion,
      newVersion,
      label: appliedLabel,
      prNumber
    };

  } catch (error) {
    core.setFailed(`Error processing PR data: ${error.message}`);
  }
};

module.exports = prData;

