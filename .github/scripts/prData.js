// File: .github/scripts/prData.js
const prData = async ({ github, context, core }) => {
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const ref = "heads/release"
  let releaseBranchSha, latestReleaseTag, currentVersion;

  try {
    // Fetching the latest SHA from the release branch
    const { data } = await github.rest.repos.getCommit({
      owner,
      repo,
      ref: "heads/release",
    });
    releaseBranchSha = data.sha;
    console.log("Release branch SHA: " + releaseBranchSha);

    // Fetching the latest release tag
    const latestRelease = await github.rest.repos.getLatestRelease({
      owner,
      repo
    });
    latestReleaseTag = latestRelease.data.tag_name;
    console.log("Latest release tag: " + latestReleaseTag);

    currentVersion = latestReleaseTag.replace(/^v/, ''); // Remove leading 'v' if present
    let versionParts = currentVersion.split('.').map(x => parseInt(x)); // Make the tag "name" a usable integer array
    
    const pullRequestData = context.payload.pull_request;
    const labels = pullRequestData.labels.map(label => label.name.toLowerCase());
    let appliedLabel = ''; 

    // Version bump logic based on labels
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
    return {
      releaseBranchSha: '',
      currentVersion: '',
      newVersion: '',
      label: '',
      prNumber: '',
    }; // Return default data to prevent destructuring errors in postQA.js
  }
};

module.exports = prData;

