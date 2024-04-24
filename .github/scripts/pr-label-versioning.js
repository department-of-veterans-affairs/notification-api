const prData = async ({ github, context, core }) => {
  const owner = context.repo.owner;
  const repo = context.repo.repo;

  const latestRelease = await github.rest.repos.getLatestRelease({
    owner,
    repo,
  });

  // Ensure the tag is in the format X.X.X
  let currentVersion = latestRelease.data.tag_name.replace(/^v/, '');
  if (!currentVersion.match(/^\d+\.\d+\.\d+$/)) {
    throw new Error("Invalid tag format");
  }

  const pullRequestData = context.payload.pull_request;
  const labels = pullRequestData.labels.map(label => label.name.toLowerCase());
  let versionParts = currentVersion.split('.').map(x => parseInt(x));

  // Define version bump logic based on the first label
  if (labels.includes('breaking change')) {
    versionParts[0] += 1; // Major version bump
    versionParts[1] = 0; // Reset minor version
    versionParts[2] = 0; // Reset patch version
  } else if (labels.some(label => ['hotfix', 'security', 'bug'].includes(label))) {
    versionParts[2] += 1; // Patch version bump
  } else {
    versionParts[1] += 1; // Minor version bump
    versionParts[2] = 0; // Reset patch version
  }

  const newVersion = versionParts.join('.');
};

module.exports = prData;


// this script above should return the values for the current version, newVersion, label that caused this semver conclusion, and the PR# involved. 
// Then, the scripts that call this module will be responsible for their own functions based on the values from this script
// the first QA Post will be responsbile for posting these values in an easy to read format for QA during her check in the pipeline.  let's get to that point.
