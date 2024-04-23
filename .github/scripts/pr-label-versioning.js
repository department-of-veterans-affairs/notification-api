const { Octokit } = require("@octokit/core");

const prData = async ({ github, context, core }) => {
  const octokit = new Octokit({ auth: 'YOUR-TOKEN' });
  const repo = context.payload.repository;

  // Fetch the latest release to get the current version tag
  const latestRelease = await octokit.request('GET /repos/{owner}/{repo}/releases', {
    owner: repo.owner.login,
    repo: repo.name
  });

  // Extract the version tag from the latest release
  const latestVersionTag = latestRelease.data[0].tag_name.replace('v', '');
  let [major, minor, patch] = latestVersionTag.split('.').map(num => parseInt(num, 10));

  // Determine the version bump from PR labels
  const prNumber = context.payload.pull_request.number;
  const { data: labels } = await github.rest.issues.listLabelsOnIssue({
    owner: repo.owner.login,
    repo: repo.name,
    issue_number: prNumber,
  });

  const priorityLabels = {
    major: ["breaking change"],
    minor: [],
    patch: ["hotfix", "security", "bug fix"],
  };

  let versionBump = 'patch'; // Default to patch
  labels.forEach(label => {
    if (priorityLabels.major.includes(label.name)) versionBump = 'major';
    else if (priorityLabels.patch.includes(label.name) && versionBump !== 'major') versionBump = 'patch';
    else if (!priorityLabels.major.includes(label.name) && !priorityLabels.patch.includes(label.name)) versionBump = 'minor';
  });

  // Increment version numbers based on the bump
  if (versionBump === 'major') {
    major++;
    minor = 0;
    patch = 0;
  } else if (versionBump === 'minor') {
    minor++;
    patch = 0;
  } else if (versionBump === 'patch') {
    patch++;
  }

  const newVersionTag = `v${major}.${minor}.${patch}`;
  
  // Output the new version
  core.setOutput('new-version', newVersionTag);
  console.log(`New version to be tagged: ${newVersionTag}`);

  // Log each label and bump decision
  labels.forEach(label => {
    console.log(`Label Name: ${label.name}, Label Color: ${label.color}, Label Description: ${label.description}`);
  });
};

module.exports = prData;

