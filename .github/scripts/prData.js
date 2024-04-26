// File: .github/scripts/prData.js
const getLatestCommitSha = async (github, owner, repo) => {
  const { data } = await github.rest.repos.getCommit({
    owner,
    repo,
    ref: "heads/release"
  });
  return data.sha;
};

const getLatestReleaseTag = async (github, owner, repo) => {
  const refs = await github.rest.git.listMatchingRefs({
	owner,
	repo,
	ref,
  });

  const releaseTags = refs.data.filter(tag => tag.name.includes("release"));
  if (releaseTags.length === 0) {
    throw new Error("No release tags found");
  }
  return releaseTags[0].name;
};

const calculateNewVersion = (currentVersion, labels) => {
  let versionParts = currentVersion.split('.').map(x => parseInt(x));
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
  return { newVersion: versionParts.join('.'), label: appliedLabel };
};

const prData = async ({ github, context, core }) => {
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  let releaseBranchSha, latestReleaseTag, currentVersion, newVersionData;

  try {
    releaseBranchSha = await getLatestCommitSha(github, owner, repo);
    console.log("Release branch SHA: " + releaseBranchSha);

    latestReleaseTag = await getLatestReleaseTag(github, owner, repo);
    currentVersion = latestReleaseTag;
    console.log("Latest release tag: " + latestReleaseTag);
  } catch (error) {
    core.setFailed("Failed to retrieve data: " + error.message);
    console.error(error);
    return { releaseBranchSha: '', currentVersion: '', latestReleaseTag: '' };
  }

  try {
    const pullRequestData = context.payload.pull_request;
    const labels = pullRequestData.labels.map(label => label.name.toLowerCase());
    newVersionData = calculateNewVersion(currentVersion, labels);

    return {
      releaseBranchSha,
      currentVersion,
      newVersion: newVersionData.newVersion,
      label: newVersionData.label,
      prNumber: pullRequestData.number
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

