// File: .github/scripts/prData.js

// Constants for repository and API details
const REPO_OWNER = context.repo.owner;
const REPO_NAME = context.repo.repo;
const REPO_REF = "heads/release";
const VARIABLE_NAME = "RELEASE_VERSION";

/**
 * Fetch pull requests associated with a commit.
 * @param {object} github GitHub API instance
 * @param {string} sha Commit SHA
 * @returns {Promise<object>} Pull request data
 */
async function fetchPullRequests(github, sha) {
  return await github.rest.repos.listPullRequestsAssociatedWithCommit({
    owner: REPO_OWNER,
    repo: REPO_NAME,
    commit_sha: sha,
  });
}

/**
 * Fetch the current release version.
 * @param {object} github GitHub API instance
 * @returns {Promise<string>} Current release version
 */
async function fetchCurrentReleaseVersion(github) {
  const { data } = await github.rest.actions.getRepoVariable({
    owner: REPO_OWNER,
    repo: REPO_NAME,
    name: VARIABLE_NAME,
  });
  return data.value;
}

/**
 * Process labels to determine new version and label.
 * @param {Array} labels Labels of the PR
 * @param {string} currentVersion Current version string
 * @returns {object} New version and applied label
 */
function processLabelsAndVersion(labels, currentVersion) {
  let versionParts = currentVersion.split('.').map(x => parseInt(x, 10));
  let appliedLabel;

  if (labels.some(label => label.name === 'breaking-change')) {
    versionParts[0] += 1; versionParts[1] = 0; versionParts[2] = 0;
    appliedLabel = 'breaking change';
  } else if (labels.some(label => ['hotfix', 'security', 'bug'].includes(label.name))) {
    versionParts[2] += 1;
    appliedLabel = labels.find(label => ['hotfix', 'security', 'bug'].includes(label.name)).name;
  } else {
    versionParts[1] += 1; versionParts[2] = 0;
    appliedLabel = labels.find(label => label).name; // Catch-all increment
  }

  return {
    newVersion: versionParts.join('.'),
    appliedLabel
  };
}

const prData = async ({ github, context, core }) => {
  const mergeSHA = context.payload.after;

  try {
    const pullRequestData = await fetchPullRequests(github, mergeSHA);
    const currentVersion = await fetchCurrentReleaseVersion(github);

    const labels = pullRequestData.data[0].labels.map(label => ({
      id: label.id,
      name: label.name,
      description: label.description,
      color: label.color,
    }));
    const prNumber = pullRequestData.data[0].number;

    const { newVersion, appliedLabel } = processLabelsAndVersion(labels, currentVersion);

    // Output to logs
    console.log(`PR Number: ${prNumber}, Labels: ${labels.map(label => label.name).join(', ')}, New Version: ${newVersion}, Applied Label: ${appliedLabel}`);

    return {
      releaseBranchSha: '', // You will need to fetch or calculate this based on your logic
      latestReleaseTag: '', // Same as above
      currentVersion,
      newVersion,
      label: appliedLabel,
      prNumber
    };

  } catch (error) {
    core.setFailed(`Error processing PR data: ${error.message}`);
    console.error('Error processing PR data:', error);
    return null;
  }
};

module.exports = prData;

