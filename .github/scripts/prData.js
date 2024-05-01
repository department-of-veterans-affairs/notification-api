// File: .github/scripts/prData.js

const prData = async ({ github, context, core }) => {
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const ref = "heads/release";
  const name = "RELEASE_VERSION";
  const mergeSHA = context.payload;

  let releaseBranchSha, latestReleaseTag, currentVersion, versionParts, appliedLabel, prNumber;

  console.log("Context Payload:", JSON.stringify(context.payload, null, 2));

  try {
    console.log(`MergeSha is ${mergeSHA}`);

    const pullRequestData = await github.rest.repos.listPullRequestsAssociatedWithCommit({
      owner,
      repo,
      commit_sha: mergeSHA,
    });

    // Assuming we can get the PR number from the first PR associated with the commit
    prNumber = pullRequestData.data[0].number;

    let labels = pullRequestData.data[0].labels.map(label => ({
      id: label.id,
      name: label.name,
      description: label.description,
      color: label.color,
    }));
    console.log(`The label(s) on the PR: ${labels}`);
    console.log(`PR Number: ${prNumber}`);

  } catch (error) {
    core.setFailed(`Error fetching pull requests: ${error.message}`);
    console.error('Error fetching pull requests:', error);
    return; // Return early on critical failure
  }

  try {
    const { data } = await github.rest.repos.getCommit({
      owner,
      repo,
      ref,
    });
    releaseBranchSha = data.sha;
    console.log(`Release branch SHA: ${releaseBranchSha}`);

    const { data: variableData } = await github.rest.actions.getRepoVariable({
      owner,
      repo,
      name,
    });
    currentVersion = variableData.value;
    console.log(`Current RELEASE_VERSION: ${currentVersion}`);

    versionParts = currentVersion.split('.').map(x => parseInt(x, 10));
    console.log(`Version Parts: `, versionParts);

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

    const newVersion = versionParts.join('.');

    return {
      releaseBranchSha,
      latestReleaseTag, // Ensure this variable is handled if needed
      currentVersion,
      newVersion,
      label: appliedLabel,
      prNumber
    };

  } catch (error) {
    core.setFailed(`Error processing PR data: ${error.message}`);
    console.error('Error processing PR data:', error);
    return {
      releaseBranchSha: '',
      latestReleaseTag: '',
      currentVersion: '',
      newVersion: '',
      label: '',
      prNumber: '',
    };
  }
};

module.exports = prData;

