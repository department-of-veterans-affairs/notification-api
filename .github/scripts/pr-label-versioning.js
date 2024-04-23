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
  core.setOutput("new_version", newVersion);

  const createTag = core.getInput('create-tag', { required: false }) === 'true';
  const summaryMessage = createTag 
    ? `A new tag ${newVersion} is created based on the ${labels.join(', ')} label(s).`
    : `The new version will be ${newVersion} based on the ${labels.join(', ')} label(s).`;

  const summaryContent = `
    ${summaryMessage}
    Latest current release tag is ${currentVersion}.
  `;
  require('fs').appendFileSync(process.env.GITHUB_STEP_SUMMARY, summaryContent);
};

module.exports = prData;

