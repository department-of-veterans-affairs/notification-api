const prData = async ({ context }) => {
  const pullRequestData = context.payload.pull_request;
  const labels = pullRequestData.labels; // Extract labels from the pull request data

  // Logging each label separately
  labels.forEach(label => {
    console.log(`Label Name: ${label.name}, Label Color: ${label.color}, Label Description: ${label.description}`);
  });
}

module.exports = prData;
