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
  const labels = pullRequestData.labels; // Extract labels from the pull request data

  const label = labels[0].name.toLowerCase();
  let versionParts = currentVersion.split('.').map(x => parseInt(x));

  // Define version bump logic
  if (label === 'breaking change') {
    versionParts[0] += 1; // Major version bump
    versionParts[1] = 0; // Reset minor version
    versionParts[2] = 0; // Reset patch version
  } else if (['hotfix', 'security', 'bug'].includes(label)) {
    versionParts[2] += 1; // Patch version bump
  } else {
    versionParts[1] += 1; // Minor version bump
    versionParts[2] = 0; // Reset patch version
  }

  const newVersion = versionParts.join('.');
  console.log("The new version will be: ", newVersion);
}

module.exports = prData;

