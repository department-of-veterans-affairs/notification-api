// File: .github/scripts/pr-label-versioning.js
function prData({ github, context, core }) {
    // Extract the pull request object from the GitHub context
    const pullRequest = context.payload.pull_request;

	core.info(pullRequest)


    // Check if there are labels and print them
    // if (pullRequest && pullRequest.labels && pullRequest.labels.length > 0) {
        // core.info('Pull Request Labels:');
        // pullRequest.labels.forEach(label => {
            // core.info(`- ${label.name} (Color: ${label.color}, Description: ${label.description || 'No description provided.'})`);
        // });
    // } else {
        // core.info('No labels found on this pull request.');
    // }
}

module.exports = prData;

