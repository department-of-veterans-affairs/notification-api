// File: .github/scripts/prData.js
const semver = require('semver');

// Function to get the highest semantic version tag
async function getHighestSemverTag(github, owner, repo) {
    try {
        const tags = await github.rest.repos.listTags({
            owner,
            repo,
        });

        const filteredTags = tags.data.filter(tag => 
            tag.name.includes('release') && semver.valid(semver.coerce(tag.name))
        );

        const highestTag = filteredTags.sort((a, b) => 
            semver.rcompare(semver.coerce(a.name), semver.coerce(b.name))
        )[0];

        return highestTag ? highestTag.name : null;
    } catch (error) {
        console.error('Failed to fetch tags:', error);
        return null;
    }
}

const prData = async ({ github, context, core }) => {
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  let releaseBranchSha, latestReleaseTag, currentVersion;

  try {
    // Get the latest commit SHA of the release branch
    const { data } = await github.rest.repos.getCommit({
      owner,
      repo,
      ref: "heads/release"
    });
    releaseBranchSha = data.sha;
    console.log("Release branch SHA: " + releaseBranchSha);

    // Get the highest semver tag
    latestReleaseTag = await getHighestSemverTag(github, owner, repo);
    currentVersion = latestReleaseTag || '0.1.0'; // Default if no tags are found
    console.log("Latest Release Tag: " + latestReleaseTag);

    // Version calculation based on labels
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

