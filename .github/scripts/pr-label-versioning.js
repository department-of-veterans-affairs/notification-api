const prData = async ({ github, context, core }) => {
  // const octokit = new Octokit({ auth: 'YOUR-TOKEN' });
  
  // Extract the owner and repo from the context
  const owner = context.repo.owner;
  const repo = context.repo.repo;

  // Fetch the latest release to get the current version tag
  const latestRelease = await github.rest.repos.getLatestRelease({
    owner,
    repo,
  });

  console.log("The tag name is ", latestRelease.data.tag_name)

}

// const prData = async ({ context }) => {
  // const pullRequestData = context.payload.pull_request;
  // const labels = pullRequestData.labels; // Extract labels from the pull request data

  // // Logging each label separately
  // labels.forEach(label => {
    // console.log(`Label Name: ${label.name}, Label Color: ${label.color}, Label Description: ${label.description}`);
  // });
// }

module.exports = prData;
