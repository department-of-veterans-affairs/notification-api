// File: .github/scripts/prData.js

// Adding this function to extract the PR number from commit messages
function extractPrNumber(message) {
  const prNumberMatch = message.match(/\(#(\d+)\)$/);
  return prNumberMatch ? parseInt(prNumberMatch[1], 10) : null;
}

const prData = async ({ github, context, core }) => {
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const ref = "heads/release"
  const name = "RELEASE_VERSION"
  let releaseBranchSha, latestReleaseTag, currentVersion, versionParts;

  try {
    // Fetching the latest SHA from the release branch
    const { data } = await github.rest.repos.getCommit({
      owner,
      repo,
      ref,
    });
    releaseBranchSha = data.sha;
    console.log("Release branch SHA: " + releaseBranchSha);

    // Fetching the value of the RELEASE_VERSION variable
    const { data: variableData } = await github.rest.actions.getRepoVariable({
      owner,
      repo,
      name,
    });

    // Directly use the version number from the response
    let currentVersion = variableData.value;
    console.log("Current RELEASE_VERSION: " + currentVersion);

    // Splitting the version string into major, minor, and patch parts and converting them to integers
    let versionParts = currentVersion.split('.').map(x => parseInt(x, 10));
    console.log("Version Parts: ", versionParts);

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

	// add logic here to get labels from push trigger, since payload.pull_request won't be the trigger for this workflow

	// const pushData = context.payload.push:

	// console.log(the pushData is ${pushData})

	// const pullRequestData = pushData.commits.message

    // // Assuming pullRequestData is available from context or has to be fetched
    // // const pullRequestData = context.payload.pull_request;
    // const labels = pullRequestData.labels.map(label => label.name.toLowerCase());
    // let appliedLabel = ''; 
    // console.log('Labels:', labels);

    // const prNumber = pullRequestData.number;

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
    console.error('Error processing PR data:', error);
    return {
      releaseBranchSha: '',
      currentVersion: '',
      newVersion: '',
      label: '',
      prNumber: '',
    }; // Return default data to prevent destructuring errors in postQA.js
  }
}

