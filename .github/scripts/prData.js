// File: .github/scripts/prData.js
const { compare } = require('semver');

const prData = async ({ github, context, core }) => {
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  let releaseBranchSha, latestReleaseTag, currentVersion;

  try {
    const { data } = await github.rest.repos.getCommit({
      owner,
      repo,
      ref: "heads/release"
    });

    releaseBranchSha = data.sha;
    console.log("Release branch SHA: " + releaseBranchSha);

    const tags = await github.rest.repos.listTags({
      owner,
      repo,
      per_page: 100 // Adjust based on your tag frequency
    });

    // Filter tags to find those with "release" and sort them by semantic versioning
    const releaseTags = tags.data
      .filter(tag => tag.name.includes("release"))
      .sort((a, b) => compare(b.name, a.name)); // Sort in descending order

    if (releaseTags.length > 0) {
      latestReleaseTag = releaseTags[0].name;
      currentVersion = latestReleaseTag;
      console.log("Latest release tag: " + latestReleaseTag);
    } else {
      throw new Error("No release tags found");
    }
  } catch (error) {
    core.setFailed("Failed to retrieve data: " + error.message);
    console.error(error);
    return { releaseBranchSha: '', currentVersion: '', latestReleaseTag: '' };
  }

  try {
    let versionParts = currentVersion.split('.').map(x => parseInt(x));
    const pullRequestData = context.payload.pull_request;
    const labels = pullRequestData.labels.map(label => label.name.toLowerCase());
    let appliedLabel = '';

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

    return {
      releaseBranchSha,
      currentVersion,
      newVersion,
      label: appliedLabel,
      prNumber
    };
  } catch (error) {
    core.setFailed(`Error processing PR data: ${error.message}`);
    return {
      releaseBranchSha: '',
      currentVersion: '',
      newVersion: '',
      label: '',
      prNumber: '',
    };
  }
};

module.exports = prData;

