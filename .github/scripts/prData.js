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
      ref,
    });

    releaseBranchSha = data.sha;
    console.log("Release branch SHA: " + releaseBranchSha);


	//
	const refs = await octokit.rest.git.listMatchingRefs({
	  owner,
	  repo,
	  ref,
	});

	console.log("the refs from listMatchingRefs for release branch are: " + refs.data)

    // Fetch all tags from the repository
    const tags = await github.rest.repos.listTags({
      owner,
      repo,
      per_page: 100 // Adjust based on your tag frequency
    });

    // Filter tags to find the latest one with "release" in it
    const releaseTags = tags.data.filter(tag => tag.name.includes("release"));
    if (releaseTags.length > 0) {
      latestReleaseTag = releaseTags[0].name;
      currentVersion = latestReleaseTag;
      console.log("Latest release tag: " + latestReleaseTag);
    } else {
      throw new Error("No release tags found");
    }
  } catch (error) {
    core.setFailed("Failed to retrieve data: " + error.message);
    console.error(error);
    return { releaseBranchSha: '', currentVersion: '', latestReleaseTag: '' };
  }

  try {
    // versionParts will now need to be based on latest tag with string "release"
    let versionParts = currentVersion.split('.').map(x => parseInt(x));
    const pullRequestData = context.payload.pull_request;
    const labels = pullRequestData.labels.map(label => label.name.toLowerCase());
    let appliedLabel = ''; // Initialize as empty to cover cases where no labels match

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


