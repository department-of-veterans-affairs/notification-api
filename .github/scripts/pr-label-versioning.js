const prData = async ({ github, context, core }) => {
  const owner = context.repo.owner;
  const repo = context.repo.repo;

  const latestRelease = await github.rest.repos.getLatestRelease({
    owner,
    repo,
  });

  // Get the tag string by parsing latestRelease.data.tag_name.  Output should be X.X.X, regardless if there was a vX.X.X or not with the latest release
  // The output of that data.tag_name could be vX.X.X or X.X.X, but its important that there is no v in the new proposed version.

  // Get the label on the PR (there should only be one; if there is more than one, error out with "there is more than one label".)
  const pullRequestData = context.payload.pull_request;
  const labels = pullRequestData.labels; // Extract labels from the pull request data


  // Version bump that tag string for major.minor.patch, with the following logic:
	// Major version bump label: breaking change
	// Patch version bump: hotfix, security, bug fix
	// Minor version bump: every other label
	// Should two labels exist on a PR, only one should be used for versioning, with preference towards major, then minor, then patch.

  // print the new proposed version bump like console.log("The new version will be: ", versionBump)

}

module.exports = prData;

